"""End-to-end tick pipeline: normalize → Kafka → OHLCV / session / VWAP."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from sniper_data.bus.kafka import EventBus, InMemoryBus, KafkaBus, wait_for_kafka
from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore, StateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore, OHLCVStore, TimescaleStore
from sniper_data.config import Settings, get_settings
from sniper_data.connectors.mock import MockConnector
from sniper_data.models import RawTick
from sniper_data.ohlcv import OHLCVAggregator, redis_ohlcv_channel
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.sessions import SessionTracker, redis_session_channel, redis_session_key
from sniper_data.vwap import VWAPEngine, redis_vwap_key
from sniper_data.zones import evict_expired_zones

log = logging.getLogger(__name__)


class Runtime:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        bus: EventBus | None = None,
        store: StateStore | None = None,
        bars: OHLCVStore | None = None,
        inmemory: bool | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        use_mem = self.settings.use_inmemory if inmemory is None else inmemory
        self.bus: EventBus = bus or (InMemoryBus() if use_mem else KafkaBus(self.settings.kafka_bootstrap))
        self.store: StateStore = store or (
            InMemoryStateStore() if use_mem else RedisStateStore(self.settings.redis_url)
        )
        self.bars: OHLCVStore = bars or (
            InMemoryOHLCVStore() if use_mem else TimescaleStore(self.settings.database_url)
        )
        self.aggregator = OHLCVAggregator()
        self.sessions = SessionTracker()
        self.vwap = VWAPEngine(rolling_periods=self.settings.rolling_vwap_periods)
        self.patterns = PatternEngine(
            self.store,
            self.bus,
            ttl_seconds=self.settings.fvg_ttl_clamped,
            swing_lookback=self.settings.swing_lookback,
        )
        self.ticks_processed = 0
        self.bars_closed = 0
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if isinstance(self.bus, KafkaBus):
            await wait_for_kafka(self.settings.kafka_bootstrap)
        await self.bus.start()
        if isinstance(self.bars, TimescaleStore):
            await self.bars.start()
        log.info("runtime ready (inmemory=%s)", isinstance(self.bus, InMemoryBus))

    async def stop(self) -> None:
        self._stop.set()
        await self.bus.stop()
        await self.store.close()
        await self.bars.close()

    async def handle_tick(self, tick: RawTick) -> dict[str, Any]:
        await self.bus.publish("raw_ticks", tick, key=tick.symbol)
        closed = self.aggregator.on_tick(tick)
        for bar in closed:
            await self.bars.upsert(bar)
            await self.store.publish(redis_ohlcv_channel(bar.symbol, bar.timeframe), bar)
            await self.bus.publish("ohlcv_bars", bar, key=tick.symbol)
            self.bars_closed += 1

        levels = self.sessions.on_tick(
            tick.symbol, tick.price, tick.volume, tick.ts_ms, tick.asset_class
        )
        if levels is not None:
            await self.store.set(redis_session_key(levels.symbol, levels.session_type), levels)
            await self.store.publish(redis_session_channel(levels.symbol), levels)
            await self.bus.publish("session_levels", levels, key=tick.symbol)

        snapshots = self.vwap.on_tick(
            tick.symbol, tick.price, tick.volume, tick.ts_ms, tick.asset_class
        )
        for snap in snapshots:
            await self.store.set(redis_vwap_key(snap.symbol, snap.anchor_type), snap)
            await self.store.publish(f"vwap:{snap.symbol}", snap)
            await self.bus.publish("vwap_values", snap, key=tick.symbol)

        await self.patterns.on_tick(tick)
        if levels is not None:
            await self.patterns.on_session(levels)
        for snap in snapshots:
            await self.patterns.on_vwap(snap)
        pattern_batches = []
        for bar in closed:
            pattern_batches.append(await self.patterns.on_bar(bar))

        self.ticks_processed += 1
        return {
            "tick": tick,
            "bars": closed,
            "session": levels,
            "vwap": snapshots,
            "patterns": pattern_batches,
        }

    async def run_demo(self, duration_s: float | None = None) -> None:
        connector = MockConnector(
            symbols=self.settings.symbols,
            interval_ms=self.settings.tick_interval_ms,
        )
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop.set)
            except NotImplementedError:
                pass

        async def _evict_loop() -> None:
            while not self._stop.is_set():
                try:
                    await evict_expired_zones(self.store)
                except Exception as exc:  # noqa: BLE001
                    log.warning("eviction: %s", exc)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=60.0)
                except asyncio.TimeoutError:
                    continue

        evict_task = asyncio.create_task(_evict_loop())
        started = loop.time()
        try:
            async for tick in connector.stream():
                try:
                    await self.handle_tick(tick)
                except Exception:
                    log.exception("tick failed")
                if duration_s is not None and (loop.time() - started) >= duration_s:
                    break
                if self._stop.is_set():
                    break
                if self.ticks_processed % 50 == 0:
                    log.info(
                        "processed %s ticks, closed %s bars, patterns %s",
                        self.ticks_processed,
                        self.bars_closed,
                        self.patterns.snapshot(),
                    )
        finally:
            self._stop.set()
            evict_task.cancel()
            await connector.close()


async def run_pattern_replay() -> dict[str, Any]:
    """Feed locked ICT fixtures through in-memory stores (no Docker / brokers)."""
    from sniper_data.bus.kafka import InMemoryBus
    from sniper_data.bus.redis_store import InMemoryStateStore
    from sniper_data.pattern_detection.engine import PatternEngine
    from sniper_data.pattern_detection.fixtures import (
        buy_side_sweep_sequence,
        fvg_create_and_fill,
        london_session,
        mss_after_sell_sweep_bars,
        order_block_displacement,
        sell_side_sweep_sequence,
    )

    bus = InMemoryBus()
    store = InMemoryStateStore()
    stats: dict[str, int] = {}

    async def _run(name: str, setup) -> None:
        engine = PatternEngine(store, bus, swing_lookback=2)
        await setup(engine)
        for key, value in engine.snapshot().items():
            stats[key] = stats.get(key, 0) + value
        log.info("replay %s → %s", name, engine.snapshot())

    async def _sweeps(engine: PatternEngine) -> None:
        engine.sweep.on_session(london_session())
        for b in sell_side_sweep_sequence(sweep_volume=0.01):
            await engine.on_bar(b)
        engine.sweep.on_session(london_session())
        for b in buy_side_sweep_sequence(sweep_volume=0.01):
            await engine.on_bar(b)

    async def _fvg(engine: PatternEngine) -> None:
        for b in fvg_create_and_fill():
            await engine.on_bar(b)

    async def _ob(engine: PatternEngine) -> None:
        for b in order_block_displacement():
            await engine.on_bar(b)

    async def _mss(engine: PatternEngine) -> None:
        sweep, bars = mss_after_sell_sweep_bars()
        engine.mss.on_sweep(sweep)
        for b in bars:
            await engine.on_bar(b)

    await _run("sweep", _sweeps)
    await _run("fvg", _fvg)
    await _run("order_block", _ob)
    await _run("mss", _mss)
    return {
        "stats": stats,
        "topics": {t: [r["value"] for r in bus.topics[t]] for t in bus.topics},
        "redis_keys": sorted(store.data),
    }


async def run_pipeline(*, inmemory: bool = False, duration_s: float | None = None) -> Runtime:
    logging.basicConfig(
        level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    get_settings.cache_clear()
    settings = get_settings()
    rt = Runtime(settings, inmemory=inmemory)
    await rt.start()
    try:
        await rt.run_demo(duration_s=duration_s)
    finally:
        if duration_s is not None:
            await rt.stop()
    return rt
