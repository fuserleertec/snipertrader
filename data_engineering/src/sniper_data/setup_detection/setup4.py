"""Setup 4 — Standard Deviation Extension Fade → ``sd_extension_fade``.

Session VWAP only: Redis ``vwap:{symbol}:session`` with Phase 1 flat
``band_m3`` / ``band_m2`` / ``band_p2`` / ``band_p3``. Do not read AVWAP here.

Locked defaults: volume < 80% of 20-bar avg, SL beyond ±3σ, TP = session
VWAP, min_rr 1.5 (prefer 2.0 at 3σ), min conviction 60, news stub 15m.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import AssetClass, KillZoneEvent, MssEvent, OHLCVBar, VWAPValues
from sniper_data.pattern_detection.context import get_kill_zone
from sniper_data.setup_detection.atr import atr, stop_beyond
from sniper_data.setup_detection.candidate import SetupCandidate, breakdown_from_factors, risk_reward, score_conviction
from sniper_data.setup_detection.candles import rejection_reverse
from sniper_data.setup_detection.context import (
    atr_regime,
    get_session_vwap,
    kill_zone_active,
    session_band_extreme,
)
from sniper_data.setup_detection.news import AllowAllNewsFilter, NewsFilter
from sniper_data.setup_detection.params import SetupParams, load_setup_params

log = logging.getLogger(__name__)

SETUP_NUMBER = 4
SETUP_TYPE = "sd_extension_fade"


@dataclass
class _Sym:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=80))
    last_vwap: VWAPValues | None = None
    pending_mss: list[MssEvent] = field(default_factory=list)
    last_fire_ts: int = 0


def _tf(bar: OHLCVBar, allowed: tuple[str, ...]) -> str | None:
    tf = bar.timeframe.value if hasattr(bar.timeframe, "value") else str(bar.timeframe)
    return tf if tf in allowed else None


def _klass(value) -> AssetClass:
    return value if isinstance(value, AssetClass) else AssetClass(value)


def _mean_volume(bars: deque[OHLCVBar], period: int) -> float | None:
    prior = list(bars)[:-1]
    window = prior[-period:] if period > 0 else prior
    if len(window) < max(2, min(period, 5)):
        return None
    return sum(b.volume for b in window) / len(window)


def _session_name(vwap: VWAPValues | None) -> str | None:
    if vwap is None or vwap.session_type is None:
        return None
    return vwap.session_type.value if hasattr(vwap.session_type, "value") else str(vwap.session_type)


class SdExtensionFadeDetector:
    def __init__(
        self,
        store: StateStore,
        *,
        params: SetupParams | None = None,
        news: NewsFilter | None = None,
    ) -> None:
        self.store = store
        self.params = params or load_setup_params()
        self.news = news if news is not None else AllowAllNewsFilter()
        self._state: dict[str, _Sym] = defaultdict(_Sym)

    def on_vwap(self, snap: VWAPValues) -> None:
        anchor = snap.anchor_type.value if hasattr(snap.anchor_type, "value") else str(snap.anchor_type)
        if anchor == "session":
            self._state[snap.symbol].last_vwap = snap

    def on_mss(self, event: MssEvent) -> None:
        self._state[event.symbol].pending_mss.append(event)

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        tf = _tf(bar, self.params.s4_timeframes)
        if tf is None:
            return []
        st = self._state[bar.symbol]
        prev = st.bars[-1] if st.bars else None
        st.bars.append(bar)
        vwap = st.last_vwap or await get_session_vwap(self.store, bar.symbol)
        if vwap is not None:
            st.last_vwap = vwap
        if vwap is None:
            return []
        if self.news.should_skip(bar.symbol, bar.close_ts_ms, window_ms=self.params.s4_news_window_ms):
            log.info("setup4 skip news window symbol=%s ts=%s", bar.symbol, bar.close_ts_ms)
            st.pending_mss.clear()
            return []

        pending = list(st.pending_mss)
        st.pending_mss.clear()
        avg_vol = _mean_volume(st.bars, self.params.s4_vol_avg_period)
        if avg_vol is None or avg_vol <= 0:
            return []
        low_volume = bar.volume < self.params.s4_vol_frac * avg_vol
        if not low_volume:
            return []

        tagged = session_band_extreme(bar.low, vwap, frac=self.params.s4_band_tag_frac) or session_band_extreme(
            bar.high, vwap, frac=self.params.s4_band_tag_frac
        )
        if tagged is None:
            tagged = session_band_extreme(bar.close, vwap, frac=self.params.s4_band_tag_frac)
        if tagged is None:
            return []

        atr_val = atr(st.bars, self.params.atr_period) or 0.0
        regime = atr_regime(atr_val, bar.close, high_frac=self.params.atr_regime_high_frac)
        if regime == "high" and tagged not in {"plus_3_sigma", "minus_3_sigma"}:
            log.info("setup4 skip atr-regime high requires 3σ symbol=%s tag=%s", bar.symbol, tagged)
            return []

        if tagged in {"minus_2_sigma", "minus_3_sigma"}:
            side = "long"
        elif tagged in {"plus_2_sigma", "plus_3_sigma"}:
            side = "short"
        else:
            return []

        mss = self._match_mss(pending, bar, side)
        rejected = rejection_reverse(prev, bar, side, pin_wick_ratio=self.params.s4_pin_wick_ratio)
        if not rejected and mss is None:
            return []

        zone = await get_kill_zone(self.store, bar.symbol)
        cand = self._complete(bar, tf, vwap, side, tagged, atr_val, zone, mss, regime)
        if cand is None:
            return []
        if st.last_fire_ts and bar.close_ts_ms - st.last_fire_ts < 60_000:
            return []
        st.last_fire_ts = bar.close_ts_ms
        return [cand]

    def _match_mss(self, events: list[MssEvent], bar: OHLCVBar, side: str) -> MssEvent | None:
        want = "bullish" if side == "long" else "bearish"
        allowed = set(self.params.s4_timeframes)
        for ev in events:
            tf = ev.timeframe
            if tf is not None and tf not in allowed:
                continue
            if ev.symbol == bar.symbol and ev.direction == want and ev.ts_ms <= bar.close_ts_ms:
                return ev
        return None

    def _complete(
        self,
        bar: OHLCVBar,
        tf: str,
        vwap: VWAPValues,
        side: str,
        tagged: str,
        atr_val: float,
        zone: KillZoneEvent | None,
        mss: MssEvent | None,
        regime: str,
    ) -> SetupCandidate | None:
        buffer = self.params.stop_buffer_atr * atr_val
        entry = bar.close
        if side == "long":
            stop = stop_beyond("long", vwap.band_m3, buffer)
        else:
            stop = stop_beyond("short", vwap.band_p3, buffer)
        target = vwap.vwap
        rr = risk_reward(side, entry, stop, target)
        need = self.params.s4_min_rr_at_3s if tagged.endswith("3_sigma") else self.params.s4_min_rr
        if tagged.endswith("3_sigma") and rr < self.params.s4_min_rr_at_3s:
            if rr < self.params.s4_min_rr:
                return None
            # prefer 2.0 at 3σ; still accept if ≥ locked min_rr 1.5
            need = self.params.s4_min_rr
        if rr < need:
            log.info("setup4 discard rr<%s tag=%s symbol=%s rr=%s", need, tagged, bar.symbol, rr)
            return None
        kz = kill_zone_active(zone, ts_ms=bar.close_ts_ms)
        factors = ["vwap_band_extension", "low_volume", "rejection_candle"]
        if mss is not None:
            factors.append("mss")
        if tagged.endswith("3_sigma"):
            factors.append("three_sigma")
        conviction = score_conviction(
            confluence=2 if tagged.endswith("3_sigma") else 1,
            volume_confirmed=True,
            kill_zone_aligned=kz,
            confirmed_reclaim=mss is not None,
            base=50,
        )
        ids = [f"vwap-session-{bar.symbol}"]
        if mss is not None and mss.id:
            ids.append(mss.id)
        session = _session_name(vwap)
        return SetupCandidate(
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
            trigger_event_ids=ids,
            ts_ms=bar.close_ts_ms,
            ref_vwap=vwap.vwap,
            ref_session=session,
            session_type=session,
            risk_reward=rr,
            kill_zone=zone.kill_zone.value if zone is not None else None,
            contributing_factors=factors,
            factor_breakdown=breakdown_from_factors(factors, base=50),
            volume_confirmed=True,
            kill_zone_aligned=kz,
            notes={"band_tag": tagged, "atr": atr_val, "atr_regime": regime},
        )
