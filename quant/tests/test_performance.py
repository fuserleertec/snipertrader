"""GET /performance/summary — Frontend contract (by_setup keyed by product_key)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.performance import summarize_signals
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import (
    PERFORMANCE_SETUP_TYPES,
    PRODUCT_KEYS,
    PRODUCT_TO_SETUP_TYPE,
    SETUP_TYPE_TO_PRODUCT,
)
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings
from tests.test_validate import _payload

SUMMARY_FIELDS = {
    "win_rate",
    "average_rr",
    "sharpe_ratio",
    "max_drawdown_pct",
    "signals_today",
    "signals_week",
    "by_setup",
}
BUCKET_FIELDS = {
    "setup_type",
    "product_key",
    "win_rate",
    "average_rr",
    "sharpe_ratio",
    "max_drawdown_pct",
    "signals_today",
    "signals_week",
}
FORBIDDEN_BY_SETUP = {
    "sweep_reclaim",
    "fvg_entry",
    "po3_judas",
    "sd_extension_fade",
    "vwap_pullback_cont",
    "avwap_ob_confluence",
    "mss_break",
    "order_block",
    "sweep_mss",
    "ob_fvg",
    "4_pending_user_confirm",
    "5_pending_user_confirm",
    "6_pending_user_confirm",
}


def _client():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    return TestClient(create_app(settings=settings, signals=InMemorySignalStore(), engine=engine))


def test_empty_book_shape_and_required_keys():
    http = _client()
    body = http.get("/performance/summary").json()
    assert SUMMARY_FIELDS <= set(body)
    assert body["win_rate"] == 0.0
    assert body["average_rr"] == 0.0
    assert body["sharpe_ratio"] == 0.0
    assert body["max_drawdown_pct"] == 0.0
    assert body["signals_today"] == 0
    assert body["signals_week"] == 0
    assert list(body["by_setup"]) == list(PRODUCT_KEYS)
    assert FORBIDDEN_BY_SETUP.isdisjoint(body["by_setup"])
    for product_key in PRODUCT_KEYS:
        bucket = body["by_setup"][product_key]
        setup_type = PRODUCT_TO_SETUP_TYPE[product_key]
        assert BUCKET_FIELDS <= set(bucket)
        assert bucket["setup_type"] == setup_type
        assert bucket["product_key"] == product_key
        assert bucket["win_rate"] == 0.0
        assert bucket["average_rr"] == 0.0
        assert bucket["signals_today"] == 0
        assert bucket["signals_week"] == 0
        assert bucket["n_signals"] == 0
    assert body["by_setup"]["3_po3_asia_range_sweep"]["setup_type"] == "po3_judas"
    assert body["by_setup"]["4_sd_extension_fade"]["setup_type"] == "sd_extension_fade"
    assert body["by_setup"]["5_vwap_pullback_cont"]["setup_type"] == "vwap_pullback_cont"
    assert body["by_setup"]["6_avwap_ob_confluence"]["setup_type"] == "avwap_ob_confluence"


def test_summary_from_realized_r():
    empty = summarize_signals([])
    assert empty.win_rate == 0.0
    assert list(empty.by_setup) == list(PRODUCT_KEYS)

    http = _client()
    created = http.post(
        "/signals",
        json=_payload(setup_type="sweep_reclaim", confidence=0.9, ts_ms=1_800_000_000_000),
    ).json()
    http.patch(
        f"/signals/{created['id']}",
        json={"status": "TP_HIT", "exit_price": 108.0, "realized_r": 2.0, "closed_ts_ms": 50},
    )
    body = http.get("/performance/summary").json()
    assert body["win_rate"] == 1.0
    assert body["average_rr"] == 2.0
    sweep = body["by_setup"]["1_liquidity_sweep_vwap_reclaim"]
    assert sweep["setup_type"] == "sweep_reclaim"
    assert sweep["product_key"] == "1_liquidity_sweep_vwap_reclaim"
    assert sweep["win_rate"] == 1.0
    assert sweep["average_rr"] == 2.0
    assert sweep["n_signals"] == 1
    assert body["by_setup"]["4_sd_extension_fade"]["win_rate"] == 0.0
    assert "mss_break" not in body["by_setup"]


def test_product_key_lock_strings():
    assert SETUP_TYPE_TO_PRODUCT == {
        "sweep_reclaim": "1_liquidity_sweep_vwap_reclaim",
        "fvg_entry": "2_fvg_mitigation_vwap",
        "po3_judas": "3_po3_asia_range_sweep",
        "sd_extension_fade": "4_sd_extension_fade",
        "vwap_pullback_cont": "5_vwap_pullback_cont",
        "avwap_ob_confluence": "6_avwap_ob_confluence",
    }
    assert PERFORMANCE_SETUP_TYPES == tuple(SETUP_TYPE_TO_PRODUCT)
    values = set(SETUP_TYPE_TO_PRODUCT.values())
    assert "3_po3_judas" not in values
    assert "4_mss_break" not in values
    assert "4_pending_user_confirm" not in values
    assert "5_pending_user_confirm" not in values
    assert "6_pending_user_confirm" not in values
    assert "4_sd_extension_fade" in values


def test_grafana_labels_use_product_key_lock():
    import json
    from pathlib import Path

    dash = json.loads(
        (Path(__file__).resolve().parents[1] / "grafana/provisioning/dashboards/json/setup-performance.json").read_text()
    )
    blob = json.dumps(dash)
    assert "3_po3_asia_range_sweep" in blob
    assert "3_po3_judas" not in blob
    assert "4_sd_extension_fade" in blob
    assert "5_vwap_pullback_cont" in blob
    assert "6_avwap_ob_confluence" in blob
    assert "4_pending_user_confirm" not in blob
    assert "5_pending_user_confirm" not in blob
    assert "6_pending_user_confirm" not in blob
    var = dash["templating"]["list"][0]
    assert var["name"] == "setup_type"
    texts = [opt["text"] for opt in var["options"]]
    values = [opt["value"] for opt in var["options"]]
    assert texts == list(PRODUCT_KEYS)
    assert values == list(PERFORMANCE_SETUP_TYPES)
    assert "mss_break" not in values
    assert "order_block" not in values
    assert "sweep_mss" not in values
    sql = " ".join(
        t.get("rawSql", "") for p in dash["panels"] for t in p.get("targets", [])
    )
    assert "WHEN 'sd_extension_fade' THEN '4_sd_extension_fade'" in sql
    assert "mss_break" not in sql
    assert "pending_user_confirm" not in sql


def test_openapi_documents_performance_summary():
    spec = _client().get("/openapi.json").json()
    assert "/performance/summary" in spec["paths"]
    desc = spec["paths"]["/performance/summary"]["get"].get("description", "")
    assert "3_po3_asia_range_sweep" in desc
    assert "4_sd_extension_fade" in desc
    assert "3_po3_judas" not in desc
    assert "keyed by `product_key`" in desc
    props = spec["components"]["schemas"]["PerformanceBucket"]["properties"]
    assert "product_key" in props
    assert "setup_type" in props
    assert "sharpe_ratio" in props
    pk_desc = props["product_key"].get("description", "")
    assert "3_po3_asia_range_sweep" in pk_desc
    assert "4_sd_extension_fade" in pk_desc
    assert "pending_user_confirm" not in pk_desc
    by_desc = spec["components"]["schemas"]["PerformanceSummary"]["properties"]["by_setup"].get(
        "description", ""
    )
    assert "1_liquidity_sweep_vwap_reclaim" in by_desc
    assert "4_sd_extension_fade" in by_desc
    assert "Keyed by product_key" in by_desc
