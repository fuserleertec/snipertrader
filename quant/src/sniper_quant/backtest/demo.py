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


def demo_universe() -> tuple[list[OHLCVBar], list[BacktestSignal]]:
    """BTC + ETH with overlapping drift so correlation is meaningful, plus six setups."""
    btc = synthetic_daily_bars("BTCUSDT", start_price=60_000, seed_phase=0.0)
    eth = synthetic_daily_bars("ETHUSDT", start_price=3_000, seed_phase=0.15)
    bars = btc + eth
    signals: list[BacktestSignal] = []
    # Place a signal every ~12 days, cycling the six placeholder setups, alternating side.
    for i, setup in enumerate(SETUP_TYPES * 3):
        idx = 8 + i * 12
        if idx >= len(btc) - 3:
            break
        bar = btc[idx]
        side = Side.LONG if i % 2 == 0 else Side.SHORT
        atr = (bar.high - bar.low) * 2.0
        signals.append(
            BacktestSignal(
                ts_ms=bar.open_ts_ms + HOUR_MS,
                symbol="BTCUSDT",
                setup_type=setup,
                side=side,
                entry=bar.open,
                atr=atr,
                signal_id=f"demo-{setup}-{i}",
            )
        )
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
