"""Market Structure Shift detector.

Swing lookback
--------------
``DEFAULT_SWING_LOOKBACK = 5`` (override with ``SWING_LOOKBACK``). A bar
is a confirmed swing high (low) when its high (low) is strictly greater
(less) than the ``lookback`` bars on **each** side.

Locked ``MssEvent`` fields
--------------------------
Bullish MSS: break of the last lower-high after a sell-side sweep
(``trigger_sweep_side=sell``). Bearish MSS: break of the last higher-low
after a buy-side sweep. Sweeps are consumed, never invented.
``timeframe`` is only set for ``1m`` / ``5m`` / ``15m`` (landed schema).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.models import AssetClass, MssEvent, OHLCVBar, SweepEvent
from sniper_data.pattern_detection.ids import make_id

DEFAULT_SWING_LOOKBACK = 5
_MSS_TIMEFRAMES = {"1m", "5m", "15m"}


@dataclass(frozen=True)
class SwingPoint:
    kind: str
    price: float
    ts_ms: int
    index: int


@dataclass
class _Armed:
    sweep: SweepEvent
    last_lh: float | None = None
    last_hl: float | None = None
    prior_swing_high: float | None = None
    prior_swing_low: float | None = None
    fired: bool = False


@dataclass
class _Sym:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=400))
    swings: list[SwingPoint] = field(default_factory=list)
    armed: list[_Armed] = field(default_factory=list)
    next_index: int = 0


class MSSDetector:
    def __init__(self, lookback: int = DEFAULT_SWING_LOOKBACK) -> None:
        if lookback < 1:
            raise ValueError("swing lookback must be >= 1")
        self.lookback = lookback
        self._state: dict[str, _Sym] = defaultdict(_Sym)

    def on_sweep(self, event: SweepEvent) -> None:
        if not event.id:
            raise ValueError("sweep event is missing id")
        st = self._state[event.symbol]
        if any(a.sweep.id == event.id for a in st.armed):
            return
        st.armed.append(
            _Armed(
                sweep=event,
                prior_swing_high=event.swept_level if event.side == "sell" else None,
                prior_swing_low=event.swept_level if event.side == "buy" else None,
            )
        )

    def on_bar(self, bar: OHLCVBar) -> list[MssEvent]:
        st = self._state[bar.symbol]
        st.bars.append(bar)
        idx = st.next_index
        st.next_index += 1
        self._confirm_swings(st, idx)
        out: list[MssEvent] = []
        for armed in st.armed:
            if armed.fired:
                continue
            ev = self._maybe_shift(st, armed, bar)
            if ev is not None:
                armed.fired = True
                out.append(ev)
        return out

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
                if armed.prior_swing_high is not None and price < armed.prior_swing_high:
                    armed.last_lh = price
                armed.prior_swing_high = price
            else:
                if armed.prior_swing_low is not None and price > armed.prior_swing_low:
                    armed.last_hl = price
                armed.prior_swing_low = price

    def _maybe_shift(self, st: _Sym, armed: _Armed, bar: OHLCVBar) -> MssEvent | None:
        sweep = armed.sweep
        swing_high = _last_price(st.swings, "high")
        swing_low = _last_price(st.swings, "low")

        if sweep.side == "sell" and armed.last_lh is not None and bar.high > armed.last_lh:
            return self._event(
                bar,
                "bullish",
                armed.last_lh,
                swing_high if swing_high is not None else bar.high,
                swing_low if swing_low is not None else bar.low,
                sweep,
            )
        if sweep.side == "buy" and armed.last_hl is not None and bar.low < armed.last_hl:
            return self._event(
                bar,
                "bearish",
                armed.last_hl,
                swing_high if swing_high is not None else bar.high,
                swing_low if swing_low is not None else bar.low,
                sweep,
            )
        return None

    def _event(
        self,
        bar: OHLCVBar,
        direction: str,
        broken_level: float,
        swing_high: float | None,
        swing_low: float | None,
        sweep: SweepEvent,
    ) -> MssEvent:
        tf = bar.timeframe.value if hasattr(bar.timeframe, "value") else str(bar.timeframe)
        return MssEvent(
            id=make_id("mss", bar.symbol, tf, bar.close_ts_ms, direction),
            symbol=bar.symbol,
            asset_class=bar.asset_class if isinstance(bar.asset_class, AssetClass) else AssetClass(bar.asset_class),
            ts_ms=bar.close_ts_ms,
            direction=direction,  # type: ignore[arg-type]
            broken_level=broken_level,
            swing_high=swing_high,
            swing_low=swing_low,
            trigger_sweep_id=sweep.id,
            trigger_sweep_side=sweep.side,
            timeframe=tf if tf in _MSS_TIMEFRAMES else None,  # type: ignore[arg-type]
            confirmed=True,
        )


def _last_price(swings: list[SwingPoint], kind: str) -> float | None:
    for sw in reversed(swings):
        if sw.kind == kind:
            return sw.price
    return None
