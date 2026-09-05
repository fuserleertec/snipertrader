"""Run setups 1–3 in parallel, dedupe, risk-filter, then publish."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any

from sniper_data.bus.kafka import EventBus
from sniper_data.bus.redis_store import StateStore
from sniper_data.metrics import (
    record_setup_approved,
    record_setup_candidate,
    record_setup_latency,
    record_setup_rejected,
)
from sniper_data.models import (
    FVGZone,
    KillZoneEvent,
    MssEvent,
    OHLCVBar,
    SessionLevels,
    SweepEvent,
    VWAPValues,
)
from sniper_data.pattern_detection.ids import make_id
from sniper_data.pattern_detection.validate import validate_topic
from sniper_data.setup_detection.candidate import SetupCandidate, to_risk_request, to_setup_signal
from sniper_data.setup_detection.risk_client import RiskClient, RiskDecision
from sniper_data.setup_detection.setup1 import SweepReclaimDetector
from sniper_data.setup_detection.setup2 import FVGEntryDetector
from sniper_data.setup_detection.setup3 import JudasDetector

log = logging.getLogger(__name__)

DEDUPE_WINDOW_MS = 5 * 60 * 1000
OVERLAPPING_TFS = frozenset({"1m", "5m", "15m"})
SETUP_SIGNALS_TOPIC = "setup_signals"


@dataclass
class OrchestratorStats:
    raw: int = 0
    approved: int = 0
    rejected: int = 0
    deduped: int = 0
    published: int = 0

    def as_dict(self) -> dict[str, Any]:
        decided = self.approved + self.rejected
        fp_rate = (self.rejected / decided) if decided else None
        return {
            "raw": self.raw,
            "approved": self.approved,
            "rejected": self.rejected,
            "deduped": self.deduped,
            "published": self.published,
            "false_positive_rate": fp_rate,
        }


@dataclass
class SetupOrchestrator:
    store: StateStore
    bus: EventBus
    risk: RiskClient
    swing_lookback: int = 5
    setup1: SweepReclaimDetector = field(init=False)
    setup2: FVGEntryDetector = field(init=False)
    setup3: JudasDetector = field(init=False)
    stats: OrchestratorStats = field(default_factory=OrchestratorStats)
    raw_log: list[dict[str, Any]] = field(default_factory=list)
    approved_log: list[dict[str, Any]] = field(default_factory=list)
    _recent: list[SetupCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.setup1 = SweepReclaimDetector(self.store, swing_lookback=self.swing_lookback)
        self.setup2 = FVGEntryDetector(self.store)
        self.setup3 = JudasDetector(self.store)

    def on_vwap(self, snap: VWAPValues) -> None:
        self.setup1.on_vwap(snap)
        self.setup2.on_vwap(snap)
        self.setup3.on_vwap(snap)

    def on_session(self, levels: SessionLevels) -> None:
        self.setup3.on_session(levels)

    def on_kill_zone(self, event: KillZoneEvent) -> None:
        self.setup3.on_kill_zone(event)

    def on_sweep(self, event: SweepEvent) -> None:
        self.setup1.on_sweep(event)
        self.setup3.on_sweep(event)

    def on_mss(self, event: MssEvent) -> None:
        self.setup1.on_mss(event)

    def on_fvg(self, zone: FVGZone) -> None:
        self.setup2.on_fvg(zone)

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        t0 = time.perf_counter()
        batches = await _gather_setups(
            self.setup1.on_bar(bar),
            self.setup2.on_bar(bar),
            self.setup3.on_bar(bar),
        )
        record_setup_latency("all", time.perf_counter() - t0)
        incoming = [c for batch in batches for c in batch]
        return await self.submit(incoming)

    async def submit(self, incoming: list[SetupCandidate]) -> list[SetupCandidate]:
        if not incoming:
            return []
        for cand in incoming:
            self.stats.raw += 1
            record_setup_candidate(cand.setup_type, cand.side)
            log.info("setup raw %s", cand.log_fields())
            self.raw_log.append(cand.log_fields())

        winners = self._dedupe_against_recent(incoming)
        published: list[SetupCandidate] = []
        for cand in winners:
            payload = to_risk_request(cand)
            decision = await self.risk.validate(payload)
            if not decision.approved:
                self.stats.rejected += 1
                record_setup_rejected(cand.setup_type, decision.reason)
                log.info(
                    "setup rejected %s reason=%s",
                    cand.log_fields(),
                    decision.reason,
                )
                continue
            signal_id = make_id("sig", cand.setup_type, cand.symbol, cand.timeframe, cand.ts_ms, cand.side)
            signal = to_setup_signal(cand, signal_id, position_size=decision.adjusted_position_size)
            wire = validate_topic(SETUP_SIGNALS_TOPIC, signal)
            await self.bus.publish(SETUP_SIGNALS_TOPIC, wire, key=cand.symbol)
            self.stats.approved += 1
            self.stats.published += 1
            record_setup_approved(cand.setup_type)
            log.info("setup approved %s id=%s", cand.log_fields(), signal_id)
            self.approved_log.append({**cand.log_fields(), "id": signal_id})
            self._recent.append(cand)
            published.append(cand)
        self._prune_recent(incoming[-1].ts_ms if incoming else 0)
        return published

    def _dedupe_against_recent(self, incoming: list[SetupCandidate]) -> list[SetupCandidate]:
        pool = [c for c in self._recent] + list(incoming)
        winners = dedupe_candidates(pool)
        winner_ids = {id(c) for c in winners}
        kept = [c for c in incoming if id(c) in winner_ids]
        dropped = len(incoming) - len(kept)
        self.stats.deduped += dropped
        return kept

    def _prune_recent(self, now_ms: int) -> None:
        self._recent = [c for c in self._recent if now_ms - c.ts_ms <= DEDUPE_WINDOW_MS]


def dedupe_candidates(candidates: list[SetupCandidate]) -> list[SetupCandidate]:
    """Same symbol + direction + overlapping TF within 5 minutes → highest conviction."""
    ordered = sorted(candidates, key=lambda c: (c.ts_ms, -c.conviction))
    kept: list[SetupCandidate] = []
    for cand in ordered:
        rival_idx = None
        for i, existing in enumerate(kept):
            if _conflicts(existing, cand):
                rival_idx = i
                break
        if rival_idx is None:
            kept.append(cand)
            continue
        rival = kept[rival_idx]
        if cand.conviction > rival.conviction:
            kept[rival_idx] = cand
    return kept


def _conflicts(a: SetupCandidate, b: SetupCandidate) -> bool:
    if a.symbol != b.symbol or a.side != b.side:
        return False
    if a.timeframe not in OVERLAPPING_TFS or b.timeframe not in OVERLAPPING_TFS:
        return False
    return abs(a.ts_ms - b.ts_ms) <= DEDUPE_WINDOW_MS


async def _gather_setups(*aws: Awaitable[list[SetupCandidate]]) -> list[list[SetupCandidate]]:
    import asyncio

    return list(await asyncio.gather(*aws))


def subscribe_inmemory(bus, orchestrator: SetupOrchestrator) -> None:
    """Wire InMemoryBus topic callbacks into the orchestrator."""

    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise TypeError("bus does not support in-process subscribe")

    async def _sweep(payload: dict) -> None:
        orchestrator.on_sweep(SweepEvent.model_validate(payload))

    async def _mss(payload: dict) -> None:
        orchestrator.on_mss(MssEvent.model_validate(payload))

    async def _fvg(payload: dict) -> None:
        orchestrator.on_fvg(FVGZone.model_validate(payload))

    async def _bar(payload: dict) -> None:
        await orchestrator.on_bar(OHLCVBar.model_validate(payload))

    async def _session(payload: dict) -> None:
        orchestrator.on_session(SessionLevels.model_validate(payload))

    async def _vwap(payload: dict) -> None:
        orchestrator.on_vwap(VWAPValues.model_validate(payload))

    async def _kz(payload: dict) -> None:
        orchestrator.on_kill_zone(KillZoneEvent.model_validate(payload))

    async def _anchor(_payload: dict) -> None:
        return None

    subscribe("sweep_events", _sweep)
    subscribe("mss_events", _mss)
    subscribe("fvg_zones", _fvg)
    subscribe("ohlcv_bars", _bar)
    subscribe("session_levels", _session)
    subscribe("vwap_values", _vwap)
    subscribe("kill_zone_events", _kz)
    subscribe("anchor_events", _anchor)
