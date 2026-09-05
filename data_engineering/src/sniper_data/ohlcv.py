"""Tick → 1m / 5m / 15m / 1h / 4h OHLCV bars (UTC-aligned)."""

from __future__ import annotations

from dataclasses import dataclass

from sniper_data.models import AssetClass, OHLCVBar, RawTick, Timeframe
from sniper_data.symbols import infer_asset_class

TIMEFRAME_MS: dict[Timeframe, int] = {
    Timeframe.M1: 60_000,
    Timeframe.M5: 5 * 60_000,
    Timeframe.M15: 15 * 60_000,
    Timeframe.H1: 60 * 60_000,
    Timeframe.H4: 4 * 60 * 60_000,
}


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

    def apply(self, price: float, volume: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume
        self.n_ticks += 1

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
                self._open[key] = _OpenBar(
                    timeframe=tf,
                    open_ts_ms=open_ms,
                    open=tick.price,
                    high=tick.price,
                    low=tick.price,
                    close=tick.price,
                    volume=tick.volume,
                    n_ticks=1,
                    symbol=tick.symbol,
                    asset_class=klass,
                )
                continue
            if current.open_ts_ms != open_ms:
                closed.append(current.close_bar())
                self._open[key] = _OpenBar(
                    timeframe=tf,
                    open_ts_ms=open_ms,
                    open=tick.price,
                    high=tick.price,
                    low=tick.price,
                    close=tick.price,
                    volume=tick.volume,
                    n_ticks=1,
                    symbol=tick.symbol,
                    asset_class=klass,
                )
            else:
                current.apply(tick.price, tick.volume)
        return closed

    def flush(self) -> list[OHLCVBar]:
        bars = [b.close_bar() for b in self._open.values()]
        self._open.clear()
        return bars
