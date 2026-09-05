"""End-to-end tick pipeline: normalize → Kafka → OHLCV / session / VWAP / Phase 2."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from typing import Any

from sniper_data.avwap import (
    AnchoredVWAPEngine,
    persist_avwap,
    register_anchor,
    sync_anchors_from_store,
)
from sniper_data.bus.kafka import EventBus, InMemoryBus, KafkaBus, consume_topic, wait_for_kafka
from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore, StateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore, OHLCVStore, TimescaleStore
from sniper_data.config import Settings, get_settings
from sniper_data.connectors.mock import MockConnector
from sniper_data.kill_zones import KillZoneScheduler, apply_killzone_tick
from sniper_data.metrics import (
    record_avwap,
    record_tick,
    record_volume_profile,
    start_metrics_server,
)
from sniper_data.models import AnchorRegistration, RawTick
from sniper_data.ohlcv import OHLCVAggregator, redis_ohlcv_channel
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.sessions import SessionTracker, redis_session_channel, redis_session_key
from sniper_data.swings import SwingDetector
from sniper_data.volume_profile import VolumeProfileEngine, redis_volume_profile_key
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
        self.avwap = AnchoredVWAPEngine(max_anchors_per_symbol=self.settings.max_anchors_per_symbol)
        self.profiles = VolumeProfileEngine()
        self.swings = SwingDetector(
            left=self.settings.swing_left,
            right=self.settings.swing_right,
        )
        self.patterns = PatternEngine(
            self.store,
            self.bus,
            ttl_seconds=self.settings.fvg_ttl_clamped,
            swing_lookback=self.settings.swing_lookback,
        )
        self.killzones = KillZoneScheduler(self.settings.symbols)
        self.ticks_processed = 0
        self.bars_closed = 0
        self.ticks_by_class: dict[str, int] = {}
        self._stop = asyncio.Event()
        self._anchor_sync_seen: set[str] = set()

    async def start(self) -> None:
        if isinstance(self.bus, KafkaBus):
            await wait_for_kafka(self.settings.kafka_bootstrap)
        await self.bus.start()
        if isinstance(self.bars, TimescaleStore):
            await self.bars.start()
        start_metrics_server(self.settings.metrics_port)
        if isinstance(self.bus, InMemoryBus):
            self.bus.subscribe("anchor_events", self._on_anchor_event)
        log.info("runtime ready (inmemory=%s)", isinstance(self.bus, InMemoryBus))

    async def _on_anchor_event(self, payload: dict) -> None:
        try:
            req = AnchorRegistration.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("anchor_events rejected: %s", exc)
            return
        await register_anchor(self.avwap, self.store, req)

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

        if tick.symbol not in self._anchor_sync_seen:
            await sync_anchors_from_store(self.avwap, self.store, tick.symbol)
            self._anchor_sync_seen.add(tick.symbol)
        else:
            # Cheap refresh so HTTP-registered anchors appear without restart.
            await sync_anchors_from_store(self.avwap, self.store, tick.symbol)

        if self.settings.swing_detect:
            for req in self.swings.on_tick(
                tick.symbol, tick.price, tick.volume, tick.ts_ms, tick.asset_class
            ):
                meta = await register_anchor(self.avwap, self.store, req)
                await self.bus.publish(
                    "anchor_events",
                    req.model_copy(update={"anchor_id": meta.anchor_id}).model_dump(mode="json"),
                    key=tick.symbol,
                )

        t0 = time.perf_counter()
        avwaps = self.avwap.on_tick(
            tick.symbol, tick.price, tick.volume, tick.ts_ms, tick.asset_class
        )
        for snap in avwaps:
            await persist_avwap(self.store, snap, self.avwap.acc_payload(snap.symbol, snap.anchor_id))
        record_avwap(len(avwaps), tick.asset_class, time.perf_counter() - t0)

        t1 = time.perf_counter()
        profiles = self.profiles.on_tick(
            tick.symbol, tick.price, tick.volume, tick.ts_ms, tick.asset_class
        )
        for prof in profiles:
            await self.store.set(redis_volume_profile_key(prof.symbol, prof.session_type), prof)
            await self.store.publish(f"volume_profile:{prof.symbol}", prof)
        record_volume_profile(
            [p.session_type.value for p in profiles],
            time.perf_counter() - t1,
        )

        await self.patterns.on_tick(tick)
        if levels is not None:
            await self.patterns.on_session(levels)
        for snap in snapshots:
            await self.patterns.on_vwap(snap)
        pattern_batches = []
        for bar in closed:
            pattern_batches.append(await self.patterns.on_bar(bar))

        self.ticks_processed += 1
        klass_name = tick.asset_class.value
        self.ticks_by_class[klass_name] = self.ticks_by_class.get(klass_name, 0) + 1
        record_tick(tick.asset_class)
        return {
            "tick": tick,
            "bars": closed,
            "session": levels,
            "vwap": snapshots,
            "avwap": avwaps,
            "volume_profile": profiles,
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
        kz_task = None
        if self.settings.killzone_inprocess:
            kz_task = asyncio.create_task(self._killzone_loop())
        kafka_anchor_task = None
        if isinstance(self.bus, KafkaBus):
            kafka_anchor_task = asyncio.create_task(self._consume_anchor_events())
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
                        "processed %s ticks, closed %s bars, classes=%s",
                        self.ticks_processed,
                        self.bars_closed,
                        self.ticks_by_class,
                    )
        finally:
            self._stop.set()
            evict_task.cancel()
            if kz_task is not None:
                kz_task.cancel()
            if kafka_anchor_task is not None:
                kafka_anchor_task.cancel()
            await connector.close()

    async def _killzone_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await apply_killzone_tick(self.bus, self.store, self.killzones)
            except Exception as exc:  # noqa: BLE001
                log.warning("kill zone: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.killzone_poll_s)
            except asyncio.TimeoutError:
                continue

    async def _consume_anchor_events(self) -> None:
        try:
            async for payload in consume_topic(
                self.settings.kafka_bootstrap,
                "anchor_events",
                group_id="sniper-avwap-anchors",
            ):
                if self._stop.is_set():
                    break
                await self._on_anchor_event(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("anchor_events consumer: %s", exc)


async def run_pattern_replay() -> dict[str, Any]:
    """Feed locked ICT fixtures through in-memory stores (no Docker / brokers)."""
    from sniper_data.pattern_detection.fixtures import (
        buy_side_sweep_sequence,
        fvg_create_and_fill,
        london_session,
        mss_after_sell_sweep_bars,
        order_block_displacement,
        sell_side_sweep_sequence,
        swing_high_sequence,
        swing_low_sequence,
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

    async def _swings(engine: PatternEngine) -> None:
        for b in swing_high_sequence(lookback=2):
            await engine.on_bar(b)
        for b in swing_low_sequence(lookback=2):
            await engine.on_bar(b)

    await _run("sweep", _sweeps)
    await _run("fvg", _fvg)
    await _run("order_block", _ob)
    await _run("mss", _mss)
    await _run("swings", _swings)
    return {
        "stats": stats,
        "topics": {t: [r["value"] for r in bus.topics[t]] for t in bus.topics},
        "redis_keys": sorted(store.data),
    }


async def run_anchor_wiring_demo() -> dict[str, Any]:
    """In-memory swing → ``anchor_events`` → DE AVWAP Redis key → ML read-back."""
    from sniper_data.avwap import persist_avwap, register_anchor
    from sniper_data.models import AssetClass
    from sniper_data.pattern_detection.anchors import ANCHOR_TOPIC, to_anchor_payload
    from sniper_data.pattern_detection.context import get_avwap, get_kill_zone, get_volume_profile
    from sniper_data.pattern_detection.fixtures import SYM, swing_high_sequence

    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus, swing_lookback=2)
    avwap = AnchoredVWAPEngine()

    async def _on_anchor(payload: dict) -> None:
        req = AnchorRegistration.model_validate(payload)
        await register_anchor(avwap, store, req)

    bus.subscribe(ANCHOR_TOPIC, _on_anchor)

    for b in swing_high_sequence(lookback=2):
        await engine.on_bar(b)

    events = [r["value"] for r in bus.topics[ANCHOR_TOPIC]]
    if not events:
        raise RuntimeError("swing high fixture did not publish anchor_events")
    first = events[0]
    to_anchor_payload(AnchorRegistration.model_validate(first))

    # Simulate DE ticks after the swing so AVWAP has observations.
    last_bar = swing_high_sequence(lookback=2)[-1]
    ts = last_bar.close_ts_ms
    for i, (px, vol) in enumerate(((118.0, 10.0), (119.0, 20.0), (117.5, 30.0))):
        snaps = avwap.on_tick(SYM, px, vol, ts + i + 1, AssetClass.CRYPTO)
        for snap in snaps:
            await persist_avwap(store, snap, avwap.acc_payload(snap.symbol, snap.anchor_id))

    read = await get_avwap(store, SYM, first["anchor_id"])
    if read is None:
        raise RuntimeError("AVWAP Redis key missing after mock DE compute")

    return {
        "anchor_event": first,
        "avwap": read.model_dump(mode="json"),
        "volume_profile": await get_volume_profile(store, SYM, "ny_am"),
        "kill_zone": await get_kill_zone(store, SYM),
        "stats": engine.snapshot(),
    }


async def run_setup_replay() -> dict[str, Any]:
    from sniper_data.setup_detection.replay import run_setup_replay as _replay

    return await _replay()


async def run_setup_loop(*, inmemory: bool = False, duration_s: float | None = None) -> dict[str, Any]:
    """Live consumer: DE topics → setups 1–6 → risk → ``setup_signals``."""
    from sniper_data.setup_detection.orchestrator import SetupOrchestrator, subscribe_inmemory
    from sniper_data.setup_detection.risk_client import HttpRiskClient

    settings = get_settings()
    bus: EventBus = InMemoryBus() if inmemory else KafkaBus(settings.kafka_bootstrap)
    store: StateStore = InMemoryStateStore() if inmemory else RedisStateStore(settings.redis_url)
    risk = HttpRiskClient(settings.risk_validate_url)
    orch = SetupOrchestrator(store, bus, risk, swing_lookback=settings.swing_lookback)
    await bus.start()
    if inmemory:
        subscribe_inmemory(bus, orch)
        if duration_s:
            await asyncio.sleep(duration_s)
        await bus.stop()
        await store.close()
        return orch.stats.as_dict()

    await wait_for_kafka(settings.kafka_bootstrap)
    stop = asyncio.Event()

    async def _consume(topic: str, handler) -> None:
        try:
            async for payload in consume_topic(settings.kafka_bootstrap, topic, group_id=f"sniper-setups-{topic}"):
                if stop.is_set():
                    break
                await handler(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("setup consumer %s: %s", topic, exc)

    from sniper_data.models import (
        FVGZone,
        KillZoneEvent,
        MssEvent,
        OHLCVBar,
        OrderBlock,
        SessionLevels,
        SweepEvent,
        VWAPValues,
    )

    tasks = [
        asyncio.create_task(_consume("sweep_events", lambda p: _sync(orch.on_sweep, SweepEvent.model_validate(p)))),
        asyncio.create_task(_consume("mss_events", lambda p: _sync(orch.on_mss, MssEvent.model_validate(p)))),
        asyncio.create_task(_consume("fvg_zones", lambda p: _sync(orch.on_fvg, FVGZone.model_validate(p)))),
        asyncio.create_task(_consume("order_block_zones", lambda p: _sync(orch.on_ob, OrderBlock.model_validate(p)))),
        asyncio.create_task(_consume("ohlcv_bars", lambda p: orch.on_bar(OHLCVBar.model_validate(p)))),
        asyncio.create_task(_consume("session_levels", lambda p: _sync(orch.on_session, SessionLevels.model_validate(p)))),
        asyncio.create_task(_consume("vwap_values", lambda p: _sync(orch.on_vwap, VWAPValues.model_validate(p)))),
        asyncio.create_task(_consume("kill_zone_events", lambda p: _sync(orch.on_kill_zone, KillZoneEvent.model_validate(p)))),
        asyncio.create_task(_consume("anchor_events", lambda p: _sync(orch.setup6.on_anchor, p))),
    ]
    try:
        if duration_s is not None:
            await asyncio.sleep(duration_s)
        else:
            await asyncio.gather(*tasks)
    finally:
        stop.set()
        for t in tasks:
            t.cancel()
        await bus.stop()
        await store.close()
    return orch.stats.as_dict()


async def _sync(fn, value) -> None:
    fn(value)


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
