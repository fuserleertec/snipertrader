"""Max daily loss: 3% of equity. New risk cannot consume the remainder."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DailyLossCheck:
    ok: bool
    already_breached: bool
    remaining_risk_budget: float
    max_additional_size: float


def daily_loss_check(
    *,
    equity: float,
    daily_pnl: float,
    new_risk: float,
    risk_per_unit: float,
    max_daily_loss_frac: float = 0.03,
) -> DailyLossCheck:
    limit = max(equity, 0.0) * max(max_daily_loss_frac, 0.0)
    # daily_pnl is negative when the book is down.
    remaining = limit + daily_pnl
    already = remaining <= 1e-12
    if already:
        return DailyLossCheck(
            ok=False,
            already_breached=True,
            remaining_risk_budget=0.0,
            max_additional_size=0.0,
        )
    max_size = remaining / risk_per_unit if risk_per_unit > 0 else 0.0
    ok = new_risk <= remaining + 1e-9
    return DailyLossCheck(
        ok=ok,
        already_breached=False,
        remaining_risk_budget=remaining,
        max_additional_size=max(max_size, 0.0),
    )
