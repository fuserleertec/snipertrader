"""Phase 2 Project Manager integration tests — setups 1–3 E2E + gates."""

from __future__ import annotations

import json

import pytest

from sniper_data.models import RISK_VALIDATE_FIELDS
from sniper_data.setup_detection.e2e import (
    LOCKED_TUNABLES,
    build_phase2_e2e_report,
    build_phase3_e2e_report,
    run_cli_replay_check,
    run_gate_conviction_skips_validate,
    run_gate_dedupe_300s,
    run_gate_reject_never_publishes,
    run_setup1_e2e,
    run_setup2_e2e,
    run_setup3_e2e,
    run_setup4_e2e,
    run_setup5_e2e,
    run_setup6_e2e,
    write_quant_replay_pack,
)
from sniper_data.setup_detection.params import SetupParams


def _require_pass(result: dict) -> None:
    failed = [a["name"] for a in result["assertions"] if not a["pass"]]
    assert result["status"] == "PASS", f"{result['id']} failed: {failed} — {result}"


def test_locked_tunables_match_quant():
    p = SetupParams()
    assert p.s1_min_rr == LOCKED_TUNABLES["s1_min_rr"] == 2.0
    assert p.s3_accum_session == LOCKED_TUNABLES["s3_accum_session"] == "asia"
    assert p.s3_kill_zone == LOCKED_TUNABLES["s3_kill_zone"] == "ny_am"
    assert p.dedupe_window_sec == LOCKED_TUNABLES["dedupe_window_sec"] == 300
    assert p.min_conviction_to_validate == LOCKED_TUNABLES["min_conviction_to_validate"] == 60


@pytest.mark.asyncio
async def test_e2e_setup1_sweep_mss_vwap_reclaim_then_risk_then_publish():
    result = await run_setup1_e2e(approved=True)
    _require_pass(result)
    assert result["setup_type"] == "sweep_reclaim"
    assert result["trace"][0] == "validate"
    assert result["trace"][1] == "publish:setup_signals"
    assert result["published_signal"]["setup_type"] == "sweep_reclaim"
    assert result["raw"]["risk_reward"] >= 2.0
    assert "swp-buy-low" in result["raw"]["trigger_event_ids"]
    assert any(i.startswith("mss") for i in result["raw"]["trigger_event_ids"])


@pytest.mark.asyncio
async def test_e2e_setup2_fvg_vwap_hvn_entry_then_risk():
    result = await run_setup2_e2e(with_ob=False, approved=True)
    _require_pass(result)
    assert result["setup_type"] == "fvg_entry"
    assert result["trace"][0] == "validate"
    assert result["published_signal"]["entry"] == result["raw"]["entry"]


@pytest.mark.asyncio
async def test_e2e_setup2_ob_fvg_when_ob_overlaps():
    result = await run_setup2_e2e(with_ob=True, approved=True)
    _require_pass(result)
    assert result["setup_type"] == "ob_fvg"


@pytest.mark.asyncio
async def test_e2e_setup3_asia_judas_ny_am_displacement_then_risk():
    result = await run_setup3_e2e(approved=True)
    _require_pass(result)
    assert result["setup_type"] == "po3_judas"
    assert result["raw"]["kill_zone"] == "ny_am"
    assert result["trace"][0] == "validate"
    assert result["published_signal"]["setup_type"] == "po3_judas"


@pytest.mark.asyncio
async def test_e2e_conviction_below_60_never_validates():
    _require_pass(await run_gate_conviction_skips_validate())


@pytest.mark.asyncio
async def test_e2e_rejected_validate_never_publishes():
    _require_pass(await run_gate_reject_never_publishes())


@pytest.mark.asyncio
async def test_e2e_dedupe_300s_keeps_highest_conviction():
    _require_pass(await run_gate_dedupe_300s())


@pytest.mark.asyncio
async def test_e2e_cli_inmemory_replay_all_six():
    _require_pass(await run_cli_replay_check())


@pytest.mark.asyncio
async def test_e2e_setup4_sd_extension_fade_approve_and_reject():
    ok = await run_setup4_e2e(approved=True)
    no = await run_setup4_e2e(approved=False)
    _require_pass(ok)
    _require_pass(no)
    assert ok["setup_type"] == "sd_extension_fade"
    assert ok["product_key"] == "4_sd_extension_fade"
    assert ok["trace"][0] == "validate"
    assert ok["trace"][1] == "publish:setup_signals"
    assert "contributing_factors" in ok["published_signal"]
    assert ok["published_signal"]["factor_breakdown"]
    assert "id" not in ok["risk_request"]
    assert "contributing_factors" not in ok["risk_request"]
    assert no["publish_count"] == 0
    assert no["published_signal"] is None


@pytest.mark.asyncio
async def test_e2e_setup5_vwap_pullback_cont_approve_and_reject():
    ok = await run_setup5_e2e(approved=True)
    no = await run_setup5_e2e(approved=False)
    _require_pass(ok)
    _require_pass(no)
    assert ok["setup_type"] == "vwap_pullback_cont"
    assert ok["product_key"] == "5_vwap_pullback_cont"
    assert ok["trace"][0] == "validate"
    assert ok["published_signal"]["factor_breakdown"]
    assert "factor_breakdown" not in ok["risk_request"]
    assert no["publish_count"] == 0


@pytest.mark.asyncio
async def test_e2e_setup6_avwap_ob_confluence_approve_and_reject():
    ok = await run_setup6_e2e(approved=True)
    no = await run_setup6_e2e(approved=False)
    _require_pass(ok)
    _require_pass(no)
    assert ok["setup_type"] == "avwap_ob_confluence"
    assert ok["product_key"] == "6_avwap_ob_confluence"
    assert ok["trace"][0] == "validate"
    assert ok["published_signal"]["ref_vwap"] == 100.0
    assert ok["published_signal"]["factor_breakdown"]
    assert no["publish_count"] == 0


@pytest.mark.asyncio
async def test_e2e_phase3_report_overall_pass():
    report = await build_phase3_e2e_report()
    assert report["summary"]["overall"] == "PASS", report["summary"]
    assert report["phase"] == 3
    rows = report["quant_replay"]["per_setup"]
    assert {r["setup_type"] for r in rows} >= {
        "sd_extension_fade",
        "vwap_pullback_cont",
        "avwap_ob_confluence",
    }
    for row in rows:
        req = row["validate_request"]
        assert "id" not in req
        assert "contributing_factors" not in req
        assert "factor_breakdown" not in req
        assert set(req) <= set(RISK_VALIDATE_FIELDS)
        sig = row["mocked_approve"]["published_setup_signal"]
        assert sig["id"]
        assert row["mocked_approve"]["publish_count"] == 1
        assert row["mocked_reject"]["publish_count"] == 0


@pytest.mark.asyncio
async def test_e2e_setup1_reject_zero_publish():
    result = await run_setup1_e2e(approved=False)
    _require_pass(result)
    assert result["publish_count"] == 0
    assert result["published_signal"] is None
    assert result["trace"] == ["validate"]
    assert "id" not in result["risk_request"]


@pytest.mark.asyncio
async def test_e2e_setup2_and_3_reject_zero_publish():
    s2 = await run_setup2_e2e(with_ob=False, approved=False)
    s3 = await run_setup3_e2e(approved=False)
    _require_pass(s2)
    _require_pass(s3)
    assert s2["publish_count"] == s3["publish_count"] == 0
    assert s2["published_signal"] is None
    assert s3["published_signal"] is None


@pytest.mark.asyncio
async def test_e2e_phase2_report_overall_pass():
    report = await build_phase2_e2e_report()
    assert report["summary"]["overall"] == "PASS", report["summary"]
    assert report["summary"]["failed"] == 0
    rows = report["quant_replay"]["per_setup"]
    assert {r["setup_type"] for r in rows} == {"sweep_reclaim", "fvg_entry", "po3_judas"}
    for row in rows:
        req = row["validate_request"]
        assert "id" not in req
        assert set(req) <= set(RISK_VALIDATE_FIELDS)
        sig = row["mocked_approve"]["published_setup_signal"]
        assert sig["id"]
        assert sig["setup_type"] == row["setup_type"]
        assert row["mocked_approve"]["publish_count"] == 1
        assert row["mocked_reject"]["publish_count"] == 0
        assert row["mocked_reject"]["published_setup_signal"] is None


@pytest.mark.asyncio
async def test_quant_replay_pack_files(tmp_path):
    report = await build_phase2_e2e_report()
    dest = tmp_path / "quant_replay"
    written = write_quant_replay_pack(report, dest)
    assert (dest / "curl_replay.sh").exists()
    for kind in ("sweep_reclaim", "fvg_entry", "po3_judas"):
        req = json.loads((dest / f"{kind}.validate.json").read_text())
        sig = json.loads((dest / f"{kind}.setup_signal.json").read_text())
        assert "id" not in req
        assert sig["id"]
        assert written[f"{kind}.validate.json"]
