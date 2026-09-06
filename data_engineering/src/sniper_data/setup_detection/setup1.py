"""Setup 1 — Liquidity Sweep + VWAP Reclaim → ``sweep_reclaim``.

Quant walk-forward defaults (see ``SetupParams``):
stop_buffer=0.05×ATR(14), nearer of ±1σ/±2σ with min_rr=2.0,
mss_swing_lookback=5, max_bars_sweep_to_mss=15, require_confirmed_sweep,
session VWAP only, timeframes 5m/15m.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import (
    AssetClass,
    KillZoneEvent,
    MssEvent,
    OHLCVBar,
    SweepEvent,
    VWAPValues,
)
from sniper_data.pattern_detection.context import get_kill_zone
from sniper_data.pattern_detection.mss import SwingPoint
from sniper_data.setup_detection.atr import atr, stop_beyond
from sniper_data.setup_detection.candidate import SetupCandidate, attach_explainability, risk_reward, score_conviction
from sniper_data.setup_detection.context import band_tagged, get_session_vwap, kill_zone_active
from sniper_data.setup_detection.params import SetupParams, load_setup_params

log = logging.getLogger(__name__)

SETUP_NUMBER = 1
SETUP_TYPE = "sweep_reclaim"


@dataclass
class _Armed:
    sweep: SweepEvent
    extreme: float
    last_lh: float | None = None
    last_hl: float | None = None
    prior_high: float | None = None
    prior_low: float | None = None
    bars_since: int = 0
    fired: bool = False


@dataclass
class _Sym:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=400))
    swings: list[SwingPoint] = field(default_factory=list)
    armed: list[_Armed] = field(default_factory=list)
    pending_mss: list[MssEvent] = field(default_factory=list)
    next_index: int = 0
    last_vwap: VWAPValues | None = None


def _choose_target(side: str, entry: float, stop: float, vwap: VWAPValues, min_rr: float) -> float | None:
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    if side == "long":
        options = [vwap.band_p1, vwap.band_p2]
        valid = [t for t in options if t > entry and (t - entry) / risk >= min_rr]
    else:
        options = [vwap.band_m1, vwap.band_m2]
        valid = [t for t in options if t < entry and (entry - t) / risk >= min_rr]
    if not valid:
        return None
    return min(valid, key=lambda t: abs(t - entry))


class SweepReclaimDetector:
    def __init__(
        self,
        store: StateStore,
        *,
        swing_lookback: int | None = None,
        params: SetupParams | None = None,
    ) -> None:
        self.store = store
        self.params = params or load_setup_params()
        self.lookback = max(1, swing_lookback if swing_lookback is not None else self.params.s1_mss_swing_lookback)
        self._state: dict[str, _Sym] = defaultdict(_Sym)

    def _tf(self, bar: OHLCVBar) -> str | None:
        tf = bar.timeframe.value if hasattr(bar.timeframe, "value") else str(bar.timeframe)
        return tf if tf in self.params.s1_timeframes else None

    def on_vwap(self, snap: VWAPValues) -> None:
        anchor = snap.anchor_type.value if hasattr(snap.anchor_type, "value") else str(snap.anchor_type)
        if anchor == "session":
            self._state[snap.symbol].last_vwap = snap

    def on_sweep(self, event: SweepEvent) -> None:
        if not event.id:
            return
        if self.params.s1_require_confirmed_sweep:
            if not (event.confirmed is True or event.reclaim is True):
                return
        st = self._state[event.symbol]
        if any(a.sweep.id == event.id for a in st.armed):
            for a in st.armed:
                if a.sweep.id == event.id:
                    a.sweep = event
            return
        st.armed.append(
            _Armed(
                sweep=event,
                extreme=event.swept_level,
                prior_high=event.swept_level,
                prior_low=event.swept_level,
            )
        )

    def on_mss(self, event: MssEvent) -> None:
        self._state[event.symbol].pending_mss.append(event)

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        st = self._state[bar.symbol]
        st.bars.append(bar)
        idx = st.next_index
        st.next_index += 1
        self._confirm_swings(st, idx)
        self._update_extremes(st, bar)

        pending_mss = list(st.pending_mss)
        st.pending_mss.clear()

        vwap = st.last_vwap or await get_session_vwap(self.store, bar.symbol)
        if vwap is not None:
            st.last_vwap = vwap
        zone = await get_kill_zone(self.store, bar.symbol)
        out: list[SetupCandidate] = []
        for armed in st.armed:
            if armed.fired:
                continue
            armed.bars_since += 1
            if armed.bars_since > self.params.s1_max_bars_sweep_to_mss:
                armed.fired = True
                continue
            mss = self._match_mss(armed, pending_mss) or self._detect_reclaim_mss(armed, bar)
            if mss is None:
                continue
            cand = self._complete(armed, bar, mss, vwap, zone)
            if cand is not None:
                armed.fired = True
                out.append(cand)
        return out

    def _update_extremes(self, st: _Sym, bar: OHLCVBar) -> None:
        for armed in st.armed:
            if armed.fired:
                continue
            if armed.sweep.side == "buy":
                armed.extreme = min(armed.extreme, bar.low, armed.sweep.swept_level)
            else:
                armed.extreme = max(armed.extreme, bar.high, armed.sweep.swept_level)

    def _confirm_swings(self, st: _Sym, latest_index: int) -> None:
        n = self.lookback
        cand_index = latest_index - n
        if cand_index < n:
            return
        bars = list(st.bars)
        start_index = latest_index - len(bars) + 1
        local = cand_index - start_index
        if local < n or local + n >= len(bars):
            return
        cand = bars[local]
        window = bars[local - n : local + n + 1]
        if all(cand.high > b.high for i, b in enumerate(window) if i != n):
            st.swings.append(SwingPoint("high", cand.high, cand.close_ts_ms, cand_index))
            self._note_swing(st, "high", cand.high)
        if all(cand.low < b.low for i, b in enumerate(window) if i != n):
            st.swings.append(SwingPoint("low", cand.low, cand.close_ts_ms, cand_index))
            self._note_swing(st, "low", cand.low)

    def _note_swing(self, st: _Sym, kind: str, price: float) -> None:
        for armed in st.armed:
            if armed.fired:
                continue
            if kind == "high":
                if armed.prior_high is not None and price < armed.prior_high:
                    armed.last_lh = price
                armed.prior_high = price
            else:
                if armed.prior_low is not None and price > armed.prior_low:
                    armed.last_hl = price
                armed.prior_low = price

    def _match_mss(self, armed: _Armed, events: list[MssEvent]) -> MssEvent | None:
        want = "bullish" if armed.sweep.side == "buy" else "bearish"
        for ev in events:
            if ev.symbol != armed.sweep.symbol:
                continue
            if ev.direction == want and ev.ts_ms >= armed.sweep.ts_ms:
                return ev
        return None

    def _detect_reclaim_mss(self, armed: _Armed, bar: OHLCVBar) -> MssEvent | None:
        sweep = armed.sweep
        klass = sweep.asset_class if isinstance(sweep.asset_class, AssetClass) else AssetClass(sweep.asset_class)
        tf = self._tf(bar)
        if sweep.side == "buy" and armed.last_lh is not None and bar.high > armed.last_lh:
            return MssEvent(
                id=f"mss-reclaim-{sweep.id}",
                symbol=bar.symbol,
                asset_class=klass,
                ts_ms=bar.close_ts_ms,
                direction="bullish",
                broken_level=armed.last_lh,
                swing_high=bar.high,
                swing_low=bar.low,
                trigger_sweep_id=sweep.id,
                trigger_sweep_side=sweep.side,
                timeframe=tf,  # type: ignore[arg-type]
                confirmed=True,
            )
        if sweep.side == "sell" and armed.last_hl is not None and bar.low < armed.last_hl:
            return MssEvent(
                id=f"mss-reclaim-{sweep.id}",
                symbol=bar.symbol,
                asset_class=klass,
                ts_ms=bar.close_ts_ms,
                direction="bearish",
                broken_level=armed.last_hl,
                swing_high=bar.high,
                swing_low=bar.low,
                trigger_sweep_id=sweep.id,
                trigger_sweep_side=sweep.side,
                timeframe=tf,  # type: ignore[arg-type]
                confirmed=True,
            )
        return None

    def _complete(
        self,
        armed: _Armed,
        bar: OHLCVBar,
        mss: MssEvent,
        vwap: VWAPValues | None,
        zone: KillZoneEvent | None,
    ) -> SetupCandidate | None:
        tf = self._tf(bar)
        if tf is None or vwap is None:
            return None
        side = "long" if armed.sweep.side == "buy" else "short"
        if side == "long" and not (bar.close > vwap.vwap):
            return None
        if side == "short" and not (bar.close < vwap.vwap):
            return None
        atr_val = atr(self._state[bar.symbol].bars, self.params.atr_period) or 0.0
        buffer = self.params.stop_buffer_atr * atr_val
        entry = bar.close
        stop = stop_beyond(side, armed.extreme, buffer)
        if side == "long" and stop >= entry:
            stop = stop_beyond(side, min(armed.sweep.swept_level, bar.low, armed.extreme), buffer)
        if side == "short" and stop <= entry:
            stop = stop_beyond(side, max(armed.sweep.swept_level, bar.high, armed.extreme), buffer)
        target = _choose_target(side, entry, stop, vwap, self.params.s1_min_rr)
        if target is None:
            log.info(
                "setup1 discard rr<%s symbol=%s side=%s entry=%s stop=%s vwap=%s",
                self.params.s1_min_rr,
                bar.symbol,
                side,
                entry,
                stop,
                vwap.vwap,
            )
            return None
        rr = risk_reward(side, entry, stop, target)
        if rr < self.params.s1_min_rr:
            return None
        tagged = band_tagged(armed.extreme, vwap) or band_tagged(armed.sweep.swept_level, vwap)
        kz = kill_zone_active(zone, ts_ms=bar.close_ts_ms)
        conviction = score_conviction(
            confluence=1 + (1 if tagged else 0),
            volume_confirmed=armed.sweep.volume_profile == "aggressive",
            kill_zone_aligned=kz,
            confirmed_reclaim=bool(armed.sweep.confirmed or armed.sweep.reclaim),
        )
        session = None
        if vwap.session_type is not None:
            session = vwap.session_type.value if hasattr(vwap.session_type, "value") else str(vwap.session_type)
        names = ["liquidity_sweep", "mss", "vwap_reclaim"]
        if armed.sweep.volume_profile == "aggressive":
            names.append("volume_confirm")
        if kz:
            names.append("kill_zone")
        cand = SetupCandidate(
            setup_number=SETUP_NUMBER,
            setup_type=SETUP_TYPE,
            symbol=bar.symbol,
            asset_class=bar.asset_class if isinstance(bar.asset_class, AssetClass) else AssetClass(bar.asset_class),
            side=side,
            conviction=conviction,
            entry=entry,
            stop=stop,
            target=target,
            timeframe=tf,  # type: ignore[arg-type]
            trigger_event_ids=[armed.sweep.id, mss.id],
            ts_ms=bar.close_ts_ms,
            ref_vwap=vwap.vwap,
            ref_session=session,
            session_type=session,
            risk_reward=rr,
            kill_zone=zone.kill_zone.value if zone is not None else None,
            volume_confirmed=armed.sweep.volume_profile == "aggressive",
            kill_zone_aligned=kz,
            notes={"band_tag": tagged, "mss_direction": mss.direction, "atr": atr_val},
        )
        return attach_explainability(cand, names)
