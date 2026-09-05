"""Run setups 1–6 in parallel, refine conviction, dedupe, risk-filter, publish."""

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
    OrderBlock,
    SessionLevels,
    SweepEvent,
    VWAPValues,
)
from sniper_data.pattern_detection.ids import make_id
from sniper_data.pattern_detection.validate import validate_topic
from sniper_data.setup_detection.candidate import SetupCandidate, to_risk_request, to_setup_signal
from sniper_data.setup_detection.context import get_kill_zone, kill_zone_active
from sniper_data.setup_detection.news import AllowAllNewsFilter, NewsFilter
from sniper_data.setup_detection.params import SetupParams, load_setup_params
from sniper_data.setup_detection.risk_client import RiskClient
from sniper_data.setup_detection.setup1 import SweepReclaimDetector
from sniper_data.setup_detection.setup2 import FVGEntryDetector
from sniper_data.setup_detection.setup3 import JudasDetector
from sniper_data.setup_detection.setup4 import SdExtensionFadeDetector
from sniper_data.setup_detection.setup5 import VwapPullbackContDetector
from sniper_data.setup_detection.setup6 import AvwapObConfluenceDetector

log = logging.getLogger(__name__)

SETUP_SIGNALS_TOPIC = "setup_signals"


@dataclass
class OrchestratorStats:
    raw: int = 0
    approved: int = 0
    rejected: int = 0
    deduped: int = 0
    published: int = 0
    skipped_conviction: int = 0
    pre_filter: int = 0
    post_filter: int = 0

    def as_dict(self) -> dict[str, Any]:
        decided = self.approved + self.rejected
        fp_rate = (self.rejected / decided) if decided else None
        return {
            "raw": self.raw,
            "approved": self.approved,
            "rejected": self.rejected,
            "deduped": self.deduped,
            "published": self.published,
            "skipped_conviction": self.skipped_conviction,
            "pre_filter": self.pre_filter,
            "post_filter": self.post_filter,
            "false_positive_rate": fp_rate,
        }


@dataclass
class SetupOrchestrator:
    store: StateStore
    bus: EventBus
    risk: RiskClient
    swing_lookback: int | None = None
    params: SetupParams | None = None
    news: NewsFilter | None = None
    setup1: SweepReclaimDetector = field(init=False)
    setup2: FVGEntryDetector = field(init=False)
    setup3: JudasDetector = field(init=False)
    setup4: SdExtensionFadeDetector = field(init=False)
    setup5: VwapPullbackContDetector = field(init=False)
    setup6: AvwapObConfluenceDetector = field(init=False)
    stats: OrchestratorStats = field(default_factory=OrchestratorStats)
    raw_log: list[dict[str, Any]] = field(default_factory=list)
    approved_log: list[dict[str, Any]] = field(default_factory=list)
    pre_filter_log: list[dict[str, Any]] = field(default_factory=list)
    post_filter_log: list[dict[str, Any]] = field(default_factory=list)
    _recent: list[SetupCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.params = self.params or load_setup_params()
        news = self.news if self.news is not None else AllowAllNewsFilter()
        lookback = self.swing_lookback if self.swing_lookback is not None else self.params.s1_mss_swing_lookback
        self.setup1 = SweepReclaimDetector(self.store, swing_lookback=lookback, params=self.params)
        self.setup2 = FVGEntryDetector(self.store, params=self.params)
        self.setup3 = JudasDetector(self.store, params=self.params)
        self.setup4 = SdExtensionFadeDetector(self.store, params=self.params, news=news)
        self.setup5 = VwapPullbackContDetector(self.store, params=self.params)
        self.setup6 = AvwapObConfluenceDetector(self.store, params=self.params)

    def on_vwap(self, snap: VWAPValues) -> None:
        self.setup1.on_vwap(snap)
        self.setup2.on_vwap(snap)
        self.setup3.on_vwap(snap)
        self.setup4.on_vwap(snap)
        self.setup5.on_vwap(snap)
        self.setup6.on_vwap(snap)

    def on_session(self, levels: SessionLevels) -> None:
        self.setup3.on_session(levels)

    def on_kill_zone(self, event: KillZoneEvent) -> None:
        self.setup3.on_kill_zone(event)

    def on_sweep(self, event: SweepEvent) -> None:
        self.setup1.on_sweep(event)
        self.setup3.on_sweep(event)

    def on_mss(self, event: MssEvent) -> None:
        self.setup1.on_mss(event)
        self.setup4.on_mss(event)
        self.setup6.on_mss(event)

    def on_fvg(self, zone: FVGZone) -> None:
        self.setup2.on_fvg(zone)
        self.setup5.on_fvg(zone)

    def on_ob(self, zone: OrderBlock) -> None:
        self.setup5.on_ob(zone)
        self.setup6.on_ob(zone)

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        t0 = time.perf_counter()
        batches = await _gather_setups(
            self.setup1.on_bar(bar),
            self.setup2.on_bar(bar),
            self.setup3.on_bar(bar),
            self.setup4.on_bar(bar),
            self.setup5.on_bar(bar),
            self.setup6.on_bar(bar),
        )
        record_setup_latency("all", time.perf_counter() - t0)
        incoming = [c for batch in batches for c in batch]
        await self._refine(incoming, bar)
        return await self.submit(incoming)

    async def _refine(self, incoming: list[SetupCandidate], bar: OHLCVBar) -> None:
        """Adaptive conviction: kill zone, volume confirm, multi-pattern confluence.

        ATR-regime threshold adjustment is applied inside Setup 4 (high ATR/price
        requires a ±3σ tag). Hooks here only add documented bonuses.
        """
        if not incoming:
            return
        zone = await get_kill_zone(self.store, bar.symbol)
        kz = kill_zone_active(zone, ts_ms=bar.close_ts_ms)
        by_key: dict[tuple[str, str], set[str]] = {}
        for cand in incoming:
            by_key.setdefault((cand.symbol, cand.side), set()).add(cand.setup_type)
        p = self.params or load_setup_params()
        for cand in incoming:
            extra = 0
            factors = list(cand.contributing_factors)
            if kz or cand.kill_zone_aligned:
                cand.kill_zone_aligned = True
                extra += p.conv_kill_zone_bonus
                if "kill_zone" not in factors:
                    factors.append("kill_zone")
            if cand.volume_confirmed:
                extra += p.conv_volume_bonus
                if "volume_confirm" not in factors:
                    factors.append("volume_confirm")
            if len(by_key.get((cand.symbol, cand.side), ())) >= 2:
                extra += p.conv_multi_pattern_bonus
                if "multi_pattern" not in factors:
                    factors.append("multi_pattern")
            cand.conviction = max(0, min(100, cand.conviction + extra))
            cand.contributing_factors = factors
            breakdown = dict(cand.factor_breakdown)
            if kz or cand.kill_zone_aligned:
                breakdown["kill_zone"] = float(p.conv_kill_zone_bonus)
            if cand.volume_confirmed:
                breakdown["volume_confirm"] = float(p.conv_volume_bonus)
            if len(by_key.get((cand.symbol, cand.side), ())) >= 2:
                breakdown["multi_pattern"] = float(p.conv_multi_pattern_bonus)
            breakdown["conviction"] = float(cand.conviction)
            cand.factor_breakdown = breakdown

    async def submit(self, incoming: list[SetupCandidate]) -> list[SetupCandidate]:
        if not incoming:
            return []
        self.stats.pre_filter += len(incoming)
        for cand in incoming:
            self.stats.raw += 1
            record_setup_candidate(cand.setup_type, cand.side)
            log.info("setup raw / pre-filter %s", cand.log_fields())
            self.raw_log.append(cand.log_fields())
            self.pre_filter_log.append(cand.log_fields())

        winners = self._dedupe_against_recent(incoming)
        self.stats.post_filter += len(winners)
        for cand in winners:
            log.info("setup post-filter %s", cand.log_fields())
            self.post_filter_log.append(cand.log_fields())

        published: list[SetupCandidate] = []
        params = self.params or load_setup_params()
        for cand in winners:
            min_conv = params.min_conviction_for(cand.setup_type)
            if cand.conviction < min_conv:
                self.stats.skipped_conviction += 1
                log.info("setup skip conviction<%s %s", min_conv, cand.log_fields())
                continue
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
        window = self.params.dedupe_window_ms if self.params else 300_000
        winners = dedupe_candidates(pool, window_ms=window)
        winner_ids = {id(c) for c in winners}
        kept = [c for c in incoming if id(c) in winner_ids]
        dropped = len(incoming) - len(kept)
        self.stats.deduped += dropped
        return kept

    def _prune_recent(self, now_ms: int) -> None:
        window = self.params.dedupe_window_ms if self.params else 300_000
        self._recent = [c for c in self._recent if now_ms - c.ts_ms <= window]


def dedupe_candidates(
    candidates: list[SetupCandidate],
    *,
    window_ms: int | None = None,
) -> list[SetupCandidate]:
    """Same symbol + direction within window → highest conviction, else earliest ts."""
    window = window_ms if window_ms is not None else 300_000
    ordered = sorted(candidates, key=lambda c: (c.ts_ms, -c.conviction))
    kept: list[SetupCandidate] = []
    for cand in ordered:
        rival_idx = None
        for i, existing in enumerate(kept):
            if _conflicts(existing, cand, window_ms=window):
                rival_idx = i
                break
        if rival_idx is None:
            kept.append(cand)
            continue
        rival = kept[rival_idx]
        if cand.conviction > rival.conviction:
            kept[rival_idx] = cand
        elif cand.conviction == rival.conviction and cand.ts_ms < rival.ts_ms:
            kept[rival_idx] = cand
    return kept


def _conflicts(a: SetupCandidate, b: SetupCandidate, *, window_ms: int) -> bool:
    if a.symbol != b.symbol or a.side != b.side:
        return False
    return abs(a.ts_ms - b.ts_ms) <= window_ms


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

    async def _ob(payload: dict) -> None:
        orchestrator.on_ob(OrderBlock.model_validate(payload))

    async def _bar(payload: dict) -> None:
        await orchestrator.on_bar(OHLCVBar.model_validate(payload))

    async def _session(payload: dict) -> None:
        orchestrator.on_session(SessionLevels.model_validate(payload))

    async def _vwap(payload: dict) -> None:
        orchestrator.on_vwap(VWAPValues.model_validate(payload))

    async def _kz(payload: dict) -> None:
        orchestrator.on_kill_zone(KillZoneEvent.model_validate(payload))

    async def _anchor(payload: dict) -> None:
        orchestrator.setup6.on_anchor(payload)

    subscribe("sweep_events", _sweep)
    subscribe("mss_events", _mss)
    subscribe("fvg_zones", _fvg)
    subscribe("order_block_zones", _ob)
    subscribe("ohlcv_bars", _bar)
    subscribe("session_levels", _session)
    subscribe("vwap_values", _vwap)
    subscribe("kill_zone_events", _kz)
    subscribe("anchor_events", _anchor)
