from __future__ import annotations

from sniper_quant.models import OpenPosition, Side
from sniper_quant.risk.correlation import correlation_check, pearson
from sniper_quant.risk.engine import RiskEngine, RiskState
from tests.conftest import candidate, make_settings


def _trend(n: int = 60, start: float = 0.01) -> list[float]:
    # Nearly identical upward drift → ρ ≈ 1
    return [start + i * 0.0001 for i in range(n)]


def test_pearson_perfect():
    xs = list(range(30))
    ys = [2 * x for x in xs]
    assert abs(pearson(xs, ys) - 1.0) < 1e-9


def test_correlation_reject_above_threshold():
    returns = {"BTCUSDT": _trend(), "ETHUSDT": _trend()}
    check = correlation_check(
        "BTCUSDT",
        ["ETHUSDT"],
        returns,
        lookback=60,
        threshold=0.70,
    )
    assert check.ok is False
    assert check.vs_symbol == "ETHUSDT"
    assert check.max_abs_corr is not None and check.max_abs_corr > 0.70


def test_engine_rejects_correlated_peer():
    state = RiskState(
        equity=100_000,
        positions=[OpenPosition(symbol="ETHUSDT", side=Side.LONG, size=1, entry=3000)],
        daily_returns={"BTCUSDT": _trend(), "ETHUSDT": _trend()},
    )
    engine = RiskEngine(settings=make_settings(), state=state)
    decision = engine.validate(candidate())
    assert decision.approved is False
    assert decision.reason == "correlation_threshold"
    assert decision.checks["correlation"]["ok"] is False


def test_uncorrelated_passes():
    # Alternating vs flat-trend → low |ρ|
    a = [((i % 2) * 2 - 1) * 0.01 for i in range(60)]
    b = [0.001 for _ in range(60)]
    check = correlation_check("AAA", ["BBB"], {"AAA": a, "BBB": b}, threshold=0.70)
    assert check.ok is True
