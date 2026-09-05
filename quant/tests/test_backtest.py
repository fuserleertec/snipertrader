from __future__ import annotations

from sniper_quant.backtest.demo import demo_universe, run_inmemory_demo, synthetic_daily_bars
from sniper_quant.backtest.engine import BacktestSignal, EventBacktester
from sniper_quant.backtest.metrics import compute_metrics, max_drawdown, sharpe_ratio
from sniper_quant.models import OHLCVBar, Side, SignalStatus
from sniper_quant.setups import SETUP_TYPES


def test_metrics_helpers():
    assert max_drawdown([100, 120, 90, 95]) == (120 - 90) / 120
    assert sharpe_ratio([0.01, 0.01, 0.01]) == 0.0  # zero vol
    assert sharpe_ratio([0.01, -0.01, 0.02, -0.005]) != 0.0


def test_inmemory_demo_runs_all_six_setups():
    result = run_inmemory_demo()
    used = {t.setup_type for t in result.trades}
    assert used == set(SETUP_TYPES)
    assert result.metrics.n_trades == 12
    m = result.metrics
    assert abs(m.win_rate - 0.5) < 1e-9
    assert m.max_drawdown >= 0.0
    assert m.starting_equity == 100_000.0
    assert isinstance(m.sharpe, float)
    assert isinstance(m.avg_rr, float)


def test_event_sl_before_tp_same_bar():
    # Long: bar that both tags stop and target → SL wins
    bars = [
        OHLCVBar(
            symbol="ES",
            asset_class="futures",
            timeframe="1h",
            open_ts_ms=1_000,
            close_ts_ms=3_600_000,
            open=100,
            high=100.2,
            low=99.8,
            close=100,
            volume=1,
        ),
        OHLCVBar(
            symbol="ES",
            asset_class="futures",
            timeframe="1h",
            open_ts_ms=3_600_000,
            close_ts_ms=7_200_000,
            open=100,
            high=120,
            low=80,
            close=110,
            volume=1,
        ),
    ]
    signals = [
        BacktestSignal(
            ts_ms=1_100,
            symbol="ES",
            setup_type="order_block",
            side=Side.LONG,
            entry=100,
            atr=1.0,  # stop 98, target 104
        )
    ]
    result = EventBacktester().run(bars, signals, equity=100_000)
    assert result.metrics.n_trades == 1
    assert result.trades[0].status is SignalStatus.SL_HIT


def test_demo_universe_has_six_setup_types():
    _bars, signals = demo_universe()
    types = {s.setup_type for s in signals}
    assert types == set(SETUP_TYPES)
    assert len(signals) == 12
