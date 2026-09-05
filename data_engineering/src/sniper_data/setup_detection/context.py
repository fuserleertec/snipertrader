"""Read landed DE Redis books for setup detectors. No invented keys."""

from __future__ import annotations

from typing import Any

from sniper_data.avwap import index_ids, redis_avwap_key
from sniper_data.bus.redis_store import StateStore
from sniper_data.kill_zones import redis_kill_zone_key
from sniper_data.models import (
    AnchoredVWAP,
    FVGZone,
    KillZoneEvent,
    MssEvent,
    OrderBlock,
    SessionLevels,
    SessionType,
    SweepEvent,
    VolumeProfile,
    VWAPValues,
)
from sniper_data.pattern_detection.context import (
    get_avwap,
    get_kill_zone,
    get_latest_avwap,
    get_volume_profile,
    list_volume_profiles,
)
from sniper_data.sessions import redis_session_key
from sniper_data.symbols import normalize_symbol
from sniper_data.volume_profile import redis_volume_profile_key
from sniper_data.vwap import redis_vwap_key
from sniper_data.zones import fvg_key, mss_key, ob_key, sweep_key

# Re-export exact key helpers so callers do not invent names.
__all__ = [
    "atr_regime",
    "fvg_key",
    "get_active_fvgs",
    "get_active_obs",
    "get_avwap",
    "get_htf_obs",
    "get_kill_zone",
    "get_latest_avwap",
    "get_mss",
    "get_session",
    "get_session_vwap",
    "get_sweep",
    "get_volume_profile",
    "list_avwaps",
    "list_volume_profiles",
    "mss_key",
    "ob_key",
    "redis_avwap_key",
    "redis_kill_zone_key",
    "redis_session_key",
    "redis_volume_profile_key",
    "redis_vwap_key",
    "sweep_key",
]


def _parse(model, raw: Any):
    if raw is None:
        return None
    if isinstance(raw, model):
        return raw
    return model.model_validate(raw)


async def get_session_vwap(store: StateStore, symbol: str) -> VWAPValues | None:
    symbol = normalize_symbol(symbol)
    return _parse(VWAPValues, await store.get(redis_vwap_key(symbol, "session")))


async def get_session(
    store: StateStore,
    symbol: str,
    session_type: str | SessionType,
) -> SessionLevels | None:
    symbol = normalize_symbol(symbol)
    st = session_type.value if isinstance(session_type, SessionType) else session_type
    return _parse(SessionLevels, await store.get(redis_session_key(symbol, st)))


async def get_sweep(store: StateStore, symbol: str, event_id: str) -> SweepEvent | None:
    return _parse(SweepEvent, await store.get(sweep_key(normalize_symbol(symbol), event_id)))


async def get_mss(store: StateStore, symbol: str, event_id: str) -> MssEvent | None:
    return _parse(MssEvent, await store.get(mss_key(normalize_symbol(symbol), event_id)))


async def get_active_fvgs(store: StateStore, symbol: str) -> list[FVGZone]:
    symbol = normalize_symbol(symbol)
    out: list[FVGZone] = []
    for key in await store.scan(f"fvg:{symbol}:*"):
        ttl = await store.ttl(key)
        if ttl == -2:
            continue
        parsed = _parse(FVGZone, await store.get(key))
        if parsed is None or parsed.mitigated:
            continue
        out.append(parsed)
    return out


async def get_active_obs(store: StateStore, symbol: str) -> list[OrderBlock]:
    symbol = normalize_symbol(symbol)
    out: list[OrderBlock] = []
    for key in await store.scan(f"ob:{symbol}:*"):
        parsed = _parse(OrderBlock, await store.get(key))
        if parsed is None or parsed.mitigated:
            continue
        out.append(parsed)
    return out


def ranges_overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> bool:
    return a_low <= b_high and b_low <= a_high


def price_in_range(price: float, low: float, high: float, *, pad: float = 0.0) -> bool:
    return (low - pad) <= price <= (high + pad)


def profile_overlaps_zone(profile: VolumeProfile | None, low: float, high: float) -> bool:
    if profile is None:
        return False
    if price_in_range(profile.poc, low, high):
        return True
    for node in profile.high_volume_nodes:
        if price_in_range(node.price, low, high):
            return True
    return False


def band_tagged(price: float, vwap: VWAPValues, *, frac: float = 0.25, include_3s: bool = False) -> str | None:
    """Return which session-VWAP σ band ``price`` tagged (Phase 1 flat fields)."""
    sigma = vwap.sigma if vwap.sigma > 0 else abs(vwap.band_p1 - vwap.vwap)
    tol = max(abs(price) * 1e-4, frac * sigma if sigma else abs(price) * 0.001)
    levels = [
        ("plus_1_sigma", vwap.band_p1),
        ("plus_2_sigma", vwap.band_p2),
        ("minus_1_sigma", vwap.band_m1),
        ("minus_2_sigma", vwap.band_m2),
    ]
    if include_3s:
        levels.extend(
            [
                ("plus_3_sigma", vwap.band_p3),
                ("minus_3_sigma", vwap.band_m3),
            ]
        )
    for name, level in levels:
        if abs(price - level) <= tol:
            return name
    return None


def session_band_extreme(price: float, vwap: VWAPValues, *, frac: float = 0.25) -> str | None:
    """Setup 4: tag ±2σ or ±3σ on Phase 1 session VWAP (flat ``band_*`` fields)."""
    tagged = band_tagged(price, vwap, frac=frac, include_3s=True)
    if tagged in {"plus_2_sigma", "plus_3_sigma", "minus_2_sigma", "minus_3_sigma"}:
        return tagged
    return None


def atr_regime(atr_val: float | None, price: float, *, high_frac: float) -> str:
    """Simple ATR regime switch: ``high`` when ATR/price ≥ ``high_frac``, else ``normal``."""
    if not atr_val or price <= 0:
        return "normal"
    return "high" if (atr_val / price) >= high_frac else "normal"


async def list_avwaps(store: StateStore, symbol: str) -> list[AnchoredVWAP]:
    """Read Phase 2 nested-band AVWAP payloads from ``avwap:{symbol}:{anchor_id}``.

    Do **not** interpret Phase 1 flat ``band_p1`` / ``band_m1`` on these keys.
    """
    symbol = normalize_symbol(symbol)
    out: list[AnchoredVWAP] = []
    seen: set[str] = set()
    for anchor_id in await index_ids(store, symbol):
        parsed = _parse(AnchoredVWAP, await store.get(redis_avwap_key(symbol, anchor_id)))
        if parsed is None or parsed.anchor_id in seen:
            continue
        seen.add(parsed.anchor_id)
        out.append(parsed)
    latest = await get_latest_avwap(store, symbol)
    if latest is not None and latest.anchor_id not in seen:
        out.append(latest)
    return out


def _tf_name(value) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


async def get_htf_obs(
    store: StateStore,
    symbol: str,
    *,
    timeframes: tuple[str, ...] = ("1h", "4h"),
) -> list[OrderBlock]:
    """HTF order blocks (4H / 1H). Daily is a wide 4H swing proxy — no Daily TF on the wire."""
    allowed = set(timeframes)
    out: list[OrderBlock] = []
    for ob in await get_active_obs(store, symbol):
        name = _tf_name(ob.timeframe)
        if name is None:
            continue
        if name in allowed:
            out.append(ob)
    return out


def kill_zone_active(zone: KillZoneEvent | None, *, ts_ms: int | None = None) -> bool:
    if zone is None or not zone.active:
        return False
    if ts_ms is None:
        return True
    return zone.start_time <= ts_ms <= zone.end_time
