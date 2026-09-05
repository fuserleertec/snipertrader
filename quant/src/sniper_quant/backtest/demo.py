"""Synthetic OHLCV + signals so CLI / tests run without TimescaleDB."""

from __future__ import annotations

import math

from sniper_quant.backtest.engine import BacktestSignal, EventBacktester
from sniper_quant.models import AssetClass, OHLCVBar, Side
from sniper_quant.setups import SETUP_TYPES

DAY_MS = 86_400_000
HOUR_MS = 3_600_000


def synthetic_daily_bars(
    symbol: str,
    *,
    n: int = 120,
    start_ms: int = 1_700_000_000_000,
    start_price: float = 100.0,
    drift: float = 0.0008,
    vol: float = 0.012,
    asset_class: AssetClass = AssetClass.CRYPTO,
    seed_phase: float = 0.0,
) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    px = start_price
    for i in range(n):
        shock = vol * math.sin(i * 0.35 + seed_phase) + drift
        o = px
        c = max(px * (1 + shock), 0.01)
        hi = max(o, c) * (1 + vol * 0.4)
        lo = min(o, c) * (1 - vol * 0.4)
        ts = start_ms + i * DAY_MS
        bars.append(
            OHLCVBar(
                symbol=symbol,
                asset_class=asset_class,
                timeframe="1d",
                open_ts_ms=ts,
                close_ts_ms=ts + DAY_MS - 1,
                open=o,
                high=hi,
                low=lo,
                close=c,
                volume=1_000 + i,
                n_ticks=10,
            )
        )
        px = c
    return bars


def _scripted_trade(
    *,
    symbol: str,
    setup_type: str,
    side: Side,
    start_ms: int,
    entry: float,
    atr: float,
    win: bool,
    asset_class: AssetClass = AssetClass.CRYPTO,
) -> tuple[list[OHLCVBar], BacktestSignal]:
    """Three hourly bars: setup, then a bar that tags TP or SL (not both)."""
    stop = entry - 2 * atr if side is Side.LONG else entry + 2 * atr
    target = entry + 4 * atr if side is Side.LONG else entry - 4 * atr  # 2R
    bars = [
        OHLCVBar(
            symbol=symbol,
            asset_class=asset_class,
            timeframe="1h",
            open_ts_ms=start_ms,
            close_ts_ms=start_ms + HOUR_MS - 1,
            open=entry,
            high=entry * 1.001,
            low=entry * 0.999,
            close=entry,
            volume=100,
            n_ticks=5,
        )
    ]
    ts2 = start_ms + HOUR_MS
    if side is Side.LONG:
        if win:
            bars.append(
                OHLCVBar(
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="1h",
                    open_ts_ms=ts2,
                    close_ts_ms=ts2 + HOUR_MS - 1,
                    open=entry,
                    high=target + 0.01,
                    low=entry - atr * 0.1,
                    close=target,
                    volume=100,
                    n_ticks=5,
                )
            )
        else:
            bars.append(
                OHLCVBar(
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="1h",
                    open_ts_ms=ts2,
                    close_ts_ms=ts2 + HOUR_MS - 1,
                    open=entry,
                    high=entry + atr * 0.1,
                    low=stop - 0.01,
                    close=stop,
                    volume=100,
                    n_ticks=5,
                )
            )
    else:
        if win:
            bars.append(
                OHLCVBar(
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="1h",
                    open_ts_ms=ts2,
                    close_ts_ms=ts2 + HOUR_MS - 1,
                    open=entry,
                    high=entry + atr * 0.1,
                    low=target - 0.01,
                    close=target,
                    volume=100,
                    n_ticks=5,
                )
            )
        else:
            bars.append(
                OHLCVBar(
                    symbol=symbol,
                    asset_class=asset_class,
                    timeframe="1h",
                    open_ts_ms=ts2,
                    close_ts_ms=ts2 + HOUR_MS - 1,
                    open=entry,
                    high=stop + 0.01,
                    low=entry - atr * 0.1,
                    close=stop,
                    volume=100,
                    n_ticks=5,
                )
            )
    sig = BacktestSignal(
        ts_ms=start_ms + 1,
        symbol=symbol,
        setup_type=setup_type,
        side=side,
        entry=entry,
        atr=atr,
        signal_id=f"demo-{setup_type}-{start_ms}",
    )
    return bars, sig


def demo_universe() -> tuple[list[OHLCVBar], list[BacktestSignal]]:
    """Scripted wins/losses for all six placeholder setups + correlated ETH tape."""
    bars: list[OHLCVBar] = []
    signals: list[BacktestSignal] = []
    start = 1_700_000_000_000
    entry = 100.0
    atr = 1.0
    for i, setup in enumerate(SETUP_TYPES):
        for j, win in enumerate((True, False)):
            side = Side.LONG if j == 0 else Side.SHORT
            ts = start + (i * 2 + j) * 10 * HOUR_MS
            chunk, sig = _scripted_trade(
                symbol="BTCUSDT",
                setup_type=setup,
                side=side,
                start_ms=ts,
                entry=entry,
                atr=atr,
                win=win,
            )
            bars.extend(chunk)
            signals.append(sig)
    # ETH daily tape (for correlation-filter demos / docs); not traded here.
    bars.extend(synthetic_daily_bars("ETHUSDT", start_price=3_000, seed_phase=0.15))
    return bars, signals


def run_inmemory_demo(equity: float = 100_000.0):
    bars, signals = demo_universe()
    result = EventBacktester().run(bars, signals, equity=equity)
    return result


def daily_returns_from_bars(bars: list[OHLCVBar]) -> list[float]:
    ordered = sorted(bars, key=lambda b: b.open_ts_ms)
    out: list[float] = []
    for prev, cur in zip(ordered, ordered[1:]):
        if prev.close:
            out.append((cur.close - prev.close) / prev.close)
    return out
