"""Average True Range — used by Quant walk-forward stop / overlap / displacement gates."""

from __future__ import annotations

from collections.abc import Sequence

from sniper_data.models import OHLCVBar


def true_range(bar: OHLCVBar, prev_close: float | None) -> float:
    hl = bar.high - bar.low
    if prev_close is None:
        return max(hl, 0.0)
    return max(hl, abs(bar.high - prev_close), abs(bar.low - prev_close))


def atr(bars: Sequence[OHLCVBar], period: int = 14, *, exclude_last: bool = True) -> float | None:
    """Simple ATR over the last ``period`` true ranges.

    ``exclude_last`` uses bars prior to the current (in-progress) close so a
    displacement / confirmation candle does not inflate its own ATR gate.
    """
    series = list(bars)
    if exclude_last and len(series) >= 2:
        series = series[:-1]
    if len(series) < 2:
        return None
    window = series[-(period + 1) :]
    trs: list[float] = []
    for i in range(1, len(window)):
        trs.append(true_range(window[i], window[i - 1].close))
    if not trs:
        return None
    use = trs[-period:]
    return sum(use) / len(use)


def stop_beyond(side: str, extreme: float, buffer: float) -> float:
    if side == "long":
        return extreme - abs(buffer)
    return extreme + abs(buffer)
