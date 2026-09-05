from __future__ import annotations

import json
from pathlib import Path

from sniper_quant.backtest.detectors import (
    DEFAULT_PARAMS,
    SETUP_INDEX,
    detect_avwap_ob_confluence,
    detect_fvg_entry,
    detect_po3_judas,
    detect_sd_extension_fade,
    detect_sweep_reclaim,
    detect_vwap_pullback_cont,
    parse_setup_ids,
)
from sniper_quant.backtest.engine import EventBacktester
from sniper_quant.backtest.params import (
    GRID_CONFLUENCE,
    GRID_MIN_RR,
    GRID_MSS_LOOKBACK,
    fvg_entry_grid,
    po3_judas_grid,
    sweep_reclaim_grid,
)
from sniper_quant.backtest.report import render_walkforward_markdown
from sniper_quant.backtest.synthetic_setups import synthetic_setup_tape
from sniper_quant.backtest.walkforward import walk_forward_setups
from sniper_quant.cli import main


def test_parse_setup_ids():
    assert parse_setup_ids("1,2,3") == [1, 2, 3]
    assert parse_setup_ids("sweep_reclaim,po3_judas") == [1, 3]
    assert parse_setup_ids("4,5,6") == [4, 5, 6]
    assert parse_setup_ids("sd_extension_fade,avwap_ob_confluence") == [4, 6]


def test_locked_defaults():
    p = DEFAULT_PARAMS
    assert p.stop_buffer_atr == 0.05
    assert p.stop_buffer_ticks == 1
    assert p.vwap_target_band == "auto"
    assert p.min_rr == 2.0
    assert p.mss_swing_lookback == 5
    assert p.max_bars_sweep_to_mss == 15
    assert p.require_confirmed_sweep is True
    assert p.session_vwap_anchor == "session"
    assert p.timeframe == "5m"
    assert p.confluence_mode == "vwap_or_hvn"
    assert p.fvg_overlap_tol_atr == 0.05
    assert p.confirmation == "either"
    assert p.pin_wick_ratio == 2.5
    assert p.entry_mode == "confirm_close"
    assert p.fvg_stop_buffer_atr == 0.05
    assert p.target_mode == "prior_swing"
    assert p.max_fvg_age_hours == 24
    assert p.accumulation_session == "asia"
    assert p.kill_zone == "ny_am"
    assert p.resolved_kill_zone("crypto") == "either"
    assert p.resolved_kill_zone("equity") == "ny_am"
    assert p.displacement_min_body_atr == 1.2
    assert p.require_band_tag == "either"
    assert p.s3_require_band_tag is True
    assert p.target_rr_fallback == 2.0
    assert p.min_conviction_to_validate == 60
    ml = p.to_ml_setup_params()
    assert ml["s1_min_rr"] == 2.0
    assert ml["s3_kill_zone"] == "ny_am"
    assert ml["s3_require_band_tag"] is True
    assert ml["s2_target_rr_fallback"] == 2.0
    assert p.po3_stop_buffer_atr == 0.05
    assert p.partial_mid is False
    assert p.max_bars_sweep_to_displace == 6
    assert p.dedupe_window_sec == 300
    assert p.min_conviction == 60
    assert p.s4_band_trigger == "either"
    assert p.s4_vol_max_frac == 0.8
    assert p.s4_confirm == "either"
    assert p.s4_stop_buffer_atr == 0.05
    assert p.s4_min_rr == 1.5
    assert p.news_skip_minutes == 15
    assert p.s5_trend_lookback_bars == 20
    assert p.s5_pullback_level == "either"
    assert p.s5_require_ob_or_fvg is True
    assert p.s5_first_touch_window_bars == 5
    assert p.s5_min_rr == 2.0
    assert p.s6_ob_timeframe == "4h"
    assert p.s6_approach_tol_atr == 0.05
    assert p.s6_confirm == "rejection"
    assert p.s6_min_rr == 2.0
    assert p.s6_min_conviction == 70


def test_grids_cover_locked_values():
    s1 = sweep_reclaim_grid(mode="full")
    assert {p.min_rr for p in s1} == set(GRID_MIN_RR)
    assert {p.mss_swing_lookback for p in s1} == set(GRID_MSS_LOOKBACK)
    assert {p.vwap_target_band for p in s1} == {"1", "2"}
    s2 = fvg_entry_grid(mode="core")
    assert {p.confluence_mode for p in s2} == set(GRID_CONFLUENCE)
    s3 = po3_judas_grid(mode="core")
    assert {p.accumulation_session for p in s3} == {"asia", "globex"}


def test_detectors_fire_on_synthetic():
    bars = synthetic_setup_tape("BTCUSDT", cycles=6, timeframe="5m")
    sweep = detect_sweep_reclaim(bars, DEFAULT_PARAMS)
    fvg = detect_fvg_entry(bars, DEFAULT_PARAMS)
    po3 = detect_po3_judas(bars, DEFAULT_PARAMS)
    s4 = detect_sd_extension_fade(bars, DEFAULT_PARAMS)
    s5 = detect_vwap_pullback_cont(bars, DEFAULT_PARAMS)
    s6 = detect_avwap_ob_confluence(bars, DEFAULT_PARAMS)
    assert sweep, "expected sweep_reclaim hits on synthetic tape"
    assert fvg, "expected fvg_entry hits on synthetic tape"
    assert po3, "expected po3_judas hits on synthetic tape"
    assert s4, "expected sd_extension_fade hits on synthetic tape"
    assert s5, "expected vwap_pullback_cont hits on synthetic tape"
    assert s6, "expected avwap_ob_confluence hits on synthetic tape"
    assert {s.setup_type for s in sweep} == {"sweep_reclaim"}
    assert {s.setup_type for s in fvg} == {"fvg_entry"}
    assert {s.setup_type for s in po3} == {"po3_judas"}
    assert {s.setup_type for s in s4} == {"sd_extension_fade"}
    assert {s.setup_type for s in s5} == {"vwap_pullback_cont"}
    assert {s.setup_type for s in s6} == {"avwap_ob_confluence"}


def test_detected_signals_backtest():
    bars = synthetic_setup_tape("BTCUSDT", cycles=4, timeframe="5m")
    signals = detect_sweep_reclaim(bars, DEFAULT_PARAMS)
    result = EventBacktester().run(bars, signals, equity=100_000)
    assert result.metrics.n_trades >= 1
    assert result.metrics.max_drawdown >= 0.0


def test_walkforward_setups_1_2_3():
    bars = synthetic_setup_tape("BTCUSDT", cycles=12, timeframe="5m")
    rows = walk_forward_setups(bars, [1, 2, 3], n_folds=3, equity=100_000, mode="core")
    assert [r.setup_type for r in rows] == [SETUP_INDEX[i] for i in (1, 2, 3)]
    for row in rows:
        assert len(row.folds) == 3
        assert row.oos.n_trades >= 1
        assert 0.0 <= row.oos.win_rate <= 1.0
        assert row.recommended
        md = render_walkforward_markdown(
            [row],
            symbol="BTCUSDT",
            timeframe="5m",
            source="test",
            n_bars=len(bars),
            n_folds=3,
            mode="core",
        )
        assert row.setup_type in md
        assert "Locked ranges" in md
        assert "**2.0**" in md
        assert "Alignment with ML PR #7" in md
        assert "s3_kill_zone" in md


def test_walkforward_setups_4_5_6():
    bars = synthetic_setup_tape("BTCUSDT", cycles=12, timeframe="5m")
    rows = walk_forward_setups(bars, [4, 5, 6], n_folds=3, equity=100_000, mode="core")
    assert [r.setup_type for r in rows] == [SETUP_INDEX[i] for i in (4, 5, 6)]
    for row in rows:
        assert len(row.folds) == 3
        assert row.oos.n_trades >= 1
        assert 0.0 <= row.oos.win_rate <= 1.0
        md = render_walkforward_markdown(
            [row],
            symbol="BTCUSDT",
            timeframe="5m",
            source="test",
            n_bars=len(bars),
            n_folds=3,
            mode="core",
        )
        assert row.setup_type in md
        assert "sd_extension_fade" in md or row.setup_type != "sd_extension_fade"


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
            "--timeframe",
            "5m",
            "--grid-mode",
            "core",
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
    assert "Recommended params" in text


def test_grafana_dashboard_json_valid():
    path = Path(__file__).resolve().parents[1] / "grafana/provisioning/dashboards/json/setup-performance.json"
    dash = json.loads(path.read_text(encoding="utf-8"))
    titles = {p["title"] for p in dash["panels"]}
    assert "Signals per day" in titles
    assert "Win rate by day" in titles
    assert "Average realized_r (R:R) by day" in titles
    assert "Cumulative P&L" in titles
    assert dash["uid"] == "quant-setup-performance"
