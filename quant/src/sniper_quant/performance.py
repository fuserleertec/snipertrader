"""Live performance summary from stored signal outcomes / realized_r."""

from __future__ import annotations

import time
from collections import defaultdict

from sniper_quant.backtest.metrics import max_drawdown, sharpe_ratio
from sniper_quant.models import (
    PerformanceBucket,
    PerformanceSummary,
    SignalStatus,
    StoredSignal,
)
from sniper_quant.setups import PERFORMANCE_BY_SETUP_KEYS, product_key_for

DAY_MS = 24 * 60 * 60 * 1000
WEEK_MS = 7 * DAY_MS


def _setup_name(row: StoredSignal) -> str:
    setup = row.setup_type
    return setup.value if hasattr(setup, "value") else str(setup)


def _is_closed(row: StoredSignal) -> bool:
    return row.status in {SignalStatus.TP_HIT, SignalStatus.SL_HIT}


def _realized(row: StoredSignal) -> float | None:
    if not _is_closed(row):
        return None
    return row.r_multiple


def _utc_day(ts_ms: int) -> int:
    return ts_ms // DAY_MS


def _bucket(
    rows: list[StoredSignal],
    *,
    now_ms: int,
    risk_fraction: float,
    setup_type: str,
) -> PerformanceBucket:
    closed = [r for r in rows if _is_closed(r)]
    realized = [v for r in closed if (v := _realized(r)) is not None]
    wins = [r for r in closed if r.outcome == "win" or r.status is SignalStatus.TP_HIT]
    n_closed = len(closed)
    win_rate = (len(wins) / n_closed) if n_closed else 0.0
    average_rr = (sum(realized) / len(realized)) if realized else 0.0

    by_day: dict[int, float] = defaultdict(float)
    equity = 1.0
    curve = [equity]
    for row in sorted(closed, key=lambda r: r.closed_ts_ms or r.ts_ms):
        r_mult = _realized(row) or 0.0
        equity *= 1.0 + risk_fraction * r_mult
        curve.append(equity)
        by_day[_utc_day(row.closed_ts_ms or row.ts_ms)] += r_mult
    daily = [by_day[k] for k in sorted(by_day)]

    today_start = now_ms - (now_ms % DAY_MS)
    week_start = now_ms - WEEK_MS
    return PerformanceBucket(
        setup_type=setup_type,
        product_key=product_key_for(setup_type) or setup_type,
        win_rate=win_rate,
        average_rr=average_rr,
        sharpe_ratio=sharpe_ratio(daily) if len(daily) >= 2 else 0.0,
        max_drawdown_pct=max_drawdown(curve),
        n_signals=len(rows),
        n_closed=n_closed,
        signals_today=sum(1 for r in rows if r.ts_ms >= today_start),
        signals_week=sum(1 for r in rows if r.ts_ms >= week_start),
    )


def summarize_signals(
    rows: list[StoredSignal],
    *,
    now_ms: int | None = None,
    risk_fraction: float = 0.02,
) -> PerformanceSummary:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    overall = _bucket(rows, now_ms=now, risk_fraction=risk_fraction, setup_type="all")
    grouped: dict[str, list[StoredSignal]] = {name: [] for name in PERFORMANCE_BY_SETUP_KEYS}
    for row in rows:
        name = _setup_name(row)
        if name in grouped:
            grouped[name].append(row)
    by_setup = {
        name: _bucket(
            grouped.get(name, []),
            now_ms=now,
            risk_fraction=risk_fraction,
            setup_type=name,
        )
        for name in PERFORMANCE_BY_SETUP_KEYS
    }
    closed_chrono = sorted(
        [r for r in rows if _is_closed(r)],
        key=lambda r: r.closed_ts_ms or r.ts_ms,
    )
    last20 = closed_chrono[-20:]
    rolling = None
    if last20:
        wins20 = sum(1 for r in last20 if r.outcome == "win" or r.status is SignalStatus.TP_HIT)
        rolling = wins20 / len(last20)
    drift = rolling is not None and rolling < 0.45
    return PerformanceSummary(
        win_rate=overall.win_rate,
        average_rr=overall.average_rr,
        sharpe_ratio=overall.sharpe_ratio,
        max_drawdown_pct=overall.max_drawdown_pct,
        signals_today=overall.signals_today,
        signals_week=overall.signals_week,
        n_signals=overall.n_signals,
        n_closed=overall.n_closed,
        by_setup=by_setup,
        rolling_win_rate_20=rolling,
        drift_warning=drift,
        drift_note=(
            f"rolling 20-trade win rate {rolling:.1%} < 45%" if drift and rolling is not None else ""
        ),
    )
