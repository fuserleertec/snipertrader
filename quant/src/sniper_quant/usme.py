"""USME-aligned stop-loss and take-profit.

Product sources (no calculator formula existed — see quant/README):

- USME ICT Foundation v3.1 (``usme-v3-1.html``): stop moved from 1× to
  **2× ATR(14)** so 1R is wider and noise-driven stop-outs drop.
- Prop Firm MasterPlan / 30-Day Funded Challenge: **minimum 1:2 R:R**,
  never accept below 1:1.5. T1 at 2R, optional T2 at 3R.
- Structure: when an invalidation / swing level is supplied, the stop is
  placed *beyond* that level (further from entry than both structure and
  the 2× ATR stop).

Defaults used here: SL = 2× ATR(14) beyond entry (or beyond invalidation);
TP = 2R. Fallback ATR when unknown: 1% of |entry|.
"""

from __future__ import annotations

from dataclasses import dataclass

from sniper_quant.models import Side


@dataclass(frozen=True)
class USMELevels:
    entry: float
    stop: float
    target: float
    risk_per_unit: float
    r_multiple: float
    atr_used: float
    source: str


def fallback_atr(entry: float) -> float:
    return max(abs(entry) * 0.01, 1e-9)


def check_provided_levels(
    *,
    side: Side | str,
    entry: float,
    stop: float,
    target: float,
    min_rr: float = 1.5,
) -> USMELevels:
    """Validate ML-supplied entry/stop/target. Does not rewrite prices."""
    side = Side(side)
    if entry <= 0:
        raise ValueError("entry must be positive")
    if side is Side.LONG and stop >= entry:
        raise ValueError("stop must be strictly below entry for a long")
    if side is Side.SHORT and stop <= entry:
        raise ValueError("stop must be strictly above entry for a short")
    if side is Side.LONG and target <= entry:
        raise ValueError("target must be above entry for a long")
    if side is Side.SHORT and target >= entry:
        raise ValueError("target must be below entry for a short")
    risk = abs(entry - stop)
    if risk <= 0:
        raise ValueError("risk_per_unit must be positive")
    rr = abs(target - entry) / risk
    if rr + 1e-12 < min_rr:
        raise ValueError(f"reward:risk {rr:.4f} is below USME minimum {min_rr}")
    return USMELevels(
        entry=entry,
        stop=stop,
        target=target,
        risk_per_unit=risk,
        r_multiple=rr,
        atr_used=0.0,
        source="provided",
    )


def compute_usme_levels(
    *,
    side: Side | str,
    entry: float,
    atr: float | None = None,
    invalidation: float | None = None,
    stop: float | None = None,
    target: float | None = None,
    sl_atr_multiple: float = 2.0,
    tp_r_multiple: float = 2.0,
    min_rr: float = 1.5,
) -> USMELevels:
    side = Side(side)
    if entry <= 0:
        raise ValueError("entry must be positive")

    atr_used = float(atr) if atr is not None and atr > 0 else fallback_atr(entry)
    atr_stop = (
        entry - sl_atr_multiple * atr_used
        if side is Side.LONG
        else entry + sl_atr_multiple * atr_used
    )

    source = "atr_2x"
    if stop is not None:
        computed_stop = float(stop)
        source = "provided_stop"
    elif invalidation is not None:
        buffer = max(atr_used * 0.10, abs(entry) * 0.0005)
        struct_stop = (
            float(invalidation) - buffer if side is Side.LONG else float(invalidation) + buffer
        )
        # Further of structure-beyond vs 2× ATR (more conservative 1R).
        computed_stop = min(struct_stop, atr_stop) if side is Side.LONG else max(struct_stop, atr_stop)
        source = "invalidation_beyond"
    else:
        computed_stop = atr_stop

    if side is Side.LONG and computed_stop >= entry:
        raise ValueError("stop must be strictly below entry for a long")
    if side is Side.SHORT and computed_stop <= entry:
        raise ValueError("stop must be strictly above entry for a short")

    risk = abs(entry - computed_stop)
    if risk <= 0:
        raise ValueError("risk_per_unit must be positive")

    rr = max(float(tp_r_multiple), float(min_rr))
    computed_target = entry + rr * risk if side is Side.LONG else entry - rr * risk

    if target is not None:
        t = float(target)
        on_side = (side is Side.LONG and t > entry) or (side is Side.SHORT and t < entry)
        provided_rr = abs(t - entry) / risk
        if on_side and provided_rr + 1e-12 >= min_rr:
            computed_target = t
            rr = provided_rr
        # else keep engineered 2R target (ignore a too-tight caller target)

    if side is Side.LONG and computed_target <= entry:
        raise ValueError("target must be above entry for a long")
    if side is Side.SHORT and computed_target >= entry:
        raise ValueError("target must be below entry for a short")

    return USMELevels(
        entry=entry,
        stop=computed_stop,
        target=computed_target,
        risk_per_unit=risk,
        r_multiple=abs(computed_target - entry) / risk,
        atr_used=atr_used,
        source=source,
    )


def atr_from_bars(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """Wilder ATR(period). ``closes`` is previous-close aligned with highs/lows."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    window = trs[-period:]
    if not window:
        return None
    return sum(window) / len(window)
