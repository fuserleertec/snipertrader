"""Read DE Phase 2 Redis books for downstream setup logic.

Consumes landed shapes only — no field aliases, no ``schema_version``.

* ``avwap:{symbol}:{anchor_id}`` → ``AnchoredVWAP``
* ``volume_profile:{symbol}:{session_type}`` → ``VolumeProfile``
* ``kill_zone:{symbol}`` → ``KillZoneEvent``
* Kafka ``kill_zone_events`` (same JSON as the Redis key)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sniper_data.avwap import redis_avwap_key, redis_avwap_latest_key
from sniper_data.bus.kafka import EventBus
from sniper_data.bus.redis_store import StateStore
from sniper_data.kill_zones import KILL_ZONE_TOPIC, redis_kill_zone_active_key, redis_kill_zone_key
from sniper_data.models import AnchoredVWAP, KillZoneEvent, SessionType, VolumeProfile
from sniper_data.symbols import normalize_symbol
from sniper_data.volume_profile import redis_volume_profile_key


def _validate(model, raw: Any):
    if raw is None:
        return None
    if isinstance(raw, model):
        return raw
    return model.model_validate(raw)


async def get_avwap(store: StateStore, symbol: str, anchor_id: str) -> AnchoredVWAP | None:
    symbol = normalize_symbol(symbol)
    return _validate(AnchoredVWAP, await store.get(redis_avwap_key(symbol, anchor_id)))


async def get_latest_avwap(store: StateStore, symbol: str) -> AnchoredVWAP | None:
    symbol = normalize_symbol(symbol)
    return _validate(AnchoredVWAP, await store.get(redis_avwap_latest_key(symbol)))


async def get_volume_profile(
    store: StateStore,
    symbol: str,
    session_type: str | SessionType,
) -> VolumeProfile | None:
    symbol = normalize_symbol(symbol)
    st = session_type.value if isinstance(session_type, SessionType) else session_type
    return _validate(VolumeProfile, await store.get(redis_volume_profile_key(symbol, st)))


async def list_volume_profiles(store: StateStore, symbol: str) -> list[VolumeProfile]:
    symbol = normalize_symbol(symbol)
    out: list[VolumeProfile] = []
    for key in await store.scan(f"volume_profile:{symbol}:*"):
        if key.startswith("volume_profile:acc:"):
            continue
        parsed = _validate(VolumeProfile, await store.get(key))
        if parsed is not None:
            out.append(parsed)
    return out


async def get_kill_zone(store: StateStore, symbol: str) -> KillZoneEvent | None:
    symbol = normalize_symbol(symbol)
    return _validate(KillZoneEvent, await store.get(redis_kill_zone_key(symbol)))


async def get_active_kill_zone(store: StateStore, asset_class: str) -> dict | None:
    raw = await store.get(redis_kill_zone_active_key(asset_class))
    return raw if isinstance(raw, dict) else None


def subscribe_kill_zone_events(
    bus: EventBus,
    callback: Callable[[KillZoneEvent], Awaitable[None]],
) -> None:
    """In-process / test hook. Kafka workers use ``consume_topic('kill_zone_events')``."""

    async def _wrapped(payload: dict) -> None:
        await callback(KillZoneEvent.model_validate(payload))

    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise TypeError("bus does not support in-process subscribe")
    subscribe(KILL_ZONE_TOPIC, _wrapped)
