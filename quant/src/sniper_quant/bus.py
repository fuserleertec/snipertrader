"""Message-bus helpers for ``setup_signals`` and ``ensemble_features``.

Mirrors ``sniper_data.bus.kafka`` (InMemoryBus + Kafka consume) without
importing the DE package so ``quant/`` stays independently installable.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from pydantic import BaseModel

log = logging.getLogger(__name__)

SETUP_SIGNALS_TOPIC = "setup_signals"
ENSEMBLE_FEATURES_TOPIC = "ensemble_features"
OHLCV_BARS_TOPIC = "ohlcv_bars"


def dumps_bytes(value: Any) -> bytes:
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

    def history(self, topic: str) -> list[dict]:
        return [row["value"] for row in self.topics[topic]]


def _decode_kafka_key(raw: bytes | str | None) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        text = raw.decode(errors="replace").strip()
    else:
        text = str(raw).strip()
    return text or None


async def consume_keyed_topic(
    bootstrap: str,
    topic: str,
    group_id: str,
) -> AsyncIterator[tuple[str | None, dict]]:
    from aiokafka import AIOKafkaConsumer

    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        key_deserializer=_decode_kafka_key,
        value_deserializer=lambda b: json.loads(b.decode()),
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for msg in consumer:
            value = msg.value
            if isinstance(value, dict):
                yield msg.key, value
            else:
                log.warning("skip non-object kafka payload on %s", topic)
    finally:
        await consumer.stop()


async def consume_topic(
    bootstrap: str,
    topic: str,
    group_id: str,
) -> AsyncIterator[dict]:
    async for _key, value in consume_keyed_topic(bootstrap, topic, group_id):
        yield value
