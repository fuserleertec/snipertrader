"""In-memory OHLCV that contains Setups 1–3 so detectors + walk-forward run offline."""

from __future__ import annotations

import math

from sniper_quant.models import AssetClass, OHLCVBar

HOUR_MS = 3_600_000


def _bar(
    symbol: str,
    ts: int,
    o: float,
    h: float,
    l: float,
    c: float,
    volume: float = 100.0,
    timeframe: str = "1h",
) -> OHLCVBar:
    hi = max(o, h, l, c)
    lo = min(o, h, l, c)
    return OHLCVBar(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        timeframe=timeframe,
        open_ts_ms=ts,
        close_ts_ms=ts + HOUR_MS - 1,
        open=o,
        high=hi,
        low=lo,
        close=c,
        volume=volume,
        n_ticks=8,
    )


def _range_block(
    symbol: str,
    start_ms: int,
    n: int,
    mid: float,
    half: float,
    *,
    drift: float = 0.0,
) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    px = mid
    for i in range(n):
        wobble = half * 0.35 * math.sin(i * 0.7)
        o = px
        c = mid + wobble + drift * i
        h = max(o, c) + half * 0.25
        l = min(o, c) - half * 0.25
        bars.append(_bar(symbol, start_ms + i * HOUR_MS, o, h, l, c, volume=120 + i))
        px = c
    return bars


def _sweep_reclaim_long(symbol: str, start_ms: int, mid: float = 100.0) -> list[OHLCVBar]:
    bars = _range_block(symbol, start_ms, 22, mid, 0.8)
    ts = start_ms + 22 * HOUR_MS
    # Sweep below the range, close back above VWAP (~mid).
    bars.append(_bar(symbol, ts, mid, mid + 0.4, mid - 3.2, mid + 0.6, volume=400))
    bars.append(_bar(symbol, ts + HOUR_MS, mid + 0.6, mid + 1.0, mid + 0.3, mid + 0.9, volume=180))
    bars.append(_bar(symbol, ts + 2 * HOUR_MS, mid + 0.9, mid + 2.4, mid + 0.5, mid + 2.1, volume=200))
    bars.append(_bar(symbol, ts + 3 * HOUR_MS, mid + 2.1, mid + 3.2, mid + 1.6, mid + 2.8, volume=160))
    return bars


def _sweep_reclaim_short(symbol: str, start_ms: int, mid: float = 100.0) -> list[OHLCVBar]:
    bars = _range_block(symbol, start_ms, 22, mid, 0.8)
    ts = start_ms + 22 * HOUR_MS
    bars.append(_bar(symbol, ts, mid, mid + 3.2, mid - 0.4, mid - 0.6, volume=400))
    bars.append(_bar(symbol, ts + HOUR_MS, mid - 0.6, mid - 0.3, mid - 1.0, mid - 0.9, volume=180))
    bars.append(_bar(symbol, ts + 2 * HOUR_MS, mid - 0.9, mid - 0.5, mid - 2.4, mid - 2.1, volume=200))
    bars.append(_bar(symbol, ts + 3 * HOUR_MS, mid - 2.1, mid - 1.6, mid - 3.2, mid - 2.8, volume=160))
    return bars


def _fvg_long(symbol: str, start_ms: int, mid: float = 100.0) -> list[OHLCVBar]:
    bars = _range_block(symbol, start_ms, 18, mid, 0.6)
    ts = start_ms + 18 * HOUR_MS
    # left.high < right.low → bullish FVG overlapping VWAP near mid.
    bars.append(_bar(symbol, ts, mid - 0.2, mid + 0.15, mid - 0.4, mid - 0.1, volume=140))  # left
    bars.append(_bar(symbol, ts + HOUR_MS, mid, mid + 1.8, mid - 0.1, mid + 1.6, volume=260))  # displacement
    bars.append(_bar(symbol, ts + 2 * HOUR_MS, mid + 1.6, mid + 2.0, mid + 0.9, mid + 1.3, volume=180))  # right
    bars.append(_bar(symbol, ts + 3 * HOUR_MS, mid + 1.3, mid + 2.6, mid + 1.1, mid + 2.4, volume=170))
    bars.append(_bar(symbol, ts + 4 * HOUR_MS, mid + 2.4, mid + 3.4, mid + 2.0, mid + 3.1, volume=150))
    return bars


def _fvg_short(symbol: str, start_ms: int, mid: float = 100.0) -> list[OHLCVBar]:
    bars = _range_block(symbol, start_ms, 18, mid, 0.6)
    ts = start_ms + 18 * HOUR_MS
    bars.append(_bar(symbol, ts, mid + 0.2, mid + 0.4, mid - 0.15, mid + 0.1, volume=140))
    bars.append(_bar(symbol, ts + HOUR_MS, mid, mid + 0.1, mid - 1.8, mid - 1.6, volume=260))
    bars.append(_bar(symbol, ts + 2 * HOUR_MS, mid - 1.6, mid - 0.9, mid - 2.0, mid - 1.3, volume=180))
    bars.append(_bar(symbol, ts + 3 * HOUR_MS, mid - 1.3, mid - 1.1, mid - 2.6, mid - 2.4, volume=170))
    bars.append(_bar(symbol, ts + 4 * HOUR_MS, mid - 2.4, mid - 2.0, mid - 3.4, mid - 3.1, volume=150))
    return bars


def _po3_long(symbol: str, start_ms: int, mid: float = 100.0) -> list[OHLCVBar]:
    bars = _range_block(symbol, start_ms, 14, mid, 0.9)
    ts = start_ms + 14 * HOUR_MS
    # Judas: sweep range low, close through midpoint.
    bars.append(_bar(symbol, ts, mid - 0.2, mid + 0.8, mid - 3.4, mid + 1.1, volume=420))
    bars.append(_bar(symbol, ts + HOUR_MS, mid + 1.1, mid + 1.6, mid + 0.7, mid + 1.4, volume=190))
    bars.append(_bar(symbol, ts + 2 * HOUR_MS, mid + 1.4, mid + 3.0, mid + 1.0, mid + 2.7, volume=200))
    bars.append(_bar(symbol, ts + 3 * HOUR_MS, mid + 2.7, mid + 3.6, mid + 2.2, mid + 3.3, volume=160))
    return bars


def _po3_short(symbol: str, start_ms: int, mid: float = 100.0) -> list[OHLCVBar]:
    bars = _range_block(symbol, start_ms, 14, mid, 0.9)
    ts = start_ms + 14 * HOUR_MS
    bars.append(_bar(symbol, ts, mid + 0.2, mid + 3.4, mid - 0.8, mid - 1.1, volume=420))
    bars.append(_bar(symbol, ts + HOUR_MS, mid - 1.1, mid - 0.7, mid - 1.6, mid - 1.4, volume=190))
    bars.append(_bar(symbol, ts + 2 * HOUR_MS, mid - 1.4, mid - 1.0, mid - 3.0, mid - 2.7, volume=200))
    bars.append(_bar(symbol, ts + 3 * HOUR_MS, mid - 2.7, mid - 2.2, mid - 3.6, mid - 3.3, volume=160))
    return bars


def _noise(symbol: str, start_ms: int, n: int, mid: float) -> list[OHLCVBar]:
    return _range_block(symbol, start_ms, n, mid, 0.45, drift=0.0)


_PATTERN_CYCLE = (
    _sweep_reclaim_long,
    _fvg_long,
    _po3_long,
    _sweep_reclaim_short,
    _fvg_short,
    _po3_short,
)


def synthetic_setup_tape(
    symbol: str = "BTCUSDT",
    *,
    cycles: int = 12,
    start_ms: int = 1_700_000_000_000,
    start_price: float = 100.0,
    timeframe: str = "1h",
) -> list[OHLCVBar]:
    """Concatenate patterned blocks so each walk-forward fold has all three setups."""
    bars: list[OHLCVBar] = []
    ts = start_ms
    px = start_price
    for cycle in range(cycles):
        pad = _noise(symbol, ts, 6, px)
        for b in pad:
            b.timeframe = timeframe
        bars.extend(pad)
        ts += 6 * HOUR_MS
        builder = _PATTERN_CYCLE[cycle % len(_PATTERN_CYCLE)]
        chunk = builder(symbol, ts, px)
        for b in chunk:
            b.timeframe = timeframe
        bars.extend(chunk)
        ts = chunk[-1].open_ts_ms + HOUR_MS
        px = chunk[-1].close
    return bars
