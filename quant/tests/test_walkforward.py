from __future__ import annotations

import json
from pathlib import Path

from sniper_quant.backtest.detectors import (
    DEFAULT_PARAMS,
    SETUP_INDEX,
    detect_fvg_entry,
    detect_po3_judas,
    detect_sweep_reclaim,
    parse_setup_ids,
)
from sniper_quant.backtest.engine import EventBacktester
from sniper_quant.backtest.report import render_walkforward_markdown
from sniper_quant.backtest.synthetic_setups import synthetic_setup_tape
from sniper_quant.backtest.walkforward import walk_forward_setups
from sniper_quant.cli import main


def test_parse_setup_ids():
    assert parse_setup_ids("1,2,3") == [1, 2, 3]
    assert parse_setup_ids("sweep_reclaim,po3_judas") == [1, 3]


def test_detectors_fire_on_synthetic():
    bars = synthetic_setup_tape("BTCUSDT", cycles=6)
    sweep = detect_sweep_reclaim(bars, DEFAULT_PARAMS)
    fvg = detect_fvg_entry(bars, DEFAULT_PARAMS)
    po3 = detect_po3_judas(bars, DEFAULT_PARAMS)
    assert sweep, "expected sweep_reclaim hits on synthetic tape"
    assert fvg, "expected fvg_entry hits on synthetic tape"
    assert po3, "expected po3_judas hits on synthetic tape"
    assert {s.setup_type for s in sweep} == {"sweep_reclaim"}
    assert {s.setup_type for s in fvg} == {"fvg_entry"}
    assert {s.setup_type for s in po3} == {"po3_judas"}


def test_detected_signals_backtest():
    bars = synthetic_setup_tape("BTCUSDT", cycles=4)
    signals = detect_sweep_reclaim(bars, DEFAULT_PARAMS)
    result = EventBacktester().run(bars, signals, equity=100_000)
    assert result.metrics.n_trades >= 1
    assert result.metrics.max_drawdown >= 0.0


def test_walkforward_setups_1_2_3():
    bars = synthetic_setup_tape("BTCUSDT", cycles=12)
    rows = walk_forward_setups(bars, [1, 2, 3], n_folds=3, equity=100_000)
    assert [r.setup_type for r in rows] == [SETUP_INDEX[i] for i in (1, 2, 3)]
    for row in rows:
        assert len(row.folds) == 3
        assert row.oos.n_trades >= 1
        assert 0.0 <= row.oos.win_rate <= 1.0
        md = render_walkforward_markdown(
            [row],
            symbol="BTCUSDT",
            timeframe="1h",
            source="test",
            n_bars=len(bars),
            n_folds=3,
        )
        assert row.setup_type in md
        assert "tunable" in md.lower() or "Grid" in md


def test_cli_backtest_writes_report(tmp_path: Path, capsys):
    report = tmp_path / "wf.md"
    code = main(
        [
            "backtest",
            "--inmemory",
            "--setups",
            "1,2,3",
            "--folds",
            "3",
            "--report",
            str(report),
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["setups"]) == {"sweep_reclaim", "fvg_entry", "po3_judas"}
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "sweep_reclaim" in text
    assert "po3_judas" in text
    assert "Walk-forward" in text or "walk-forward" in text


def test_grafana_dashboard_json_valid():
    path = Path(__file__).resolve().parents[1] / "grafana/provisioning/dashboards/json/setup-performance.json"
    dash = json.loads(path.read_text(encoding="utf-8"))
    titles = {p["title"] for p in dash["panels"]}
    assert "Signals per day" in titles
    assert "Win rate by day" in titles
    assert "Average R:R by day" in titles
    assert "Cumulative P&L" in titles
    assert dash["uid"] == "quant-setup-performance"
