from __future__ import annotations

from sniper_quant.risk.daily_loss import daily_loss_check
from sniper_quant.risk.engine import RiskEngine, RiskState
from tests.conftest import candidate, make_settings


def test_daily_loss_already_breached():
    check = daily_loss_check(
        equity=100_000,
        daily_pnl=-3_000,  # exactly 3%
        new_risk=100,
        risk_per_unit=4,
        max_daily_loss_frac=0.03,
    )
    assert check.ok is False
    assert check.already_breached is True
    assert check.max_additional_size == 0.0


def test_daily_loss_would_breach_remaining():
    check = daily_loss_check(
        equity=100_000,
        daily_pnl=-2_500,  # $500 left
        new_risk=2_000,
        risk_per_unit=4,
        max_daily_loss_frac=0.03,
    )
    assert check.ok is False
    assert check.already_breached is False
    assert abs(check.max_additional_size - 125.0) < 1e-9  # 500/4


def test_engine_rejects_when_daily_limit_hit():
    state = RiskState(equity=100_000, daily_pnl=-3_000)
    engine = RiskEngine(settings=make_settings(), state=state)
    decision = engine.validate(candidate())
    assert decision.approved is False
    assert decision.reason == "daily_loss_limit"
    assert decision.adjusted_position_size == 0.0


def test_engine_rejects_when_trade_would_breach_budget():
    state = RiskState(equity=100_000, daily_pnl=-2_900)  # $100 left; trade wants $2000
    engine = RiskEngine(settings=make_settings(), state=state)
    decision = engine.validate(candidate())
    assert decision.approved is False
    assert decision.reason == "daily_loss_limit"
    assert decision.adjusted_position_size == 25.0  # 100 / 4
