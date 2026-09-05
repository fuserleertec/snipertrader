"""Fixed-fractional position sizing (default 2% equity risk per trade)."""

from __future__ import annotations


def fixed_fractional_size(
    equity: float,
    risk_fraction: float,
    risk_per_unit: float,
) -> float:
    if equity <= 0:
        raise ValueError("equity must be positive")
    if risk_fraction <= 0:
        raise ValueError("risk_fraction must be positive")
    if risk_per_unit <= 0:
        return 0.0
    return (equity * risk_fraction) / risk_per_unit


def risk_amount(equity: float, risk_fraction: float) -> float:
    return max(equity, 0.0) * max(risk_fraction, 0.0)


def requested_risk(position_size: float, risk_per_unit: float) -> float:
    return max(position_size, 0.0) * max(risk_per_unit, 0.0)
