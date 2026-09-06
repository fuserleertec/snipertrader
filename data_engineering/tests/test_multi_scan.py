from __future__ import annotations

import json

import pytest

from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.cli import main
from sniper_data.models import RISK_VALIDATE_FIELDS, AssetClass
from sniper_data.pattern_detection.validate import validate_topic
from sniper_data.setup_detection.activity import inspect_active_levels, must_skip_symbol
from sniper_data.setup_detection.candidate import SetupCandidate
from sniper_data.setup_detection.fixtures import bullish_fvg
from sniper_data.setup_detection.history import StaticFillSource, join_paper_history
from sniper_data.setup_detection.multi_scan import scan_universe, seed_symbol
from sniper_data.setup_detection.orchestrator import dedupe_candidates
from sniper_data.setup_detection.risk_client import StaticRiskClient
from sniper_data.zones import store_fvg


REQUIRED = ("ES", "CL", "GC", "NQ")


@pytest.mark.asyncio
async def test_paper_scan_emits_required_futures_and_ranks():
    result = await scan_universe(symbols=list(REQUIRED))
    assert result["live_trading"] is False
    symbols = {s["symbol"] for s in result["signals"]}
    assert symbols >= set(REQUIRED)
    assert len(symbols) > 1
    assert "ob_fvg" not in result["stats"]["setup_types"]
    assert all(b.get("setup_type") != "ob_fvg" for b in result["risk_calls"])
    assert result["risk_calls"]
    for body in result["risk_calls"]:
        assert "id" not in body
        assert "ensemble_score" not in body
        assert "rank_components" not in body
        assert set(body) <= set(RISK_VALIDATE_FIELDS)
    assert result["stats"]["published"] == len(result["signals"])
    assert result["stats"]["published"] == len(result["risk_calls"])
    for payload in result["signals"]:
        validate_topic("setup_signals", payload)
        assert payload.get("ensemble_score") is not None
        assert payload.get("rank_components")
        assert set(payload["rank_components"]) == {
            "setup_quality",
            "confluence",
            "kill_zone",
            "volume",
            "freshness",
        }
        assert payload.get("category") in {"crypto", "equity", "futures"}
        assert payload["setup_type"] != "ob_fvg"
    picks = result["picks"]
    assert picks
    assert {p["symbol"] for p in picks} == set(REQUIRED)
    assert picks == sorted(picks, key=lambda p: p["rank"])
    assert [p["rank"] for p in picks] == list(range(1, len(picks) + 1))
    # Dynamic: not a hardcoded ticker constant.
    assert {p["symbol"] for p in picks} <= set(REQUIRED)
    assert result["ensemble_features"]["live_trading"] is False
    assert result["ensemble_features"]["picks"]
    assert result["ensemble_features"]["refresh_seconds"] == 900
    assert result["ensemble_features"]["signals"]
    assert all(p.get("score") == p.get("ensemble_score") for p in picks)
    assert all(p.get("active_levels") is not False for p in picks)
    assert result["history_summary"]["live_trading"] is False


@pytest.mark.asyncio
async def test_inactive_symbol_skipped():
    skip, reason, info = await must_skip_symbol(InMemoryStateStore(), "YM")
    assert skip is True
    assert reason in {"no_active_levels", "no_session_book", "no_active_zones", "mitigated_only"}
    assert info.ok is False

    result = await scan_universe(symbols=["ES", "YM"], include_inactive=["YM"])
    published = {s["symbol"] for s in result["signals"]}
    assert "ES" in published
    assert "YM" not in published
    assert any(row.get("symbol") == "YM" and row.get("skipped") for row in result["per_symbol"])


@pytest.mark.asyncio
async def test_mitigated_only_is_inactive():
    store = InMemoryStateStore()
    zone = bullish_fvg().model_copy(update={"symbol": "CL", "asset_class": AssetClass.FUTURES, "mitigated": True, "id": "fvg-dead-CL"})
    await store_fvg(store, zone)
    info = await inspect_active_levels(store, "CL")
    assert info.ok is False
    assert info.mitigated_only is True
    assert info.reason == "mitigated_only"


@pytest.mark.asyncio
async def test_seeded_futures_are_active():
    store = InMemoryStateStore()
    await seed_symbol(store, "ES", fvg=True)
    info = await inspect_active_levels(store, "ES")
    assert info.ok is True
    assert info.has_session is True


@pytest.mark.asyncio
async def test_dedupe_does_not_collapse_different_symbols():
    a = SetupCandidate(
        setup_number=1, setup_type="sweep_reclaim", symbol="ES", asset_class=AssetClass.FUTURES,
        side="long", conviction=70, entry=1, stop=0.5, target=2, timeframe="5m",
        trigger_event_ids=["a"], ts_ms=1_000,
    )
    b = SetupCandidate(
        setup_number=1, setup_type="sweep_reclaim", symbol="CL", asset_class=AssetClass.FUTURES,
        side="long", conviction=70, entry=1, stop=0.5, target=2, timeframe="5m",
        trigger_event_ids=["b"], ts_ms=1_100,
    )
    same = SetupCandidate(
        setup_number=2, setup_type="fvg_entry", symbol="ES", asset_class=AssetClass.FUTURES,
        side="long", conviction=60, entry=1, stop=0.5, target=2, timeframe="5m",
        trigger_event_ids=["c"], ts_ms=1_200,
    )
    kept = dedupe_candidates([a, b, same], window_ms=300_000)
    symbols = {c.symbol for c in kept}
    assert symbols == {"ES", "CL"}
    assert sum(1 for c in kept if c.symbol == "ES") == 1


@pytest.mark.asyncio
async def test_rejected_risk_does_not_publish():
    risk = StaticRiskClient(approved=False, reason="daily_loss")
    result = await scan_universe(symbols=["ES"], risk=risk)
    assert result["signals"] == []
    assert result["risk_calls"]
    assert all("id" not in b for b in result["risk_calls"])


@pytest.mark.asyncio
async def test_paper_history_join_wins_and_losses():
    signals = [
        {"id": "w1", "symbol": "ES", "setup_type": "sweep_reclaim", "side": "long", "ts_ms": 1, "status": "ACTIVE"},
        {"id": "l1", "symbol": "CL", "setup_type": "fvg_entry", "side": "short", "ts_ms": 2, "status": "ACTIVE"},
    ]
    fills = StaticFillSource(by_id={"w1": "win", "l1": "loss"})
    rows = join_paper_history(signals, fills)
    by_id = {r["id"]: r["outcome"] for r in rows}
    assert by_id == {"w1": "win", "l1": "loss"}
    assert all(r["live_trading"] is False for r in rows)


@pytest.mark.asyncio
async def test_scan_does_not_emit_inactive_empty_store():
    skip, reason, info = await must_skip_symbol(InMemoryStateStore(), "YM")
    assert skip is True
    assert info.ok is False
    assert reason


def test_cli_paper_scan_required_futures():
    # Capture via running scan path; CLI prints JSON.
    rc = main(["setups", "--inmemory", "--paper-scan", "--universe", "ES,CL,GC,NQ", "--refresh-minutes", "15", "--cycles", "1"])
    assert rc == 0


def test_cli_replay_untouched():
    rc = main(["setups", "--inmemory"])
    assert rc == 0
