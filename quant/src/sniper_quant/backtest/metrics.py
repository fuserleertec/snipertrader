from __future__ import annotations

import math
import statistics

from sniper_quant.models import BacktestMetrics, SignalStatus, TradeRecord


def max_drawdown(equity_curve: list[float]) -> float:
    """Peak-to-trough drawdown as a positive fraction of the peak."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def sharpe_ratio(daily_returns: list[float], periods_per_year: int = 252) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mu = statistics.mean(daily_returns)
    sd = statistics.stdev(daily_returns)
    if sd <= 0:
        return 0.0
    return (mu / sd) * math.sqrt(periods_per_year)


def compute_metrics(
    trades: list[TradeRecord],
    *,
    starting_equity: float,
    ending_equity: float,
    equity_curve: list[float],
    daily_returns: list[float],
) -> BacktestMetrics:
    closed = [t for t in trades if t.status in {SignalStatus.TP_HIT, SignalStatus.SL_HIT} and t.pnl is not None]
    wins = [t for t in closed if (t.pnl or 0) > 0]
    losses = [t for t in closed if (t.pnl or 0) <= 0]
    n = len(closed)
    win_rate = (len(wins) / n) if n else 0.0
    rr_vals = [t.r_multiple for t in closed if t.r_multiple is not None]
    avg_rr = statistics.mean(rr_vals) if rr_vals else 0.0
    net = sum(t.pnl or 0.0 for t in closed)
    return BacktestMetrics(
        win_rate=win_rate,
        avg_rr=avg_rr,
        sharpe=sharpe_ratio(daily_returns),
        max_drawdown=max_drawdown(equity_curve),
        n_trades=n,
        n_wins=len(wins),
        n_losses=len(losses),
        net_pnl=net,
        ending_equity=ending_equity,
        starting_equity=starting_equity,
    )
