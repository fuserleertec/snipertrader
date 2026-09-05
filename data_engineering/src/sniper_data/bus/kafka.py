from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel

from sniper_data.bus.resilience import Backoff, retry_async
from sniper_data.config import KAFKA_TOPICS, get_settings
from sniper_data.metrics import record_kafka_error, record_publish, set_kafka_lag

log = logging.getLogger(__name__)


def _dumps(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        return value.model_dump_json().encode()
    return json.dumps(value).encode()


class EventBus(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def publish(self, topic: str, value: Any, key: str | None = None) -> None: ...


class InMemoryBus:
    """Test / no-broker bus. Messages are retained per topic."""

    def __init__(self, maxlen: int = 10_000) -> None:
        self.topics: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=maxlen))
        self._subs: dict[str, list[Callable[[dict], Awaitable[None]]]] = defaultdict(list)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, topic: str, value: Any, key: str | None = None) -> None:
        t0 = time.perf_counter()
        if isinstance(value, BaseModel):
            payload = value.model_dump(mode="json")
        else:
            payload = value
        record = {"topic": topic, "key": key, "value": payload}
        self.topics[topic].append(record)
        for cb in list(self._subs[topic]):
            await cb(payload)
        record_publish(topic, time.perf_counter() - t0)

    def subscribe(self, topic: str, callback: Callable[[dict], Awaitable[None]]) -> None:
        self._subs[topic].append(callback)

    def latest(self, topic: str) -> dict | None:
        if not self.topics[topic]:
            return None
        return self.topics[topic][-1]["value"]


class KafkaBus:
    """Producer with reconnect/backoff. Risk is never applied here."""

    def __init__(
        self,
        bootstrap: str,
        client_id: str = "sniper-data",
        *,
        partitions: int | None = None,
        send_wait: bool | None = None,
        retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self.bootstrap = bootstrap
        self.client_id = client_id
        self.partitions = int(partitions if partitions is not None else settings.kafka_partitions)
        self.send_wait = settings.kafka_send_wait if send_wait is None else send_wait
        self.retries = int(retries if retries is not None else settings.kafka_retries)
        self._producer = None

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic

        admin = AIOKafkaAdminClient(
            bootstrap_servers=self.bootstrap,
            client_id=f"{self.client_id}-admin",
        )
        await admin.start()
        try:
            existing = set(await admin.list_topics())
            missing = [
                NewTopic(
                    name=t,
                    num_partitions=max(1, self.partitions),
                    replication_factor=1,
                )
                for t in KAFKA_TOPICS
                if t not in existing
            ]
            if missing:
                await admin.create_topics(missing)
        except Exception as exc:  # noqa: BLE001 — broker may auto-create
            log.warning("topic ensure skipped: %s", exc)
        finally:
            await admin.close()

        await self._start_producer()
        log.info(
            "kafka producer up (%s partitions=%s wait=%s)",
            self.bootstrap,
            self.partitions,
            self.send_wait,
        )

    async def _start_producer(self) -> None:
        from aiokafka import AIOKafkaProducer

        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:  # noqa: BLE001
                pass
            self._producer = None
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap,
            client_id=self.client_id,
            value_serializer=_dumps,
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
            acks="all",
            request_timeout_ms=15_000,
            retry_backoff_ms=100,
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, value: Any, key: str | None = None) -> None:
        async def _once() -> None:
            if self._producer is None:
                await self._start_producer()
            assert self._producer is not None
            t0 = time.perf_counter()
            fut = self._producer.send(topic, value, key=key)
            if self.send_wait:
                await fut
            record_publish(topic, time.perf_counter() - t0)

        def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
            record_kafka_error("publish")
            log.warning("kafka publish retry %s after %s (sleep %.3fs)", attempt, exc, delay)
            self._producer = None

        await retry_async(
            _once,
            attempts=self.retries,
            backoff=Backoff(base_s=0.1, max_s=4.0),
            on_retry=_on_retry,
        )


async def consume_topic(
    bootstrap: str,
    topic: str,
    group_id: str,
    *,
    stop: asyncio.Event | None = None,
) -> AsyncIterator[dict]:
    """Consumer with reconnect/backoff. No risk filter — Quant validates at publish."""
    from aiokafka import AIOKafkaConsumer
    from aiokafka.structs import TopicPartition

    backoff = Backoff(base_s=0.2, max_s=8.0)
    while stop is None or not stop.is_set():
        consumer = None
        try:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=bootstrap,
                group_id=group_id,
                value_deserializer=lambda b: json.loads(b.decode()),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                session_timeout_ms=15_000,
                heartbeat_interval_ms=3_000,
                request_timeout_ms=20_000,
            )
            await consumer.start()
            backoff.reset()
            async for msg in consumer:
                if stop is not None and stop.is_set():
                    break
                try:
                    assigned = consumer.assignment()
                    if assigned:
                        end = await consumer.end_offsets(list(assigned))
                        lag = 0
                        for tp in assigned:
                            pos = await consumer.position(tp)
                            if isinstance(tp, TopicPartition):
                                lag += max(0, int(end.get(tp, pos) - pos))
                        set_kafka_lag(topic, group_id, lag)
                except Exception:  # noqa: BLE001
                    pass
                yield msg.value
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            record_kafka_error("consume")
            delay = backoff.next()
            log.warning("kafka consumer %s/%s: %s; reconnect in %.2fs", topic, group_id, exc, delay)
            await asyncio.sleep(delay)
        finally:
            if consumer is not None:
                try:
                    await consumer.stop()
                except Exception:  # noqa: BLE001
                    pass
        if stop is not None and stop.is_set():
            break


async def wait_for_kafka(bootstrap: str, timeout_s: float = 45.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    last = None
    backoff = Backoff(base_s=0.5, max_s=4.0, jitter=0.1)
    while asyncio.get_event_loop().time() < deadline:
        try:
            bus = KafkaBus(bootstrap)
            await bus.start()
            await bus.stop()
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            await asyncio.sleep(backoff.next())
    raise RuntimeError(f"kafka not ready: {last}")
