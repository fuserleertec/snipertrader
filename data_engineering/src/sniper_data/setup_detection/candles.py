"""Confirmation-candle helpers for Setup 2 (engulfing / pin / reversal)."""

from __future__ import annotations

from collections import deque

from sniper_data.models import OHLCVBar

Side = str  # "long" | "short"


def _body(bar: OHLCVBar) -> float:
    return abs(bar.close - bar.open)


def _range(bar: OHLCVBar) -> float:
    return max(1e-12, bar.high - bar.low)


def is_bullish(bar: OHLCVBar) -> bool:
    return bar.close > bar.open


def is_bearish(bar: OHLCVBar) -> bool:
    return bar.close < bar.open


def bullish_engulfing(prev: OHLCVBar, curr: OHLCVBar) -> bool:
    return is_bearish(prev) and is_bullish(curr) and curr.open <= prev.close and curr.close >= prev.open


def bearish_engulfing(prev: OHLCVBar, curr: OHLCVBar) -> bool:
    return is_bullish(prev) and is_bearish(curr) and curr.open >= prev.close and curr.close <= prev.open


def pin_bar(bar: OHLCVBar, side: Side) -> bool:
    rng = _range(bar)
    body = _body(bar)
    if body * 2 > rng:
        return False
    lower = min(bar.open, bar.close) - bar.low
    upper = bar.high - max(bar.open, bar.close)
    if side == "long":
        return lower >= 2 * body and bar.close >= bar.low + 0.6 * rng
    return upper >= 2 * body and bar.close <= bar.high - 0.6 * rng


def clear_reversal(bar: OHLCVBar, side: Side, zone_low: float, zone_high: float) -> bool:
    """Close back out of the zone in the setup direction after trading it."""
    touched = bar.low <= zone_high and bar.high >= zone_low
    if not touched:
        return False
    if side == "long":
        return is_bullish(bar) and bar.close >= zone_low and bar.close > bar.open
    return is_bearish(bar) and bar.close <= zone_high and bar.close < bar.open


def displacement(bar: OHLCVBar, *, toward_up: bool) -> bool:
    rng = _range(bar)
    body = _body(bar)
    if body < 0.5 * rng:
        return False
    return is_bullish(bar) if toward_up else is_bearish(bar)


def is_confirmation(prev: OHLCVBar | None, curr: OHLCVBar, side: Side, zone_low: float, zone_high: float) -> bool:
    if pin_bar(curr, side) or clear_reversal(curr, side, zone_low, zone_high):
        return True
    if prev is None:
        return False
    return bullish_engulfing(prev, curr) if side == "long" else bearish_engulfing(prev, curr)


def recent_swing_high(bars: deque[OHLCVBar] | list[OHLCVBar], lookback: int = 8) -> float | None:
    window = list(bars)[-lookback:]
    if not window:
        return None
    return max(b.high for b in window)


def recent_swing_low(bars: deque[OHLCVBar] | list[OHLCVBar], lookback: int = 8) -> float | None:
    window = list(bars)[-lookback:]
    if not window:
        return None
    return min(b.low for b in window)
