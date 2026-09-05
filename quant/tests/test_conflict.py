from __future__ import annotations

from sniper_quant.models import AssetClass, OpenPosition, Side, SignalStatus, StoredSignal
from sniper_quant.risk.engine import RiskEngine, RiskState
from tests.conftest import candidate, make_settings


def test_same_symbol_open_position_rejected():
    state = RiskState(
        equity=100_000,
        positions=[OpenPosition(symbol="BTCUSDT", side=Side.LONG, size=1, entry=100)],
    )
    engine = RiskEngine(settings=make_settings(), state=state)
    decision = engine.validate(candidate(side=Side.SHORT, stop=104.0, target=92.0))
    assert decision.approved is False
    assert decision.reason == "same_symbol_conflict"
    assert decision.adjusted_position_size == 0.0


def test_other_symbol_allowed():
    state = RiskState(
        equity=100_000,
        positions=[OpenPosition(symbol="ETHUSDT", side=Side.LONG, size=1, entry=3000)],
    )
    engine = RiskEngine(settings=make_settings(), state=state)
    decision = engine.validate(candidate())
    assert decision.approved is True
    assert decision.reason == "ok"


def test_active_signal_sync_conflicts():
    engine = RiskEngine(settings=make_settings(), state=RiskState(equity=100_000))
    engine.state.sync_from_signals(
        [
            StoredSignal(
                id="sig-1",
                symbol="BTCUSDT",
                asset_class=AssetClass.CRYPTO,
                setup_type="fvg_entry",
                side=Side.LONG,
                ts_ms=1,
                entry=100,
                status=SignalStatus.ACTIVE,
            )
        ]
    )
    decision = engine.validate(candidate())
    assert decision.approved is False
    assert decision.reason == "same_symbol_conflict"
