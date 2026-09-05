from __future__ import annotations

from sniper_quant.risk.sizing import fixed_fractional_size, requested_risk, risk_amount
from sniper_quant.usme import compute_usme_levels
from tests.conftest import candidate, make_settings
from sniper_quant.risk.engine import RiskEngine, RiskState


def test_fixed_fractional_2pct():
    # $100k * 2% = $2,000 risk; $200/unit → 10 units
    assert fixed_fractional_size(100_000, 0.02, 200.0) == 10.0
    assert risk_amount(100_000, 0.02) == 2_000.0
    assert requested_risk(10.0, 200.0) == 2_000.0


def test_usme_2x_atr_stop_and_2r_target():
    levels = compute_usme_levels(side="long", entry=100.0, atr=2.0)
    assert levels.stop == 96.0  # 100 - 2*2
    assert levels.risk_per_unit == 4.0
    assert levels.target == 108.0  # 2R
    assert abs(levels.r_multiple - 2.0) < 1e-9


def test_validate_computes_size_when_omitted(engine):
    decision = engine.validate(candidate())
    assert decision.approved is True
    # risk/unit = 4; 2% of 100k = 2000 → 500 units
    assert decision.adjusted_position_size == 500.0


def test_requested_size_within_limit_kept(engine):
    decision = engine.validate(candidate(position_size=100.0))
    assert decision.approved is True
    assert decision.adjusted_position_size == 100.0


def test_requested_size_over_limit_rejected():
    eng = RiskEngine(settings=make_settings(), state=RiskState(equity=100_000))
    decision = eng.validate(candidate(position_size=10_000.0))
    assert decision.approved is False
    assert decision.reason == "position_size_exceeds_limit"
    assert decision.adjusted_position_size == 500.0
