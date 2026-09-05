"""Tick → 1m / 5m / 15m / 1h / 4h OHLCV bars (UTC-aligned)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sniper_data.models import AssetClass, OHLCVBar, RawTick, Timeframe
from sniper_data.symbols import infer_asset_class

TIMEFRAME_MS: dict[Timeframe, int] = {
    Timeframe.M1: 60_000,
    Timeframe.M5: 5 * 60_000,
    Timeframe.M15: 15 * 60_000,
    Timeframe.H1: 60 * 60_000,
    Timeframe.H4: 4 * 60 * 60_000,
}

Aggressor = Literal["buy", "sell"]


def classify_aggressor(tick: RawTick) -> Aggressor | None:
    """Resolve taker side: explicit aggressor, then is_buyer_maker, then mid.

    Signed trade volume (for ML consumers) = +volume if buy, −volume if sell.
    Mid fallback: price >= (bid+ask)/2 → buy, else sell.
    """
    if tick.aggressor in ("buy", "sell"):
        return tick.aggressor
    if tick.is_buyer_maker is True:
        return "sell"
    if tick.is_buyer_maker is False:
        return "buy"
    if tick.bid is not None and tick.ask is not None:
        mid = (tick.bid + tick.ask) / 2.0
        return "buy" if tick.price >= mid else "sell"
    return None


def signed_volume(tick: RawTick) -> float | None:
    side = classify_aggressor(tick)
    if side is None:
        return None
    return tick.volume if side == "buy" else -tick.volume


def bar_open_ms(ts_ms: int, timeframe: Timeframe) -> int:
    width = TIMEFRAME_MS[timeframe]
    return (ts_ms // width) * width


@dataclass
class _OpenBar:
    timeframe: Timeframe
    open_ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    n_ticks: int
    symbol: str
    asset_class: AssetClass
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    classified: bool = False

    @classmethod
    def from_tick(cls, tick: RawTick, timeframe: Timeframe, klass: AssetClass) -> _OpenBar:
        bar = cls(
            timeframe=timeframe,
            open_ts_ms=bar_open_ms(tick.ts_ms, timeframe),
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            volume=0.0,
            n_ticks=0,
            symbol=tick.symbol,
            asset_class=klass,
        )
        bar.apply(tick)
        return bar

    def apply(self, tick: RawTick) -> None:
        if self.n_ticks == 0:
            self.open = tick.price
            self.high = tick.price
            self.low = tick.price
        else:
            self.high = max(self.high, tick.price)
            self.low = min(self.low, tick.price)
        self.close = tick.price
        self.volume += tick.volume
        self.n_ticks += 1
        side = classify_aggressor(tick)
        if side == "buy":
            self.buy_volume += tick.volume
            self.classified = True
        elif side == "sell":
            self.sell_volume += tick.volume
            self.classified = True

    def close_bar(self) -> OHLCVBar:
        width = TIMEFRAME_MS[self.timeframe]
        return OHLCVBar(
            symbol=self.symbol,
            asset_class=self.asset_class,
            timeframe=self.timeframe,
            open_ts_ms=self.open_ts_ms,
            close_ts_ms=self.open_ts_ms + width,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            n_ticks=self.n_ticks,
            buy_volume=self.buy_volume if self.classified else None,
            sell_volume=self.sell_volume if self.classified else None,
        )


class OHLCVAggregator:
    def __init__(self, timeframes: tuple[Timeframe, ...] | None = None) -> None:
        self.timeframes = timeframes or tuple(Timeframe)
        self._open: dict[tuple[str, Timeframe], _OpenBar] = {}

    def on_tick(self, tick: RawTick) -> list[OHLCVBar]:
        closed: list[OHLCVBar] = []
        klass = tick.asset_class if isinstance(tick.asset_class, AssetClass) else infer_asset_class(tick.symbol)
        for tf in self.timeframes:
            key = (tick.symbol, tf)
            open_ms = bar_open_ms(tick.ts_ms, tf)
            current = self._open.get(key)
            if current is None:
                self._open[key] = _OpenBar.from_tick(tick, tf, klass)
                continue
            if current.open_ts_ms != open_ms:
                closed.append(current.close_bar())
                self._open[key] = _OpenBar.from_tick(tick, tf, klass)
            else:
                current.apply(tick)
        return closed

    def flush(self) -> list[OHLCVBar]:
        bars = [b.close_bar() for b in self._open.values()]
        self._open.clear()
        return bars
