"""Setup 3 — PO3 / Judas swing rejection → ``po3_judas``.

Accumulation range from ``session:{symbol}:asia`` (crypto) or the
asset-appropriate book (ETH / Globex). Manipulation is confirmed during
an active kill zone (``kill_zone:{symbol}`` / ``kill_zone_events``):
NY AM for crypto, London accepted, RTH for equity/futures.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import (
    AssetClass,
    KillZoneEvent,
    OHLCVBar,
    SessionLevels,
    SessionType,
    SweepEvent,
    VWAPValues,
)
from sniper_data.pattern_detection.context import get_kill_zone
from sniper_data.setup_detection.atr import atr, stop_beyond
from sniper_data.setup_detection.candidate import SetupCandidate, risk_reward, score_conviction
from sniper_data.setup_detection.candles import displacement
from sniper_data.setup_detection.context import band_tagged, get_session, get_session_vwap, kill_zone_active
from sniper_data.setup_detection.params import SetupParams, load_setup_params

SETUP_NUMBER = 3
SETUP_TYPE = "po3_judas"


def accumulation_session(asset_class: AssetClass | str, *, preferred: str = "asia") -> SessionType:
    """Asia by default; Globex is optional for futures when Asia is absent."""
    name = asset_class.value if isinstance(asset_class, AssetClass) else str(asset_class)
    if preferred == "globex":
        return SessionType.GLOBEX
    if name == "futures" and preferred == "asia":
        return SessionType.ASIA
    return SessionType(preferred) if preferred in {e.value for e in SessionType} else SessionType.ASIA


def manipulation_zones(asset_class: AssetClass | str, *, default_kz: str = "ny_am") -> set[str]:
    """NY AM by default. Crypto may use either NY AM or London."""
    name = asset_class.value if isinstance(asset_class, AssetClass) else str(asset_class)
    allowed = {default_kz}
    if name == "crypto":
        allowed.add(SessionType.LONDON.value)
        allowed.add(SessionType.NY_AM.value)
    return allowed


@dataclass
class _Pending:
    sweep: SweepEvent
    accum: SessionLevels
    wick: float
    bars_since: int = 0
    fired: bool = False


@dataclass
class _Sym:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=80))
    last_vwap: VWAPValues | None = None
    last_kz: KillZoneEvent | None = None
    pending: list[_Pending] = field(default_factory=list)
    accum: SessionLevels | None = None


def _tf(bar: OHLCVBar) -> str | None:
    tf = bar.timeframe.value if hasattr(bar.timeframe, "value") else str(bar.timeframe)
    return tf if tf in {"1m", "5m", "15m"} else None


def _klass(value) -> AssetClass:
    return value if isinstance(value, AssetClass) else AssetClass(value)


class JudasDetector:
    def __init__(self, store: StateStore, *, params: SetupParams | None = None) -> None:
        self.store = store
        self.params = params or load_setup_params()
        self._state: dict[str, _Sym] = defaultdict(_Sym)

    def on_vwap(self, snap: VWAPValues) -> None:
        anchor = snap.anchor_type.value if hasattr(snap.anchor_type, "value") else str(snap.anchor_type)
        if anchor == "session":
            self._state[snap.symbol].last_vwap = snap

    def on_session(self, levels: SessionLevels) -> None:
        want = accumulation_session(levels.asset_class, preferred=self.params.s3_accum_session)
        if levels.session_type == want or (
            _klass(levels.asset_class) == AssetClass.FUTURES and levels.session_type == SessionType.GLOBEX
        ):
            if self._state[levels.symbol].accum is None or levels.session_type == want:
                self._state[levels.symbol].accum = levels

    def on_kill_zone(self, event: KillZoneEvent) -> None:
        self._state[event.symbol].last_kz = event

    def on_sweep(self, event: SweepEvent) -> None:
        st = self._state[event.symbol]
        accum = st.accum
        if accum is None:
            return
        if not self._matches_accum(event, accum):
            return
        wick = event.swept_level
        st.pending.append(_Pending(sweep=event, accum=accum, wick=wick))

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        tf = _tf(bar)
        if tf is None:
            return []
        st = self._state[bar.symbol]
        st.bars.append(bar)
        vwap = st.last_vwap or await get_session_vwap(self.store, bar.symbol)
        if vwap is not None:
            st.last_vwap = vwap
        zone = st.last_kz or await get_kill_zone(self.store, bar.symbol)
        if zone is not None:
            st.last_kz = zone
        if st.accum is None:
            preferred = accumulation_session(bar.asset_class, preferred=self.params.s3_accum_session)
            st.accum = await get_session(self.store, bar.symbol, preferred)
            if st.accum is None and _klass(bar.asset_class) == AssetClass.FUTURES:
                st.accum = await get_session(self.store, bar.symbol, SessionType.GLOBEX)

        if st.accum is not None:
            self._maybe_arm_from_bar(st, bar, st.accum)

        if not self._in_manipulation(bar, zone):
            return []
        if vwap is None or st.accum is None:
            return []

        atr_val = atr(st.bars, self.params.atr_period) or 0.0
        min_body = self.params.s3_displacement_min_body_atr * atr_val

        out: list[SetupCandidate] = []
        for pending in st.pending:
            if pending.fired:
                continue
            pending.bars_since += 1
            if pending.bars_since > self.params.s3_max_bars_sweep_to_displace:
                pending.fired = True
                continue
            if pending.sweep.side == "sell":
                pending.wick = max(pending.wick, bar.high)
                toward_up = False
            else:
                pending.wick = min(pending.wick, bar.low)
                toward_up = True
            if not displacement(bar, toward_up=toward_up, min_body=min_body):
                continue
            if not toward_up and bar.close >= pending.sweep.swept_level:
                continue
            if toward_up and bar.close <= pending.sweep.swept_level:
                continue
            dist_now = abs(bar.close - vwap.vwap)
            dist_wick = abs(pending.wick - vwap.vwap)
            if dist_now >= dist_wick:
                continue
            cand = self._complete(bar, tf, pending, vwap, zone, atr_val)
            if cand is not None:
                pending.fired = True
                out.append(cand)
        return out

    def _matches_accum(self, event: SweepEvent, accum: SessionLevels) -> bool:
        if event.side == "sell":
            return event.swept_level >= accum.high * 0.999 or event.swept_level >= accum.high
        return event.swept_level <= accum.low * 1.001 or event.swept_level <= accum.low

    def _maybe_arm_from_bar(self, st: _Sym, bar: OHLCVBar, accum: SessionLevels) -> None:
        if bar.high > accum.high:
            fake = SweepEvent(
                id=f"swp-asia-high-{bar.symbol}-{bar.close_ts_ms}",
                symbol=bar.symbol,
                asset_class=_klass(bar.asset_class),
                side="sell",
                swept_level=accum.high,
                reclaim=True,
                ts_ms=bar.close_ts_ms,
                confirmed=True,
            )
            if not any(p.sweep.side == "sell" and not p.fired for p in st.pending):
                st.pending.append(_Pending(sweep=fake, accum=accum, wick=bar.high))
        if bar.low < accum.low:
            fake = SweepEvent(
                id=f"swp-asia-low-{bar.symbol}-{bar.close_ts_ms}",
                symbol=bar.symbol,
                asset_class=_klass(bar.asset_class),
                side="buy",
                swept_level=accum.low,
                reclaim=True,
                ts_ms=bar.close_ts_ms,
                confirmed=True,
            )
            if not any(p.sweep.side == "buy" and not p.fired for p in st.pending):
                st.pending.append(_Pending(sweep=fake, accum=accum, wick=bar.low))

    def _in_manipulation(self, bar: OHLCVBar, zone: KillZoneEvent | None) -> bool:
        allowed = manipulation_zones(bar.asset_class, default_kz=self.params.s3_kill_zone)
        if zone is not None and kill_zone_active(zone, ts_ms=bar.close_ts_ms):
            name = zone.kill_zone.value if hasattr(zone.kill_zone, "value") else str(zone.kill_zone)
            return name in allowed
        return False

    def _complete(
        self,
        bar: OHLCVBar,
        tf: str,
        pending: _Pending,
        vwap: VWAPValues,
        zone: KillZoneEvent | None,
        atr_val: float,
    ) -> SetupCandidate | None:
        sweep = pending.sweep
        side = "short" if sweep.side == "sell" else "long"
        entry = bar.close
        buffer = self.params.stop_buffer_atr * atr_val
        stop = stop_beyond(side, pending.wick, buffer)
        target = pending.accum.low if side == "short" else pending.accum.high
        rr = risk_reward(side, entry, stop, target)
        if rr <= 0:
            return None
        tagged = band_tagged(pending.wick, vwap) or band_tagged(sweep.swept_level, vwap)
        if self.params.s3_require_band_tag and tagged is None:
            return None
        kz = kill_zone_active(zone, ts_ms=bar.close_ts_ms)
        conviction = score_conviction(
            confluence=1 + (2 if tagged else 0),
            volume_confirmed=sweep.volume_profile == "aggressive" or bar.volume > 0,
            kill_zone_aligned=kz,
            confirmed_reclaim=bool(sweep.confirmed or sweep.reclaim),
            base=45,
        )
        session = None
        if zone is not None:
            session = zone.kill_zone.value if hasattr(zone.kill_zone, "value") else str(zone.kill_zone)
        ids = [sweep.id]
        if sweep.id:
            ids = [sweep.id]
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
            kill_zone=session,
            notes={"band_tag": tagged, "accum_session": pending.accum.session_type.value},
        )
