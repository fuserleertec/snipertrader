"""Setup 5 — Trend Continuation VWAP Pullback → ``vwap_pullback_cont``.

Session VWAP only (Phase 1 flat bands on ``vwap:{symbol}:session``).
Trend: price above rising session VWAP for N bars (default 20 on 5m) →
bullish; below falling → bearish. Pullback to VWAP or ±1σ with OB or FVG.
First clean touch in a tunable window. Confirm engulfing or strong trend candle.

Locked defaults: N=20 @5m, min_rr 2.0, min conviction 60.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import AssetClass, FVGZone, KillZoneEvent, OHLCVBar, OrderBlock, SessionType, VWAPValues
from sniper_data.pattern_detection.context import get_kill_zone
from sniper_data.setup_detection.atr import atr, stop_beyond
from sniper_data.setup_detection.candidate import SetupCandidate, attach_explainability, risk_reward, score_conviction
from sniper_data.setup_detection.candles import (
    bearish_engulfing,
    bullish_engulfing,
    recent_swing_high,
    recent_swing_low,
    strong_trend_candle,
)
from sniper_data.setup_detection.context import (
    get_active_fvgs,
    get_active_obs,
    get_session_vwap,
    kill_zone_active,
    price_in_range,
    ranges_overlap,
)
from sniper_data.setup_detection.params import SetupParams, load_setup_params

log = logging.getLogger(__name__)

SETUP_NUMBER = 5
SETUP_TYPE = "vwap_pullback_cont"


@dataclass
class _Sym:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=120))
    vwap_hist: deque[float] = field(default_factory=lambda: deque(maxlen=120))
    last_vwap: VWAPValues | None = None
    touches: deque[int] = field(default_factory=lambda: deque(maxlen=32))
    tracked_fvg: dict[str, FVGZone] = field(default_factory=dict)
    last_fire_ts: int = 0


def _tf(bar: OHLCVBar, allowed: tuple[str, ...]) -> str | None:
    tf = bar.timeframe.value if hasattr(bar.timeframe, "value") else str(bar.timeframe)
    return tf if tf in allowed else None


def _klass(value) -> AssetClass:
    return value if isinstance(value, AssetClass) else AssetClass(value)


def _session_name(vwap: VWAPValues | None) -> str | None:
    if vwap is None or vwap.session_type is None:
        return None
    return vwap.session_type.value if hasattr(vwap.session_type, "value") else str(vwap.session_type)


class VwapPullbackContDetector:
    def __init__(self, store: StateStore, *, params: SetupParams | None = None) -> None:
        self.store = store
        self.params = params or load_setup_params()
        self._state: dict[str, _Sym] = defaultdict(_Sym)

    def on_vwap(self, snap: VWAPValues) -> None:
        anchor = snap.anchor_type.value if hasattr(snap.anchor_type, "value") else str(snap.anchor_type)
        if anchor == "session":
            self._state[snap.symbol].last_vwap = snap

    def on_fvg(self, zone: FVGZone) -> None:
        st = self._state[zone.symbol]
        if zone.mitigated:
            st.tracked_fvg.pop(zone.id, None)
            return
        st.tracked_fvg[zone.id] = zone

    def on_ob(self, _zone: OrderBlock) -> None:
        return None

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        tf = _tf(bar, self.params.s5_timeframes)
        if tf is None:
            return []
        st = self._state[bar.symbol]
        prev = st.bars[-1] if st.bars else None
        st.bars.append(bar)
        vwap = st.last_vwap or await get_session_vwap(self.store, bar.symbol)
        if vwap is not None:
            st.last_vwap = vwap
            st.vwap_hist.append(vwap.vwap)
        if vwap is None:
            return []

        trend = self._trend(st, bar, vwap)
        if trend is None:
            return []

        atr_val = atr(st.bars, self.params.atr_period) or 0.0
        pad = self.params.s5_pullback_tol_atr * atr_val
        if not self._is_pullback(bar, vwap, trend, pad=pad):
            return []

        lookback = max(1, self.params.s5_first_touch_lookback_bars)
        if self._had_prior_vwap_touch(st, vwap, pad=pad, lookback=lookback):
            st.touches.append(bar.close_ts_ms)
            return []
        st.touches.append(bar.close_ts_ms)

        fvgs = list(st.tracked_fvg.values()) or await get_active_fvgs(self.store, bar.symbol)
        obs = await get_active_obs(self.store, bar.symbol)
        zone_hit = self._structure_at_pullback(bar, vwap, trend, fvgs, obs, pad=pad)
        if zone_hit is None:
            return []

        if not self._confirm(prev, bar, trend):
            return []

        zone = await get_kill_zone(self.store, bar.symbol)
        cand = self._complete(bar, tf, vwap, trend, zone_hit, atr_val, zone)
        if cand is None:
            return []
        if st.last_fire_ts and bar.close_ts_ms - st.last_fire_ts < 60_000:
            return []
        st.last_fire_ts = bar.close_ts_ms
        return [cand]

    def _trend(self, st: _Sym, bar: OHLCVBar, vwap: VWAPValues) -> str | None:
        n = self.params.s5_trend_bars
        bars = list(st.bars)
        if len(bars) < n or len(st.vwap_hist) < n:
            return None
        window = bars[-n:]
        vwaps = list(st.vwap_hist)[-n:]
        rising = vwaps[-1] > vwaps[0]
        falling = vwaps[-1] < vwaps[0]
        above = all(b.close > v for b, v in zip(window, vwaps, strict=False))
        below = all(b.close < v for b, v in zip(window, vwaps, strict=False))
        # current bar is the pullback — allow it to touch; trend uses prior N-1 + this close vs hist
        prior = window[:-1]
        prior_v = vwaps[:-1] if len(vwaps) == n else vwaps[: len(prior)]
        if len(prior) >= n - 1 and len(prior_v) >= n - 1:
            above = all(b.close > v for b, v in zip(prior, prior_v, strict=False))
            below = all(b.close < v for b, v in zip(prior, prior_v, strict=False))
        if rising and above:
            return "long"
        if falling and below:
            return "short"
        return None

    def _is_pullback(self, bar: OHLCVBar, vwap: VWAPValues, side: str, *, pad: float) -> bool:
        levels = [vwap.vwap, vwap.band_m1, vwap.band_p1]
        touched = any(bar.low - pad <= lvl <= bar.high + pad for lvl in levels)
        if not touched:
            return False
        if side == "long":
            return bar.close >= vwap.vwap - pad
        return bar.close <= vwap.vwap + pad

    def _had_prior_vwap_touch(self, st: _Sym, vwap: VWAPValues, *, pad: float, lookback: int) -> bool:
        """First clean touch of the VWAP line (not ±1σ extension tags during trend)."""
        prior = list(st.bars)[-(lookback + 1) : -1]
        for b in prior:
            if b.low - pad <= vwap.vwap <= b.high + pad:
                return True
        return False

    def _structure_at_pullback(
        self,
        bar: OHLCVBar,
        vwap: VWAPValues,
        side: str,
        fvgs: list[FVGZone],
        obs: list[OrderBlock],
        *,
        pad: float,
    ) -> tuple[str, str] | None:
        want = "bullish" if side == "long" else "bearish"
        zone_low, zone_high = min(vwap.band_m1, vwap.vwap) - pad, max(vwap.band_p1, vwap.vwap) + pad
        for fvg in fvgs:
            if fvg.mitigated or fvg.direction != want:
                continue
            if ranges_overlap(fvg.low, fvg.high, zone_low, zone_high) or price_in_range(
                vwap.vwap, fvg.low, fvg.high, pad=pad
            ):
                return ("fvg", fvg.id)
        for ob in obs:
            if ob.mitigated or ob.direction != want:
                continue
            if ranges_overlap(ob.low, ob.high, zone_low, zone_high) or price_in_range(
                vwap.vwap, ob.low, ob.high, pad=pad
            ):
                return ("order_block", ob.id)
        return None

    def _confirm(self, prev: OHLCVBar | None, bar: OHLCVBar, side: str) -> bool:
        if strong_trend_candle(bar, side, body_frac=self.params.s5_strong_body_frac):
            return True
        if prev is None:
            return False
        return bullish_engulfing(prev, bar) if side == "long" else bearish_engulfing(prev, bar)

    def _complete(
        self,
        bar: OHLCVBar,
        tf: str,
        vwap: VWAPValues,
        side: str,
        zone_hit: tuple[str, str],
        atr_val: float,
        zone: KillZoneEvent | None,
    ) -> SetupCandidate | None:
        buffer = self.params.stop_buffer_atr * atr_val
        entry = bar.close
        liq = max(8, self.params.s5_liquidity_lookback_bars)
        if side == "long":
            swing = recent_swing_low(self._state[bar.symbol].bars, lookback=8) or bar.low
            stop = stop_beyond("long", swing, buffer)
            target = recent_swing_high(self._state[bar.symbol].bars, lookback=liq)
            if target is None or target <= entry:
                target = entry + self.params.s5_min_rr * abs(entry - stop)
        else:
            swing = recent_swing_high(self._state[bar.symbol].bars, lookback=8) or bar.high
            stop = stop_beyond("short", swing, buffer)
            target = recent_swing_low(self._state[bar.symbol].bars, lookback=liq)
            if target is None or target >= entry:
                target = entry - self.params.s5_min_rr * abs(entry - stop)
        rr = risk_reward(side, entry, stop, target)
        if rr < self.params.s5_min_rr:
            log.info("setup5 discard rr<%s symbol=%s rr=%s", self.params.s5_min_rr, bar.symbol, rr)
            return None
        kind, zone_id = zone_hit
        structure = "fvg" if kind == "fvg" else "order_block"
        names = ["trend_align", "vwap_pullback", structure, "first_touch", "engulfing"]
        kz = kill_zone_active(zone, ts_ms=bar.close_ts_ms)
        if bar.volume > 0:
            names.append("volume_confirm")
        if kz:
            names.append("kill_zone")
        conviction = score_conviction(
            confluence=2,
            volume_confirmed=bar.volume > 0,
            kill_zone_aligned=kz,
            base=50,
        )
        session = _session_name(vwap)
        if session:
            try:
                SessionType(session)
            except ValueError:
                session = session
        cand = SetupCandidate(
            setup_number=SETUP_NUMBER,
            setup_type=SETUP_TYPE,
            symbol=bar.symbol,
            asset_class=_klass(bar.asset_class),
            side=side,  # type: ignore[arg-type]
            conviction=conviction,
            entry=entry,
            stop=stop,
            target=target,
            timeframe=tf,  # type: ignore[arg-type]
            trigger_event_ids=[zone_id],
            ts_ms=bar.close_ts_ms,
            ref_vwap=vwap.vwap,
            ref_session=session,
            session_type=session,
            risk_reward=rr,
            kill_zone=zone.kill_zone.value if zone is not None else None,
            volume_confirmed=bar.volume > 0,
            kill_zone_aligned=kz,
            notes={"structure": kind, "atr": atr_val},
        )
        return attach_explainability(cand, names)
