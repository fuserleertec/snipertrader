"""Shared TP/SL evaluation. Same-bar SL+TP → SL wins (conservative)."""

from __future__ import annotations

from sniper_quant.models import OHLCVBar, Side, SignalStatus


def bar_exit(
    *,
    side: Side | str,
    stop: float,
    target: float,
    bar: OHLCVBar,
) -> tuple[float | None, SignalStatus | None]:
    """Return ``(exit_px, status)`` if this bar tags stop or target."""
    side = Side(side)
    if side is Side.LONG:
        hit_sl = bar.low <= stop
        hit_tp = bar.high >= target
        if hit_sl:
            return stop, SignalStatus.SL_HIT
        if hit_tp:
            return target, SignalStatus.TP_HIT
        return None, None
    hit_sl = bar.high >= stop
    hit_tp = bar.low <= target
    if hit_sl:
        return stop, SignalStatus.SL_HIT
    if hit_tp:
        return target, SignalStatus.TP_HIT
    return None, None


def r_multiple_achieved(*, side: Side | str, entry: float, stop: float, exit_px: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    side = Side(side)
    if side is Side.LONG:
        return (exit_px - entry) / risk
    return (entry - exit_px) / risk


def outcome_from_status(status: SignalStatus) -> str | None:
    if status is SignalStatus.TP_HIT:
        return "win"
    if status is SignalStatus.SL_HIT:
        return "loss"
    if status is SignalStatus.CANCELLED:
        return "cancelled"
    return None
