"""Phase 2 Project Manager integration tests — setups 1–3 E2E + gates."""

from __future__ import annotations

import pytest

from sniper_data.setup_detection.e2e import (
    LOCKED_TUNABLES,
    build_phase2_e2e_report,
    run_cli_replay_check,
    run_gate_conviction_skips_validate,
    run_gate_dedupe_300s,
    run_gate_reject_never_publishes,
    run_setup1_e2e,
    run_setup2_e2e,
    run_setup3_e2e,
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
async def test_e2e_cli_inmemory_replay_all_three():
    _require_pass(await run_cli_replay_check())


@pytest.mark.asyncio
async def test_e2e_phase2_report_overall_pass():
    report = await build_phase2_e2e_report()
    assert report["summary"]["overall"] == "PASS", report["summary"]
    assert report["summary"]["failed"] == 0
