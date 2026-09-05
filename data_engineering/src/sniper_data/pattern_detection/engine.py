"""Orchestrate sweep / FVG / MSS / order-block detectors against landed DE contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sniper_data.bus.kafka import EventBus
from sniper_data.bus.redis_store import StateStore
from sniper_data.models import (
    FVGZone,
    MssEvent,
    OHLCVBar,
    OrderBlock,
    RawTick,
    SessionLevels,
    SweepEvent,
    VWAPValues,
)
from sniper_data.pattern_detection.fvg import FVGDetector
from sniper_data.pattern_detection.mss import DEFAULT_SWING_LOOKBACK, MSSDetector
from sniper_data.pattern_detection.order_block import OrderBlockDetector
from sniper_data.pattern_detection.sweep import SweepDetector
from sniper_data.pattern_detection.validate import validate_topic
from sniper_data.zones import clamp_ttl, store_fvg, store_mss, store_ob, store_sweep


@dataclass
class PatternStats:
    sweeps: int = 0
    fvgs: int = 0
    mss: int = 0
    order_blocks: int = 0
    mitigations: int = 0
    confirmed_sweeps: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "sweeps": self.sweeps,
            "fvgs": self.fvgs,
            "mss": self.mss,
            "order_blocks": self.order_blocks,
            "mitigations": self.mitigations,
            "confirmed_sweeps": self.confirmed_sweeps,
        }


@dataclass
class PatternBatch:
    sweeps: list[SweepEvent] = field(default_factory=list)
    fvgs: list[FVGZone] = field(default_factory=list)
    mss: list[MssEvent] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)


class PatternEngine:
    def __init__(
        self,
        store: StateStore,
        bus: EventBus,
        *,
        ttl_seconds: int | None = None,
        swing_lookback: int = DEFAULT_SWING_LOOKBACK,
    ) -> None:
        self.store = store
        self.bus = bus
        self.ttl = clamp_ttl(ttl_seconds)
        self.sweep = SweepDetector(store)
        self.fvg = FVGDetector()
        self.mss = MSSDetector(lookback=swing_lookback)
        self.order_block = OrderBlockDetector()
        self.stats = PatternStats()
        self.last_vwap: dict[tuple[str, str], VWAPValues] = {}

    async def on_tick(self, tick: RawTick) -> None:
        self.sweep.on_tick(tick)

    async def on_session(self, levels: SessionLevels) -> None:
        self.sweep.on_session(levels)

    async def on_vwap(self, snap: VWAPValues) -> None:
        anchor = snap.anchor_type.value if hasattr(snap.anchor_type, "value") else str(snap.anchor_type)
        self.last_vwap[(snap.symbol, anchor)] = snap

    async def on_bar(self, bar: OHLCVBar) -> PatternBatch:
        batch = PatternBatch()

        for event in await self.sweep.on_bar(bar):
            await self._emit_sweep(event)
            batch.sweeps.append(event)
            if event.confirmed:
                self.stats.confirmed_sweeps += 1
            else:
                self.stats.sweeps += 1
                self.mss.on_sweep(event)

        for zone in self.fvg.on_bar(bar):
            await self._emit_fvg(zone)
            batch.fvgs.append(zone)
            if zone.mitigated:
                self.stats.mitigations += 1
            else:
                self.stats.fvgs += 1

        for event in self.mss.on_bar(bar):
            await self._emit_mss(event)
            batch.mss.append(event)
            self.stats.mss += 1

        for zone in self.order_block.on_bar(bar):
            await self._emit_ob(zone)
            batch.order_blocks.append(zone)
            if zone.mitigated:
                self.stats.mitigations += 1
            else:
                self.stats.order_blocks += 1

        return batch

    async def _emit_sweep(self, event: SweepEvent) -> None:
        payload = validate_topic("sweep_events", event)
        await store_sweep(self.store, event, ttl_seconds=self.ttl)
        await self.bus.publish("sweep_events", payload, key=event.symbol)

    async def _emit_fvg(self, zone: FVGZone) -> None:
        zoned = zone.model_copy(update={"ttl_seconds": self.ttl})
        payload = validate_topic("fvg_zones", zoned)
        await store_fvg(self.store, zoned, ttl_seconds=self.ttl)
        await self.bus.publish("fvg_zones", payload, key=zone.symbol)

    async def _emit_mss(self, event: MssEvent) -> None:
        payload = validate_topic("mss_events", event)
        await store_mss(self.store, event, ttl_seconds=self.ttl)
        await self.bus.publish("mss_events", payload, key=event.symbol)

    async def _emit_ob(self, zone: OrderBlock) -> None:
        zoned = zone.model_copy(update={"ttl_seconds": self.ttl})
        payload = validate_topic("order_block_zones", zoned)
        await store_ob(self.store, zoned, ttl_seconds=self.ttl)
        await self.bus.publish("order_block_zones", payload, key=zone.symbol)

    def snapshot(self) -> dict[str, Any]:
        return self.stats.as_dict()
