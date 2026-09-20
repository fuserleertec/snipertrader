from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel

from sniper_data.config import KAFKA_TOPICS

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
        if isinstance(value, BaseModel):
            payload = value.model_dump(mode="json")
        else:
            payload = value
        record = {"topic": topic, "key": key, "value": payload}
        self.topics[topic].append(record)
        for cb in list(self._subs[topic]):
            await cb(payload)

    def subscribe(self, topic: str, callback: Callable[[dict], Awaitable[None]]) -> None:
        self._subs[topic].append(callback)

    def latest(self, topic: str) -> dict | None:
        if not self.topics[topic]:
            return None
        return self.topics[topic][-1]["value"]


class KafkaBus:
    def __init__(self, bootstrap: str, client_id: str = "sniper-data") -> None:
        self.bootstrap = bootstrap
        self.client_id = client_id
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
                NewTopic(name=t, num_partitions=1, replication_factor=1)
                for t in KAFKA_TOPICS
                if t not in existing
            ]
            if missing:
                await admin.create_topics(missing)
        except Exception as exc:  # noqa: BLE001 — broker may auto-create
            log.warning("topic ensure skipped: %s", exc)
        finally:
            await admin.close()

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap,
            client_id=self.client_id,
            value_serializer=_dumps,
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
        )
        await self._producer.start()
        log.info("kafka producer up (%s)", self.bootstrap)

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, value: Any, key: str | None = None) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaBus.start() was not called")
        await self._producer.send_and_wait(topic, value, key=key)


async def consume_topic(
    bootstrap: str,
    topic: str,
    group_id: str,
) -> AsyncIterator[dict]:
    from aiokafka import AIOKafkaConsumer

    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        value_deserializer=lambda b: json.loads(b.decode()),
        auto_offset_reset="latest",
    )
    await consumer.start()
    try:
        async for msg in consumer:
            yield msg.value
    finally:
        await consumer.stop()


async def wait_for_kafka(bootstrap: str, timeout_s: float = 45.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    last = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            bus = KafkaBus(bootstrap)
            await bus.start()
            await bus.stop()
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            await asyncio.sleep(1.0)
    raise RuntimeError(f"kafka not ready: {last}")
