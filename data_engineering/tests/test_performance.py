from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import Settings
from sniper_data.performance import PerformanceStore, SignalOutcome, compute_summary
from sniper_data.setups import SETUP_KEYS, SETUP_3_PO3_ASIA_RANGE_SWEEP, resolve_setup_key

FROZEN = (
    "1_liquidity_sweep_vwap_reclaim",
    "2_fvg_mitigation_vwap",
    "3_po3_asia_range_sweep",
    "4_sd_extension_fade",
    "5_vwap_pullback_cont",
    "6_avwap_ob_confluence",
)


def _client():
    store = InMemoryStateStore()
    app = create_app(store=store, settings=Settings(USE_INMEMORY=True))
    return TestClient(app), store


def test_setup_keys_are_the_pm_lock():
    assert SETUP_KEYS == FROZEN
    assert resolve_setup_key("po3_judas") == SETUP_3_PO3_ASIA_RANGE_SWEEP
    assert resolve_setup_key("4_sd_extension_fade") == "4_sd_extension_fade"


def test_empty_summary_has_exact_envelope():
    http, _ = _client()
    resp = http.get("/performance/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"timestamp", "overall", "by_setup"}
    assert isinstance(body["timestamp"], int)
    assert body["timestamp"] > 0
    overall = body["overall"]
    assert set(overall) == {
        "win_rate",
        "average_rr",
        "sharpe_ratio",
        "max_drawdown_pct",
        "signals_today",
        "signals_week",
    }
    assert overall["win_rate"] == 0.0
    assert overall["signals_today"] == 0
    assert set(body["by_setup"]) == set(FROZEN)
    for key in FROZEN:
        stats = body["by_setup"][key]
        assert set(stats) == {"win_rate", "average_rr", "signals"}
        assert stats == {"win_rate": 0.0, "average_rr": 0.0, "signals": 0}


def test_outcomes_roundtrip_and_po3_alias():
    http, _ = _client()
    created = http.post(
        "/performance/outcomes",
        json={
            "setup": "1_liquidity_sweep_vwap_reclaim",
            "won": True,
            "rr": 2.0,
            "ts_ms": 1_725_458_400_000,
        },
    )
    assert created.status_code == 201
    alias = http.post(
        "/performance/outcomes",
        json={"setup_type": "po3_judas", "won": False, "rr": 1.0, "ts_ms": 1_725_458_400_100},
    )
    assert alias.status_code == 201
    body = http.get("/performance/summary").json()
    assert body["overall"]["signals_week"] >= 0
    assert body["by_setup"]["1_liquidity_sweep_vwap_reclaim"]["signals"] == 1
    assert body["by_setup"]["1_liquidity_sweep_vwap_reclaim"]["win_rate"] == 1.0
    assert body["by_setup"]["1_liquidity_sweep_vwap_reclaim"]["average_rr"] == 2.0
    assert body["by_setup"]["3_po3_asia_range_sweep"]["signals"] == 1
    assert body["by_setup"]["3_po3_asia_range_sweep"]["win_rate"] == 0.0
    for key in ("2_fvg_mitigation_vwap", "4_sd_extension_fade", "5_vwap_pullback_cont", "6_avwap_ob_confluence"):
        assert body["by_setup"][key]["signals"] == 0


def test_setup_filter_does_not_drop_by_setup_keys():
    http, _ = _client()
    http.post(
        "/performance/outcomes",
        json={"setup": "2_fvg_mitigation_vwap", "won": True, "rr": 1.5, "ts_ms": 1_725_458_400_000},
    )
    body = http.get("/performance/summary?setup=2_fvg_mitigation_vwap").json()
    assert set(body["by_setup"]) == set(FROZEN)
    assert body["overall"]["win_rate"] == 1.0
    assert body["by_setup"]["2_fvg_mitigation_vwap"]["signals"] == 1
    bad = http.get("/performance/summary?setup=not_a_setup")
    assert bad.status_code == 400


def test_compute_summary_drawdown_and_sharpe():
    from sniper_data.performance import StoredOutcome

    now = 1_725_500_000_000
    rows = [
        StoredOutcome(setup="1_liquidity_sweep_vwap_reclaim", won=True, rr=2.0, ts_ms=now),
        StoredOutcome(setup="1_liquidity_sweep_vwap_reclaim", won=False, rr=3.0, ts_ms=now),
        StoredOutcome(setup="1_liquidity_sweep_vwap_reclaim", won=True, rr=1.0, ts_ms=now),
    ]
    body = compute_summary(rows, now_ms=now)
    assert body["overall"]["signals_today"] == 3
    assert body["overall"]["sharpe_ratio"] != 0.0
    assert body["overall"]["max_drawdown_pct"] >= 0.0


def test_unknown_setup_rejected():
    http, _ = _client()
    resp = http.post("/performance/outcomes", json={"setup": "nope", "won": True, "rr": 1})
    assert resp.status_code == 400


def test_performance_store_persists_on_redis_key():
    store = InMemoryStateStore()
    perf = PerformanceStore(store)
    import asyncio

    asyncio.run(
        perf.record(
            SignalOutcome(setup="5_vwap_pullback_cont", won=True, rr=1.25, ts_ms=10)
        )
    )
    raw = asyncio.run(store.get("perf:outcomes"))
    assert raw[0]["setup"] == "5_vwap_pullback_cont"
