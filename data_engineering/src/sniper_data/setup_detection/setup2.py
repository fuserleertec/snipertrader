"""Setup 2 — FVG mitigation at a VWAP / volume-profile node.

``setup_type`` is ``fvg_entry``, or ``ob_fvg`` when an order block overlaps.
Active zones come from Redis ``fvg:{symbol}:*`` (TTL ≤ 48h).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import AssetClass, FVGZone, KillZoneEvent, OHLCVBar, OrderBlock, SessionType, VWAPValues
from sniper_data.pattern_detection.context import get_kill_zone, get_volume_profile, list_volume_profiles
from sniper_data.setup_detection.atr import atr, stop_beyond
from sniper_data.setup_detection.candidate import SetupCandidate, attach_explainability, risk_reward, score_conviction
from sniper_data.setup_detection.candles import is_confirmation, recent_swing_high, recent_swing_low
from sniper_data.setup_detection.context import (
    get_active_fvgs,
    get_active_obs,
    get_session_vwap,
    kill_zone_active,
    price_in_range,
    profile_overlaps_zone,
    ranges_overlap,
)
from sniper_data.setup_detection.params import SetupParams, load_setup_params

SETUP_NUMBER = 2


@dataclass
class _Touched:
    zone: FVGZone
    touched: bool = False
    fired: bool = False


@dataclass
class _Sym:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=80))
    last_vwap: VWAPValues | None = None
    tracked: dict[str, _Touched] = field(default_factory=dict)


def _tf(bar: OHLCVBar) -> str | None:
    tf = bar.timeframe.value if hasattr(bar.timeframe, "value") else str(bar.timeframe)
    return tf if tf in {"1m", "5m", "15m"} else None


def _session_name(vwap: VWAPValues | None) -> str | None:
    if vwap is None or vwap.session_type is None:
        return None
    return vwap.session_type.value if hasattr(vwap.session_type, "value") else str(vwap.session_type)


class FVGEntryDetector:
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
            st.tracked.pop(zone.id, None)
            return
        st.tracked.setdefault(zone.id, _Touched(zone=zone))
        st.tracked[zone.id].zone = zone

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        tf = _tf(bar)
        if tf is None:
            return []
        st = self._state[bar.symbol]
        prev = st.bars[-1] if st.bars else None
        st.bars.append(bar)

        vwap = st.last_vwap or await get_session_vwap(self.store, bar.symbol)
        if vwap is not None:
            st.last_vwap = vwap
        zones = list(st.tracked.values())
        if not zones:
            for z in await get_active_fvgs(self.store, bar.symbol):
                st.tracked.setdefault(z.id, _Touched(zone=z))
            zones = list(st.tracked.values())
        obs = await get_active_obs(self.store, bar.symbol)
        session = _session_name(vwap)
        profiles = []
        if session:
            one = await get_volume_profile(self.store, bar.symbol, session)
            if one is not None:
                profiles.append(one)
        if not profiles:
            profiles = await list_volume_profiles(self.store, bar.symbol)
        zone_evt = await get_kill_zone(self.store, bar.symbol)

        out: list[SetupCandidate] = []
        for tracked in zones:
            if tracked.fired or tracked.zone.mitigated:
                continue
            fvg = tracked.zone
            age_h = (bar.close_ts_ms - fvg.created_ts_ms) / 3_600_000
            if age_h > self.params.s2_max_fvg_age_hours:
                continue
            atr_val = atr(st.bars, self.params.atr_period) or 0.0
            pad = self.params.s2_overlap_tol_atr * atr_val
            if not self._confluent(fvg, vwap, profiles, pad=pad):
                continue
            if bar.low <= fvg.high + pad and bar.high >= fvg.low - pad:
                tracked.touched = True
            if not tracked.touched:
                continue
            side = "long" if fvg.direction == "bullish" else "short"
            if not is_confirmation(
                prev,
                bar,
                side,
                fvg.low,
                fvg.high,
                pin_wick_ratio=self.params.s2_pin_wick_ratio,
                allow_reversal=False,
            ):
                continue
            cand = self._complete(bar, tf, fvg, side, vwap, obs, session, zone_evt, profiles, atr_val)
            if cand is not None:
                tracked.fired = True
                out.append(cand)
        return out

    def _confluent(self, fvg: FVGZone, vwap: VWAPValues | None, profiles, *, pad: float = 0.0) -> bool:
        if vwap is not None and price_in_range(vwap.vwap, fvg.low, fvg.high, pad=pad):
            return True
        return any(profile_overlaps_zone(p, fvg.low - pad, fvg.high + pad) for p in profiles)

    def _complete(
        self,
        bar: OHLCVBar,
        tf: str,
        fvg: FVGZone,
        side: str,
        vwap: VWAPValues | None,
        obs: list[OrderBlock],
        session: str | None,
        zone: KillZoneEvent | None,
        profiles,
        atr_val: float,
    ) -> SetupCandidate | None:
        buffer = self.params.stop_buffer_atr * atr_val
        entry = bar.close  # Quant: confirm_close
        if side == "long":
            stop = stop_beyond("long", fvg.low, buffer)
            target = recent_swing_high(self._state[bar.symbol].bars)
            if target is None or target <= entry:
                risk = abs(entry - stop)
                target = entry + self.params.s2_target_rr_fallback * risk
        else:
            stop = stop_beyond("short", fvg.high, buffer)
            target = recent_swing_low(self._state[bar.symbol].bars)
            if target is None or target >= entry:
                risk = abs(entry - stop)
                target = entry - self.params.s2_target_rr_fallback * risk
        rr = risk_reward(side, entry, stop, target)
        if rr <= 0:
            return None
        overlapping = [
            ob
            for ob in obs
            if not ob.mitigated
            and ob.direction == fvg.direction
            and ranges_overlap(ob.low, ob.high, fvg.low, fvg.high)
        ]
        setup_type = "ob_fvg" if overlapping else "fvg_entry"
        ids = [fvg.id] + [ob.id for ob in overlapping]
        pad = self.params.s2_overlap_tol_atr * atr_val
        confluence = 1
        if vwap is not None and price_in_range(vwap.vwap, fvg.low, fvg.high, pad=pad):
            confluence += 1
        if any(profile_overlaps_zone(p, fvg.low - pad, fvg.high + pad) for p in profiles):
            confluence += 1
        if overlapping:
            confluence += 1
        kz = kill_zone_active(zone, ts_ms=bar.close_ts_ms)
        conviction = score_conviction(
            confluence=confluence,
            volume_confirmed=bar.volume > 0,
            kill_zone_aligned=kz,
        )
        klass = bar.asset_class if isinstance(bar.asset_class, AssetClass) else AssetClass(bar.asset_class)
        ref_session = session
        if session:
            try:
                SessionType(session)
            except ValueError:
                ref_session = session
        names = ["fvg", "engulfing"]
        if vwap is not None and price_in_range(vwap.vwap, fvg.low, fvg.high, pad=pad):
            names.append("vwap_reclaim")
        if overlapping:
            names.append("order_block")
        if bar.volume > 0:
            names.append("volume_confirm")
        if kz:
            names.append("kill_zone")
        cand = SetupCandidate(
            setup_number=SETUP_NUMBER,
            setup_type=setup_type,  # type: ignore[arg-type]
            symbol=bar.symbol,
            asset_class=klass,
            side=side,  # type: ignore[arg-type]
            conviction=conviction,
            entry=entry,
            stop=stop,
            target=target,
            timeframe=tf,  # type: ignore[arg-type]
            trigger_event_ids=ids,
            ts_ms=bar.close_ts_ms,
            ref_vwap=vwap.vwap if vwap else None,
            ref_session=ref_session,
            session_type=session,
            risk_reward=rr,
            kill_zone=zone.kill_zone.value if zone is not None else None,
            volume_confirmed=bar.volume > 0,
            kill_zone_aligned=kz,
        )
        return attach_explainability(cand, names)
