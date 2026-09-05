"""Pattern-zone Redis writes with mandatory TTL (max 48h) + eviction job.

Provisional key map for ML Researchers
--------------------------------------
  fvg:{symbol}:{id}     Fair-value gap zone payload (JSON)
  sweep:{symbol}:{id}   Liquidity sweep event payload (JSON)
  mss:{symbol}:{id}     Market-structure shift event (JSON)
  ob:{symbol}:{id}      Order-block zone payload (JSON)

Every write uses SET with EX (SETEX semantics). TTL is clamped to
``FVG_TTL_MAX_SECONDS`` (172800). The background eviction job:

  * SCAN ``fvg:*`` ``sweep:*`` ``mss:*`` ``ob:*``
  * DELETE keys whose TTL is already gone (-2) — no-op
  * EXPIRE keys that have no TTL (-1) or a TTL > 48h
  * DELETE keys whose ``created_ts_ms`` / ``ts_ms`` is older than 48h
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sniper_data.bus.redis_store import StateStore
from sniper_data.config import FVG_TTL_MAX_SECONDS
from sniper_data.models import FVGZone, MssEvent, OrderBlock, SweepEvent

log = logging.getLogger(__name__)

ZONE_SCAN_PATTERNS = ("fvg:*", "sweep:*", "mss:*", "ob:*")


def fvg_key(symbol: str, zone_id: str) -> str:
    return f"fvg:{symbol}:{zone_id}"


def sweep_key(symbol: str, event_id: str) -> str:
    return f"sweep:{symbol}:{event_id}"


def mss_key(symbol: str, event_id: str) -> str:
    return f"mss:{symbol}:{event_id}"


def ob_key(symbol: str, zone_id: str) -> str:
    return f"ob:{symbol}:{zone_id}"


def fvg_channel(symbol: str) -> str:
    return f"fvg:{symbol}"


def sweep_channel(symbol: str) -> str:
    return f"sweep:{symbol}"


def mss_channel(symbol: str) -> str:
    return f"mss:{symbol}"


def ob_channel(symbol: str) -> str:
    return f"ob:{symbol}"


def zone_scan_pattern(prefix: str, symbol: str) -> str:
    return f"{prefix}:{symbol}:*"


def clamp_ttl(ttl_seconds: int | None) -> int:
    if ttl_seconds is None:
        return FVG_TTL_MAX_SECONDS
    return max(1, min(int(ttl_seconds), FVG_TTL_MAX_SECONDS))


async def store_fvg(
    store: StateStore,
    zone: FVGZone,
    ttl_seconds: int | None = None,
) -> str:
    key = fvg_key(zone.symbol, zone.id)
    ttl = clamp_ttl(ttl_seconds if ttl_seconds is not None else zone.ttl_seconds)
    payload = zone.model_copy(update={"ttl_seconds": ttl})
    await store.set(key, payload, ttl=ttl)
    await store.publish(fvg_channel(zone.symbol), payload)
    return key


async def store_sweep(
    store: StateStore,
    event: SweepEvent,
    ttl_seconds: int | None = None,
) -> str:
    key = sweep_key(event.symbol, event.id)
    await store.set(key, event, ttl=clamp_ttl(ttl_seconds))
    await store.publish(sweep_channel(event.symbol), event)
    return key


async def store_mss(
    store: StateStore,
    event: MssEvent,
    ttl_seconds: int | None = None,
) -> str:
    key = mss_key(event.symbol, event.id)
    await store.set(key, event, ttl=clamp_ttl(ttl_seconds))
    await store.publish(mss_channel(event.symbol), event)
    return key


async def store_ob(
    store: StateStore,
    zone: OrderBlock,
    ttl_seconds: int | None = None,
) -> str:
    key = ob_key(zone.symbol, zone.id)
    ttl = clamp_ttl(ttl_seconds if ttl_seconds is not None else zone.ttl_seconds)
    payload = zone.model_copy(update={"ttl_seconds": ttl})
    await store.set(key, payload, ttl=ttl)
    await store.publish(ob_channel(zone.symbol), payload)
    return key


def _created_ms(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for field in ("created_ts_ms", "ts_ms"):
        if field in payload:
            try:
                return int(payload[field])
            except (TypeError, ValueError):
                return None
    return None


async def evict_expired_zones(
    store: StateStore,
    *,
    now_ms: int | None = None,
    max_age_seconds: int = FVG_TTL_MAX_SECONDS,
) -> dict[str, int]:
    """Repair missing/overlong TTLs and drop zones older than 48h."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    cutoff = now_ms - max_age_seconds * 1000
    stats = {"scanned": 0, "expired_deleted": 0, "ttl_repaired": 0}
    for match in ZONE_SCAN_PATTERNS:
        keys = await store.scan(match)
        for key in keys:
            stats["scanned"] += 1
            payload = await store.get(key)
            created = _created_ms(payload)
            if created is not None and created < cutoff:
                await store.delete(key)
                stats["expired_deleted"] += 1
                continue
            ttl = await store.ttl(key)
            if ttl == -1 or ttl > max_age_seconds:
                remaining = max_age_seconds
                if created is not None:
                    age_s = max(0, (now_ms - created) // 1000)
                    remaining = max(1, max_age_seconds - age_s)
                await store.expire(key, remaining)
                stats["ttl_repaired"] += 1
    log.info("zone eviction %s", stats)
    return stats
