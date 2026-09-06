"""Corrected liquidity-sweep detector (Rev. 1.1).

Locked contract
---------------
* ``side=sell`` → session **high** taken (sell-side liquidity).
* ``side=buy``  → session **low** taken (buy-side liquidity).
* Fields: ``side`` / ``swept_level`` / ``reclaim`` only — no ``direction``
  or ``sweep_level`` aliases.
* **Low volume must not gate detection.** ``volume_profile`` is scored
  after the fact (``aggressive`` | ``low_volume``).
* A sweep is emitted when price breaks the established session extreme
  **and** cumulative delta diverges (computed in-process from
  ``buy_volume − sell_volume``).
* ``confirmed`` / ``reclaim`` flip when a high-volume opposite candle
  closes back inside the pre-sweep session range.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import AssetClass, OHLCVBar, RawTick, SessionLevels, SweepEvent
from sniper_data.pattern_detection.delta import DeltaBook
from sniper_data.pattern_detection.ids import make_id
from sniper_data.sessions import redis_session_key

VolumeProfile = Literal["aggressive", "low_volume"]

_VOLUME_LOOKBACK = 20
_RECLAIM_VOLUME_MULT = 1.2


@dataclass
class _PendingSweep:
    event: SweepEvent
    swept_level: float
    session_high: float
    session_low: float


@dataclass
class _SymbolState:
    ref_high: float | None = None
    ref_low: float | None = None
    session_type: str | None = None
    session_start_ms: int | None = None
    cum_delta: float = 0.0
    last_high_cum_delta: float | None = None
    last_low_cum_delta: float | None = None
    volumes: deque[float] = field(default_factory=lambda: deque(maxlen=_VOLUME_LOOKBACK))
    pending: _PendingSweep | None = None
    emitted_ids: set[str] = field(default_factory=set)


def _high_delta_divergence(bar_d: float, new_cum: float, last_high_cum: float | None) -> bool:
    if bar_d < 0:
        return True
    if last_high_cum is not None and new_cum < last_high_cum:
        return True
    return False


def _low_delta_divergence(bar_d: float, new_cum: float, last_low_cum: float | None) -> bool:
    if bar_d > 0:
        return True
    if last_low_cum is not None and new_cum > last_low_cum:
        return True
    return False


class SweepDetector:
    def __init__(self, store: StateStore | None = None) -> None:
        self.store = store
        self._state: dict[str, _SymbolState] = {}
        self.delta = DeltaBook()

    def on_tick(self, tick: RawTick) -> None:
        """Classify signed tick volume in-process. Never persisted."""
        self.delta.on_tick(tick)

    def _st(self, symbol: str) -> _SymbolState:
        return self._state.setdefault(symbol, _SymbolState())

    def on_session(self, levels: SessionLevels) -> None:
        st = self._st(levels.symbol)
        if st.session_start_ms != levels.session_start_ms:
            st.ref_high = levels.high
            st.ref_low = levels.low
            st.session_start_ms = levels.session_start_ms
            st.session_type = levels.session_type.value
            st.pending = None
            st.cum_delta = 0.0
            st.last_high_cum_delta = None
            st.last_low_cum_delta = None
            return
        st.session_type = levels.session_type.value

    async def _hydrate_session(self, bar: OHLCVBar) -> None:
        st = self._st(bar.symbol)
        if st.ref_high is not None or self.store is None:
            return
        keys = await self.store.scan(f"session:{bar.symbol}:*")
        if not keys and st.session_type:
            keys = [redis_session_key(bar.symbol, st.session_type)]
        for key in keys:
            payload = await self.store.get(key)
            if not isinstance(payload, dict):
                continue
            high = payload.get("high")
            low = payload.get("low")
            if high is None or low is None:
                continue
            st.ref_high = float(high)
            st.ref_low = float(low)
            st.session_type = payload.get("session_type", st.session_type)
            st.session_start_ms = payload.get("session_start_ms", st.session_start_ms)
            return

    def _score_volume_profile(self, st: _SymbolState, volume: float) -> VolumeProfile:
        """Score only. Callers must not use the result to skip a sweep."""
        prior = list(st.volumes)
        if len(prior) < 3:
            return "aggressive"
        avg = sum(prior) / len(prior)
        return "aggressive" if volume >= avg else "low_volume"

    def _reclaim_volume_ok(self, st: _SymbolState, volume: float) -> bool:
        prior = list(st.volumes)
        if len(prior) < 3:
            return True
        avg = sum(prior) / len(prior)
        return volume >= avg * _RECLAIM_VOLUME_MULT

    async def on_bar(self, bar: OHLCVBar) -> list[SweepEvent]:
        await self._hydrate_session(bar)
        st = self._st(bar.symbol)
        out: list[SweepEvent] = []

        # Prefer bar buy_volume − sell_volume; tick signed-volume is fallback only.
        resolved = self.delta.consume_bar(bar)
        bar_d = 0.0 if resolved is None else resolved
        new_cum = st.cum_delta + bar_d

        if st.pending is not None:
            updated = self._try_reclaim(st, bar)
            if updated is not None:
                out.append(updated)

        if st.ref_high is None or st.ref_low is None:
            st.ref_high = bar.high
            st.ref_low = bar.low
            st.cum_delta = new_cum
            st.volumes.append(bar.volume)
            return out

        created = self._detect_break(st, bar, bar_d, new_cum)
        if created is not None:
            out.append(created)
        elif st.pending is None:
            if bar.high >= st.ref_high:
                st.last_high_cum_delta = new_cum
            if bar.low <= st.ref_low:
                st.last_low_cum_delta = new_cum
            st.ref_high = max(st.ref_high, bar.high)
            st.ref_low = min(st.ref_low, bar.low)

        st.cum_delta = new_cum
        st.volumes.append(bar.volume)
        return out

    def _detect_break(
        self,
        st: _SymbolState,
        bar: OHLCVBar,
        bar_d: float,
        new_cum: float,
    ) -> SweepEvent | None:
        assert st.ref_high is not None and st.ref_low is not None
        sell_break = bar.high > st.ref_high
        buy_break = bar.low < st.ref_low
        if not sell_break and not buy_break:
            return None

        # Profile is computed for the payload only and is not a condition.
        profile = self._score_volume_profile(st, bar.volume)

        if sell_break and _high_delta_divergence(bar_d, new_cum, st.last_high_cum_delta):
            return self._emit(
                st,
                bar,
                side="sell",
                swept_level=st.ref_high,
                profile=profile,
                session_high=st.ref_high,
                session_low=st.ref_low,
            )
        if buy_break and _low_delta_divergence(bar_d, new_cum, st.last_low_cum_delta):
            return self._emit(
                st,
                bar,
                side="buy",
                swept_level=st.ref_low,
                profile=profile,
                session_high=st.ref_high,
                session_low=st.ref_low,
            )
        return None

    def _emit(
        self,
        st: _SymbolState,
        bar: OHLCVBar,
        *,
        side: Literal["buy", "sell"],
        swept_level: float,
        profile: VolumeProfile,
        session_high: float,
        session_low: float,
    ) -> SweepEvent:
        event_id = make_id("swp", bar.symbol, bar.timeframe.value, bar.close_ts_ms, side)
        event = SweepEvent(
            id=event_id,
            symbol=bar.symbol,
            asset_class=bar.asset_class if isinstance(bar.asset_class, AssetClass) else AssetClass(bar.asset_class),
            side=side,
            swept_level=swept_level,
            reclaim=False,
            ts_ms=bar.close_ts_ms,
            volume_profile=profile,
            delta_divergence=True,
            time_to_reclaim_ms=None,
            confirmed=False,
        )
        st.pending = _PendingSweep(
            event=event,
            swept_level=swept_level,
            session_high=session_high,
            session_low=session_low,
        )
        st.emitted_ids.add(event_id)
        return event

    def _try_reclaim(self, st: _SymbolState, bar: OHLCVBar) -> SweepEvent | None:
        pending = st.pending
        if pending is None:
            return None
        ev = pending.event
        inside = pending.session_low <= bar.close <= pending.session_high
        if ev.side == "sell":
            back = bar.close < pending.swept_level
        else:
            back = bar.close > pending.swept_level
        if not (inside and back):
            return None
        if not self._reclaim_volume_ok(st, bar.volume):
            return None
        delay = max(0, bar.close_ts_ms - ev.ts_ms)
        updated = ev.model_copy(
            update={
                "reclaim": True,
                "confirmed": True,
                "time_to_reclaim_ms": delay,
            }
        )
        st.pending = None
        st.ref_high = max(pending.session_high, bar.high)
        st.ref_low = min(pending.session_low, bar.low)
        return updated
