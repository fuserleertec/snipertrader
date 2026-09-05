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
