"""Walk-forward optimization on locked ML grids + defaults baseline."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sniper_quant.backtest.detectors import DETECTORS, SETUP_INDEX, detect_setup
from sniper_quant.backtest.engine import BacktestResult, EventBacktester
from sniper_quant.backtest.metrics import compute_metrics
from sniper_quant.backtest.params import (
    DEFAULT_PARAMS,
    DetectorParams,
    grid_for,
    orchestrator_grid,
    params_as_dict,
    setup_fields,
)
from sniper_quant.models import BacktestMetrics, OHLCVBar, TradeRecord


def _score(metrics: BacktestMetrics) -> float:
    if metrics.n_trades <= 0:
        return -1.0
    return metrics.win_rate * 2.0 + metrics.avg_rr - metrics.max_drawdown


@dataclass
class FoldResult:
    fold: int
    train_n_bars: int
    test_n_bars: int
    params: DetectorParams
    train: BacktestMetrics
    test: BacktestMetrics
    test_trades: list[TradeRecord]


@dataclass
class SetupWalkForward:
    setup_type: str
    setup_index: int
    folds: list[FoldResult]
    oos: BacktestMetrics
    oos_trades: list[TradeRecord]
    baseline_full: BacktestMetrics
    baseline_oos: BacktestMetrics
    recommended: dict
    grid_size: int


def _split_folds(n: int, n_folds: int) -> list[tuple[int, int, int]]:
    if n_folds < 2:
        raise ValueError("n_folds must be >= 2")
    if n < n_folds * 20:
        raise ValueError(f"need more bars for {n_folds} folds (have {n})")
    first_train = max(int(n * 0.40), n // (n_folds + 1))
    remaining = n - first_train
    slice_len = remaining // n_folds
    folds: list[tuple[int, int, int]] = []
    for i in range(n_folds):
        test_start = first_train + i * slice_len
        test_end = n if i == n_folds - 1 else test_start + slice_len
        folds.append((test_start, test_start, test_end))
    return folds


def _run(bars: list[OHLCVBar], signals, equity: float) -> BacktestResult:
    return EventBacktester().run(bars, signals, equity=equity)


def _metrics_of(trades: list[TradeRecord], equity: float, curve: list[float] | None = None) -> BacktestMetrics:
    eq = curve or [equity]
    daily: list[float] = []
    for a, b in zip(eq, eq[1:]):
        if a:
            daily.append((b - a) / a)
    ending = eq[-1] if eq else equity
    return compute_metrics(
        trades,
        starting_equity=equity,
        ending_equity=ending,
        equity_curve=eq,
        daily_returns=daily,
    )


def optimize_params(
    bars: list[OHLCVBar],
    setup_type: str,
    grid: tuple[DetectorParams, ...],
    *,
    equity: float = 100_000.0,
) -> tuple[DetectorParams, BacktestMetrics]:
    best: DetectorParams | None = None
    best_metrics: BacktestMetrics | None = None
    best_score = float("-inf")
    for params in grid:
        signals = detect_setup(setup_type, bars, params)
        result = _run(bars, signals, equity)
        score = _score(result.metrics)
        if score > best_score:
            best_score = score
            best = params
            best_metrics = result.metrics
    assert best is not None and best_metrics is not None
    return best, best_metrics


def _majority_recommend(folds: list[FoldResult], setup_type: str) -> dict:
    fields = setup_fields(setup_type)
    rec: dict = {}
    for field in fields:
        votes = Counter(getattr(f.params, field) for f in folds)
        rec[field] = votes.most_common(1)[0][0]
    rec["dedupe_window_sec"] = DEFAULT_PARAMS.dedupe_window_sec
    rec["min_conviction"] = DEFAULT_PARAMS.min_conviction
    rec["timeframe"] = DEFAULT_PARAMS.timeframe
    rec["session_vwap_anchor"] = DEFAULT_PARAMS.session_vwap_anchor
    return rec


def walk_forward_setup(
    bars: list[OHLCVBar],
    setup_type: str,
    *,
    n_folds: int = 3,
    equity: float = 100_000.0,
    grid: tuple[DetectorParams, ...] | None = None,
    mode: str = "full",
) -> SetupWalkForward:
    ordered = sorted(bars, key=lambda b: b.open_ts_ms)
    grid = grid or grid_for(setup_type, mode=mode)
    cuts = _split_folds(len(ordered), n_folds)
    folds: list[FoldResult] = []
    oos_trades: list[TradeRecord] = []
    oos_equity = [equity]
    baseline_oos_trades: list[TradeRecord] = []
    baseline_oos_eq = [equity]
    for i, (train_end, test_start, test_end) in enumerate(cuts, start=1):
        train_bars = ordered[:train_end]
        test_bars = ordered[test_start:test_end]
        params, train_metrics = optimize_params(train_bars, setup_type, grid, equity=equity)
        test_signals = detect_setup(setup_type, test_bars, params)
        test_result = _run(test_bars, test_signals, equity)
        folds.append(
            FoldResult(
                fold=i,
                train_n_bars=len(train_bars),
                test_n_bars=len(test_bars),
                params=params,
                train=train_metrics,
                test=test_result.metrics,
                test_trades=test_result.trades,
            )
        )
        oos_trades.extend(test_result.trades)
        if test_result.equity_curve:
            oos_equity.extend(test_result.equity_curve[1:])
        base_sig = detect_setup(setup_type, test_bars, DEFAULT_PARAMS)
        base_res = _run(test_bars, base_sig, equity)
        baseline_oos_trades.extend(base_res.trades)
        if base_res.equity_curve:
            baseline_oos_eq.extend(base_res.equity_curve[1:])

    oos = _metrics_of(oos_trades, equity, oos_equity)
    baseline_oos = _metrics_of(baseline_oos_trades, equity, baseline_oos_eq)
    full_base = _run(ordered, detect_setup(setup_type, ordered, DEFAULT_PARAMS), equity)
    idx = next((k for k, v in SETUP_INDEX.items() if v == setup_type), 0)
    return SetupWalkForward(
        setup_type=setup_type,
        setup_index=idx,
        folds=folds,
        oos=oos,
        oos_trades=oos_trades,
        baseline_full=full_base.metrics,
        baseline_oos=baseline_oos,
        recommended=_majority_recommend(folds, setup_type),
        grid_size=len(grid),
    )


def walk_forward_setups(
    bars: list[OHLCVBar],
    setup_ids: list[int],
    *,
    n_folds: int = 3,
    equity: float = 100_000.0,
    mode: str = "full",
) -> list[SetupWalkForward]:
    results: list[SetupWalkForward] = []
    for sid in setup_ids:
        name = SETUP_INDEX[sid]
        if name not in DETECTORS:
            continue
        results.append(
            walk_forward_setup(bars, name, n_folds=n_folds, equity=equity, mode=mode)
        )
    return results


def sweep_orchestrator(
    bars: list[OHLCVBar],
    setup_type: str,
    *,
    equity: float = 100_000.0,
) -> list[tuple[DetectorParams, BacktestMetrics]]:
    rows: list[tuple[DetectorParams, BacktestMetrics]] = []
    for params in orchestrator_grid():
        result = _run(bars, detect_setup(setup_type, bars, params), equity)
        rows.append((params, result.metrics))
    rows.sort(key=lambda item: _score(item[1]), reverse=True)
    return rows


# Re-export for report / CLI.
__all__ = [
    "FoldResult",
    "SetupWalkForward",
    "optimize_params",
    "params_as_dict",
    "sweep_orchestrator",
    "walk_forward_setup",
    "walk_forward_setups",
]
