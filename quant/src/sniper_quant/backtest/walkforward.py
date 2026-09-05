"""Walk-forward optimization for Setups 1–3 (avoids a single in-sample fit)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sniper_quant.backtest.detectors import (
    DETECTORS,
    PARAM_GRID,
    SETUP_INDEX,
    DetectorParams,
    detect_setup,
)
from sniper_quant.backtest.engine import BacktestResult, EventBacktester
from sniper_quant.backtest.metrics import compute_metrics
from sniper_quant.models import BacktestMetrics, OHLCVBar, TradeRecord


def _score(metrics: BacktestMetrics) -> float:
    """Train objective: reward win rate and avg R, penalize empty books lightly."""
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


def _split_folds(n: int, n_folds: int) -> list[tuple[int, int, int]]:
    """Expanding windows: train [0, cut), test [cut, next).

    Returns list of (train_end, test_start, test_end) exclusive indices.
    """
    if n_folds < 2:
        raise ValueError("n_folds must be >= 2")
    if n < n_folds * 20:
        raise ValueError(f"need more bars for {n_folds} folds (have {n})")
    # First 40% is the initial train; remaining 60% split into n_folds OOS slices.
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


def optimize_params(
    bars: list[OHLCVBar],
    setup_type: str,
    grid: tuple[DetectorParams, ...] = PARAM_GRID,
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


def walk_forward_setup(
    bars: list[OHLCVBar],
    setup_type: str,
    *,
    n_folds: int = 3,
    equity: float = 100_000.0,
    grid: tuple[DetectorParams, ...] = PARAM_GRID,
) -> SetupWalkForward:
    ordered = sorted(bars, key=lambda b: b.open_ts_ms)
    cuts = _split_folds(len(ordered), n_folds)
    folds: list[FoldResult] = []
    oos_trades: list[TradeRecord] = []
    oos_equity = [equity]
    for i, (train_end, test_start, test_end) in enumerate(cuts, start=1):
        train_bars = ordered[:train_end]
        test_bars = ordered[test_start:test_end]
        params, train_metrics = optimize_params(train_bars, setup_type, grid, equity=equity)
        test_signals = detect_setup(setup_type, test_bars, params)
        # Replay test signals on the test window only (no look-ahead into later folds).
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

    daily: list[float] = []
    for a, b in zip(oos_equity, oos_equity[1:]):
        if a:
            daily.append((b - a) / a)
    ending = oos_equity[-1] if oos_equity else equity
    oos = compute_metrics(
        oos_trades,
        starting_equity=equity,
        ending_equity=ending,
        equity_curve=oos_equity,
        daily_returns=daily,
    )
    idx = next((k for k, v in SETUP_INDEX.items() if v == setup_type), 0)
    return SetupWalkForward(
        setup_type=setup_type,
        setup_index=idx,
        folds=folds,
        oos=oos,
        oos_trades=oos_trades,
    )


def walk_forward_setups(
    bars: list[OHLCVBar],
    setup_ids: list[int],
    *,
    n_folds: int = 3,
    equity: float = 100_000.0,
) -> list[SetupWalkForward]:
    results: list[SetupWalkForward] = []
    for sid in setup_ids:
        name = SETUP_INDEX[sid]
        if name not in DETECTORS:
            continue
        results.append(walk_forward_setup(bars, name, n_folds=n_folds, equity=equity))
    return results


def params_as_dict(params: DetectorParams) -> dict:
    return asdict(params)
