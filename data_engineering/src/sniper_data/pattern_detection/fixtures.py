"""Deterministic ICT bar sequences for tests and ``sniper-data patterns --replay``."""

from __future__ import annotations

from sniper_data.models import (
    AssetClass,
    OHLCVBar,
    SessionLevels,
    SessionType,
    SweepEvent,
    Timeframe,
)

TF = Timeframe.M1
SYM = "BTCUSDT"
KLASS = AssetClass.CRYPTO
T0 = 1_717_502_400_000
BAR_MS = 60_000


def bar(
    i: int,
    o: float,
    h: float,
    l: float,
    c: float,
    volume: float,
    *,
    buy: float | None = None,
    sell: float | None = None,
    symbol: str = SYM,
    timeframe: Timeframe = TF,
) -> OHLCVBar:
    if buy is None and sell is None:
        if c >= o:
            buy, sell = volume, 0.0
        else:
            buy, sell = 0.0, volume
    return OHLCVBar(
        symbol=symbol,
        asset_class=KLASS,
        timeframe=timeframe,
        open_ts_ms=T0 + i * BAR_MS,
        close_ts_ms=T0 + (i + 1) * BAR_MS,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=volume,
        n_ticks=max(1, int(volume)),
        buy_volume=buy,
        sell_volume=sell,
    )


def london_session(high: float = 100.0, low: float = 90.0) -> SessionLevels:
    return SessionLevels(
        symbol=SYM,
        asset_class=KLASS,
        session_type=SessionType.LONDON,
        session_start_ms=T0 - 3_600_000,
        session_end_ms=T0 + 10 * 3_600_000,
        open=95.0,
        high=high,
        low=low,
        close=96.0,
        volume=1_000.0,
        updated_ts_ms=T0,
    )


def range_bars(n: int = 6, volume: float = 100.0) -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    for i in range(n):
        if i % 2 == 0:
            out.append(bar(i, 95, 99, 94, 98, volume, buy=volume * 0.6, sell=volume * 0.4))
        else:
            out.append(bar(i, 98, 99, 91, 93, volume, buy=volume * 0.35, sell=volume * 0.65))
    return out


def sell_side_sweep_sequence(*, sweep_volume: float) -> list[OHLCVBar]:
    bars = range_bars(6, volume=100.0)
    bars.append(bar(6, 99, 101.5, 98.5, 101.0, sweep_volume, buy=0.0, sell=sweep_volume))
    bars.append(bar(7, 100.5, 101.0, 96.0, 97.0, 250.0, buy=0.0, sell=250.0))
    return bars


def buy_side_sweep_sequence(*, sweep_volume: float) -> list[OHLCVBar]:
    bars = range_bars(6, volume=100.0)
    bars.append(bar(6, 91, 92, 88.0, 88.5, sweep_volume, buy=sweep_volume, sell=0.0))
    bars.append(bar(7, 89, 94.0, 88.5, 93.0, 250.0, buy=250.0, sell=0.0))
    return bars


def fvg_create_and_fill() -> list[OHLCVBar]:
    return [
        bar(0, 99, 100, 98, 99.5, 50),
        bar(1, 99.5, 105, 99.4, 104, 80),
        bar(2, 104, 106, 102, 105, 60),
        bar(3, 105, 105.5, 101, 102, 40),
    ]


def mss_after_sell_sweep_bars() -> tuple[SweepEvent, list[OHLCVBar]]:
    sweep = SweepEvent(
        id="swp-fixture-sell",
        symbol=SYM,
        asset_class=KLASS,
        side="sell",
        swept_level=100.0,
        reclaim=True,
        ts_ms=T0,
        volume_profile="aggressive",
        delta_divergence=True,
        time_to_reclaim_ms=60_000,
        confirmed=True,
    )
    seq = [
        (90, 90, 88, 89),
        (89, 92, 88.5, 91),
        (91, 95, 90, 94),
        (94, 93, 89, 90),
        (90, 91, 88, 89),
        (89, 96, 88, 95),
    ]
    bars = [bar(i, o, h, l, c, 50.0) for i, (o, h, l, c) in enumerate(seq)]
    return sweep, bars


def mss_after_buy_sweep_bars() -> tuple[SweepEvent, list[OHLCVBar]]:
    sweep = SweepEvent(
        id="swp-fixture-buy",
        symbol=SYM,
        asset_class=KLASS,
        side="buy",
        swept_level=90.0,
        reclaim=True,
        ts_ms=T0,
        volume_profile="aggressive",
        delta_divergence=True,
        time_to_reclaim_ms=60_000,
        confirmed=True,
    )
    seq = [
        (101, 102, 100, 101),
        (101, 101.5, 98, 99),
        (99, 100, 92, 93),
        (93, 97, 96, 96.5),
        (96.5, 98, 97, 97.5),
        (97, 98, 91, 92),
    ]
    bars = [bar(i, o, h, l, c, 50.0) for i, (o, h, l, c) in enumerate(seq)]
    return sweep, bars


def swing_high_sequence(*, lookback: int = 2) -> list[OHLCVBar]:
    """Confirm a swing high at bar ``lookback`` once ``lookback`` bars close on each side."""
    n = lookback
    out: list[OHLCVBar] = []
    for i in range(2 * n + 1):
        if i == n:
            out.append(bar(i, 108, 120, 107, 118, 80))
        else:
            out.append(bar(i, 100 + i * 0.2, 103 + i * 0.1, 99, 101, 40))
    return out


def swing_low_sequence(*, lookback: int = 2) -> list[OHLCVBar]:
    """Confirm a swing low at bar ``lookback`` once ``lookback`` bars close on each side."""
    n = lookback
    out: list[OHLCVBar] = []
    for i in range(2 * n + 1):
        if i == n:
            out.append(bar(i, 92, 93, 80, 82, 80))
        else:
            out.append(bar(i, 100 - i * 0.2, 101, 97 - i * 0.1, 99, 40))
    return out


def order_block_displacement() -> list[OHLCVBar]:
    return [
        bar(0, 100, 101, 99.5, 100.2, 40),
        bar(1, 100.2, 100.4, 99.8, 100.0, 35),
        bar(2, 100.0, 100.1, 98.8, 99.0, 45),
        bar(3, 99.1, 104.0, 99.0, 103.5, 200),
    ]
