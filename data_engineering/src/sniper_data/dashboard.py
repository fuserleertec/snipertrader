"""15-minute dashboard snapshot publisher (paper-only).

Keeps real-time WS as-is. Every ``DASHBOARD_SNAPSHOT_INTERVAL_S`` (default
900) writes:

* Redis ``dashboard:snapshot:{symbol}`` — pointers + embedded Phase 1/2
  payloads (or null) for VWAP / session / AVWAP / kill zone / volume profile
* Redis ``dashboard:snapshot:index`` — universe pointer map
* Redis ``universe:active`` — locked top-N ranking (GET /v1/universe/top)
* Redis ``universe:config`` — full configured list (helper)
* Kafka ``dashboard_snapshots`` — one message per symbol (key = symbol)
  plus an index frame (key = ``_index``)

Frontend ranking polls these keys on a ≤15m cadence. No ranking UI fields
beyond the locked universe-top envelope.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from typing import Any

from pydantic import BaseModel, Field

from sniper_data.avwap import redis_avwap_latest_key
from sniper_data.bus.kafka import EventBus, InMemoryBus, KafkaBus, wait_for_kafka
from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore, StateStore
from sniper_data.config import Settings, get_settings
from sniper_data.kill_zones import redis_kill_zone_key
from sniper_data.models import AssetClass
from sniper_data.sessions import dt_from_ms, primary_session, redis_session_key
from sniper_data.symbols import infer_asset_class, normalize_symbol
from sniper_data.universe import (
    MAX_UNIVERSE_SYMBOLS,
    REDIS_UNIVERSE_ACTIVE,
    UniverseTop,
    top_envelope,
    write_universe_active,
    write_universe_config,
)
from sniper_data.volume_profile import redis_volume_profile_key
from sniper_data.vwap import redis_vwap_key
from sniper_data.zones import fvg_key, mss_key, ob_key, sweep_key

log = logging.getLogger(__name__)

DASHBOARD_SNAPSHOT_TOPIC = "dashboard_snapshots"
REDIS_SNAPSHOT_PREFIX = "dashboard:snapshot:"
REDIS_SNAPSHOT_INDEX = "dashboard:snapshot:index"


class SnapshotPointers(BaseModel):
    vwap: str
    session: str
    avwap_latest: str
    kill_zone: str
    volume_profile: str


class SnapshotAvailable(BaseModel):
    vwap: bool
    session: bool
    avwap: bool
    kill_zone: bool
    volume_profile: bool


class DashboardSnapshot(BaseModel):
    """Per-symbol 15m snapshot. Embedded objects match Phase 1/2 wire shapes."""

    schema_version: str = "1.1"
    symbol: str
    asset_class: AssetClass
    ts_ms: int
    cadence_s: int = 900
    live_trading: bool = False
    price: float | None = None
    pointers: SnapshotPointers
    available: SnapshotAvailable
    vwap: dict[str, Any] | None = None
    session: dict[str, Any] | None = None
    avwap: dict[str, Any] | None = None
    kill_zone: dict[str, Any] | None = None
    volume_profile: dict[str, Any] | None = None


class SnapshotIndex(BaseModel):
    schema_version: str = "1.1"
    ts_ms: int
    cadence_s: int = 900
    live_trading: bool = False
    max_symbols: int = MAX_UNIVERSE_SYMBOLS
    count: int
    symbols: list[str] = Field(default_factory=list)
    keys: dict[str, str] = Field(default_factory=dict)
    universe_active_key: str = REDIS_UNIVERSE_ACTIVE


def redis_snapshot_key(symbol: str) -> str:
    return f"{REDIS_SNAPSHOT_PREFIX}{normalize_symbol(symbol)}"


def _as_dict(raw: Any) -> dict[str, Any] | None:
    return raw if isinstance(raw, dict) else None


def _price_from(session: dict | None, vwap: dict | None, avwap: dict | None) -> float | None:
    if session and session.get("close") is not None:
        return float(session["close"])
    if vwap and vwap.get("vwap") is not None:
        return float(vwap["vwap"])
    if avwap and avwap.get("vwap_value") is not None:
        return float(avwap["vwap_value"])
    return None


def _volatility(vwap: dict | None, session: dict | None) -> float:
    if vwap and vwap.get("vwap") and vwap.get("sigma") is not None:
        mid = float(vwap["vwap"])
        if mid > 0:
            return abs(float(vwap["sigma"])) / mid
    if session:
        high = float(session.get("high") or 0)
        low = float(session.get("low") or 0)
        close = float(session.get("close") or 0)
        if close > 0 and high >= low:
            return (high - low) / close
    return 0.0


async def _count_patterns(store: StateStore, symbol: str) -> int:
    n = 0
    for prefix in ("sweep", "fvg", "mss", "ob", "setup"):
        if prefix == "setup":
            keys = await store.scan(f"setup:{symbol}:*")
            n += len([k for k in keys if not k.startswith("setup:index:")])
        else:
            keys = await store.scan(f"{prefix}:{symbol}:*")
            n += len(keys)
    return n


async def collect_symbol_state(
    store: StateStore,
    symbol: str,
    *,
    now_ms: int | None = None,
    cadence_s: int = 900,
) -> tuple[DashboardSnapshot, dict[str, Any]]:
    symbol = normalize_symbol(symbol)
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    klass = infer_asset_class(symbol)
    window = primary_session(klass, dt_from_ms(now))
    session_type = window.session_type.value if window is not None else (
        "london" if klass is AssetClass.CRYPTO else "rth"
    )
    vwap_key = redis_vwap_key(symbol, "session")
    session_key = redis_session_key(symbol, session_type)
    avwap_key = redis_avwap_latest_key(symbol)
    kz_key = redis_kill_zone_key(symbol)
    vp_key = redis_volume_profile_key(symbol, session_type)

    vwap = _as_dict(await store.get(vwap_key))
    if vwap is None:
        vwap = _as_dict(await store.get(redis_vwap_key(symbol, "weekly")))
        if vwap is not None:
            vwap_key = redis_vwap_key(symbol, "weekly")
    session = _as_dict(await store.get(session_key))
    if session is None:
        session_keys = await store.scan(f"session:{symbol}:*")
        if session_keys:
            session_key = sorted(session_keys)[0]
            session = _as_dict(await store.get(session_key))
    avwap = _as_dict(await store.get(avwap_key))
    kill_zone = _as_dict(await store.get(kz_key))
    volume_profile = _as_dict(await store.get(vp_key))
    if volume_profile is None:
        vp_keys = [
            k
            for k in await store.scan(f"volume_profile:{symbol}:*")
            if not k.startswith("volume_profile:acc:")
        ]
        if vp_keys:
            vp_key = sorted(vp_keys)[0]
            volume_profile = _as_dict(await store.get(vp_key))

    available = SnapshotAvailable(
        vwap=vwap is not None,
        session=session is not None,
        avwap=avwap is not None,
        kill_zone=kill_zone is not None,
        volume_profile=volume_profile is not None,
    )
    snap = DashboardSnapshot(
        symbol=symbol,
        asset_class=klass,
        ts_ms=now,
        cadence_s=int(cadence_s),
        live_trading=False,
        price=_price_from(session, vwap, avwap),
        pointers=SnapshotPointers(
            vwap=vwap_key,
            session=session_key,
            avwap_latest=avwap_key,
            kill_zone=kz_key,
            volume_profile=vp_key,
        ),
        available=available,
        vwap=vwap,
        session=session,
        avwap=avwap,
        kill_zone=kill_zone,
        volume_profile=volume_profile,
    )
    pattern_count = await _count_patterns(store, symbol)
    metrics = {
        "symbol": symbol,
        "asset_class": klass.value,
        "volume": float((session or {}).get("volume") or (vwap or {}).get("cum_volume") or 0.0),
        "volatility": _volatility(vwap, session),
        "session_active": bool(
            (kill_zone or {}).get("active") or available.session
        ),
        "levels_available": sum(
            1
            for flag in (
                available.vwap,
                available.session,
                available.avwap,
                available.kill_zone,
                available.volume_profile,
            )
            if flag
        ),
        "pattern_count": pattern_count,
    }
    return snap, metrics


async def publish_snapshots(
    store: StateStore,
    symbols: list[str],
    *,
    bus: EventBus | None = None,
    now_ms: int | None = None,
    cadence_s: int = 900,
) -> dict[str, Any]:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    symbols = [normalize_symbol(s) for s in symbols][:MAX_UNIVERSE_SYMBOLS]
    snaps: list[DashboardSnapshot] = []
    metrics: list[dict[str, Any]] = []
    keys: dict[str, str] = {}
    for symbol in symbols:
        snap, row = await collect_symbol_state(
            store, symbol, now_ms=now, cadence_s=cadence_s
        )
        body = snap.model_dump(mode="json")
        key = redis_snapshot_key(symbol)
        await store.set(key, body)
        keys[symbol] = key
        snaps.append(snap)
        metrics.append(row)
        if bus is not None:
            await bus.publish(DASHBOARD_SNAPSHOT_TOPIC, body, key=symbol)

    index = SnapshotIndex(
        ts_ms=now,
        cadence_s=int(cadence_s),
        live_trading=False,
        count=len(symbols),
        symbols=symbols,
        keys=keys,
    )
    index_body = index.model_dump(mode="json")
    await store.set(REDIS_SNAPSHOT_INDEX, index_body)
    await write_universe_config(store, symbols, cadence_s=cadence_s)
    ranking = top_envelope(metrics, limit=MAX_UNIVERSE_SYMBOLS, now_ms=now)
    await write_universe_active(store, ranking)
    if bus is not None:
        await bus.publish(DASHBOARD_SNAPSHOT_TOPIC, index_body, key="_index")
        await bus.publish(DASHBOARD_SNAPSHOT_TOPIC, ranking.model_dump(mode="json"), key="_universe")
    return {
        "ts_ms": now,
        "symbols": symbols,
        "snapshots": [s.model_dump(mode="json") for s in snaps],
        "index": index_body,
        "universe_active": ranking.model_dump(mode="json"),
        "live_trading": False,
    }


async def refresh_paper_state(
    store: StateStore,
    symbols: list[str],
    *,
    bus: EventBus | None = None,
    bars=None,
    now_ms: int | None = None,
    cadence_s: int = 900,
    seed_history: bool = True,
    seed_patterns: bool = True,
) -> dict[str, Any]:
    """One 15m cycle: optional history/pattern refresh + snapshot + ranking."""
    from sniper_data.history import seed_ohlcv_history
    from sniper_data.patterns import seed_patterns as _seed_patterns

    if seed_history and bars is not None:
        await seed_ohlcv_history(bars, symbols, now_ms=now_ms)
    if seed_patterns:
        await _seed_patterns(store, symbols, bus=bus, now_ms=now_ms)
    return await publish_snapshots(
        store, symbols, bus=bus, now_ms=now_ms, cadence_s=cadence_s
    )


async def run_snapshot_loop(
    *,
    settings: Settings | None = None,
    bus: EventBus | None = None,
    store: StateStore | None = None,
    bars=None,
    inmemory: bool | None = None,
    interval_s: float | None = None,
    duration_s: float | None = None,
    once: bool = False,
) -> dict[str, Any]:
    settings = settings or get_settings()
    use_mem = settings.use_inmemory if inmemory is None else inmemory
    bus = bus or (InMemoryBus() if use_mem else KafkaBus(settings.kafka_bootstrap, client_id="sniper-snapshot"))
    store = store or (
        InMemoryStateStore() if use_mem else RedisStateStore(settings.redis_url)
    )
    interval = (
        float(interval_s)
        if interval_s is not None
        else float(settings.dashboard_snapshot_interval_s)
    )
    if isinstance(bus, KafkaBus):
        await wait_for_kafka(settings.kafka_bootstrap)
    await bus.start()

    from sniper_data.bus.timescaledb import InMemoryOHLCVStore, TimescaleStore
    from sniper_data.metrics import start_metrics_server

    if bars is None:
        bars = InMemoryOHLCVStore() if use_mem else TimescaleStore(settings.database_url)
        if isinstance(bars, TimescaleStore):
            try:
                await bars.start()
            except Exception as exc:  # noqa: BLE001
                log.warning("snapshot OHLCV store unavailable: %s", exc)
                bars = None
    start_metrics_server(settings.metrics_port)

    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    last: dict[str, Any] = {}
    started = loop.time()
    try:
        while not stop.is_set():
            try:
                last = await refresh_paper_state(
                    store,
                    settings.symbols,
                    bus=bus,
                    bars=bars,
                    cadence_s=int(interval),
                    seed_history=settings.seed_history,
                    seed_patterns=settings.seed_patterns,
                )
                log.info(
                    "dashboard snapshot symbols=%s live_trading=false cadence_s=%s",
                    last.get("symbols"),
                    int(interval),
                )
            except Exception:  # noqa: BLE001
                log.exception("dashboard snapshot failed")
            if once:
                break
            if duration_s is not None and (loop.time() - started) >= duration_s:
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    finally:
        await bus.stop()
        await store.close()
        if bars is not None:
            await bars.close()
    return last


# Referenced by schema docs / tests — keep names importable.
_ = (sweep_key, fvg_key, mss_key, ob_key, UniverseTop)
