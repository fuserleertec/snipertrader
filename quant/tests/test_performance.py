"""GET /performance/summary — Frontend contract (by_setup keyed by setup_type)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.performance import summarize_signals
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import PERFORMANCE_SETUP_TYPES, SETUP_TYPE_TO_PRODUCT
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
    assert set(PERFORMANCE_SETUP_TYPES) <= set(body["by_setup"])
    assert "ob_fvg" not in body["by_setup"]
    for name in PERFORMANCE_SETUP_TYPES:
        bucket = body["by_setup"][name]
        assert BUCKET_FIELDS <= set(bucket)
        assert bucket["setup_type"] == name
        assert bucket["product_key"] == SETUP_TYPE_TO_PRODUCT[name]
        assert bucket["win_rate"] == 0.0
        assert bucket["average_rr"] == 0.0
        assert bucket["signals_today"] == 0
        assert bucket["signals_week"] == 0
    assert body["by_setup"]["po3_judas"]["product_key"] == "3_po3_judas"
    assert body["by_setup"]["mss_break"]["product_key"] == "4_mss_break"
    assert body["by_setup"]["order_block"]["product_key"] == "5_order_block"
    assert body["by_setup"]["sweep_mss"]["product_key"] == "6_sweep_mss"


def test_summary_from_realized_r():
    empty = summarize_signals([])
    assert empty.win_rate == 0.0
    assert set(PERFORMANCE_SETUP_TYPES) <= set(empty.by_setup)

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
    sweep = body["by_setup"]["sweep_reclaim"]
    assert sweep["setup_type"] == "sweep_reclaim"
    assert sweep["product_key"] == "1_liquidity_sweep_vwap_reclaim"
    assert sweep["win_rate"] == 1.0
    assert sweep["average_rr"] == 2.0
    assert sweep["n_signals"] == 1
    assert body["by_setup"]["mss_break"]["win_rate"] == 0.0


def test_openapi_documents_performance_summary():
    spec = _client().get("/openapi.json").json()
    assert "/performance/summary" in spec["paths"]
    props = spec["components"]["schemas"]["PerformanceBucket"]["properties"]
    assert "product_key" in props
    assert "setup_type" in props
    assert "sharpe_ratio" in props
