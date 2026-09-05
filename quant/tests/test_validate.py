from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings


REQUIRED = {"approved", "reason", "adjusted_position_size"}


def _client(state: RiskState | None = None):
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=state or RiskState(equity=100_000))
    app = create_app(settings=settings, signals=InMemorySignalStore(), engine=engine)
    return TestClient(app), engine


def _payload(**kwargs):
    body = {
        "schema_version": "1.1",
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "setup_type": "sweep_reclaim",
        "side": "long",
        "confidence": 0.88,
        "ts_ms": 1_700_000_000_000,
        "entry": 100.0,
        "stop": 96.0,
        "target": 108.0,
        "timeframe": "15m",
        "trigger_event_ids": ["evt-1"],
    }
    body.update(kwargs)
    return body


def test_validate_response_shape_approved():
    http, _ = _client()
    resp = http.post("/risk/validate", json=_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert REQUIRED <= set(body)
    assert body["approved"] is True
    assert isinstance(body["reason"], str)
    assert isinstance(body["adjusted_position_size"], (int, float))
    assert body["reason"] == "ok"
    assert "id" not in _payload()


def test_validate_omits_id_and_rejects_unknown_setup():
    http, _ = _client()
    resp = http.post("/risk/validate", json=_payload(setup_type="ote"))
    assert resp.status_code == 422


def test_validate_requires_risk_fields():
    http, _ = _client()
    body = _payload()
    del body["entry"]
    del body["stop"]
    del body["target"]
    del body["timeframe"]
    del body["trigger_event_ids"]
    assert http.post("/risk/validate", json=body).status_code == 422


def test_validate_bad_timeframe():
    http, _ = _client()
    assert http.post("/risk/validate", json=_payload(timeframe="1h")).status_code == 422


def test_validate_reject_shape_conflict():
    http, _ = _client()
    created = http.post("/signals", json=_payload())
    assert created.status_code == 201
    body = http.post("/risk/validate", json=_payload()).json()
    assert REQUIRED <= set(body)
    assert body["approved"] is False
    assert body["reason"] == "same_symbol_conflict"
    assert body["adjusted_position_size"] == 0.0


def test_openapi_and_health():
    http, _ = _client()
    assert http.get("/health").json()["ok"] is True
    spec = http.get("/openapi.json").json()
    assert "/risk/validate" in spec["paths"]
    assert "post" in spec["paths"]["/risk/validate"]
    assert http.get("/docs").status_code == 200
    params = http.get("/risk/params").json()
    assert params["risk_fraction"] == 0.02
    assert params["max_daily_loss_frac"] == 0.03
    assert params["setup_types"] == [
        "sweep_reclaim",
        "fvg_entry",
        "mss_break",
        "order_block",
        "sweep_mss",
        "ob_fvg",
    ]
    schema = spec["components"]["schemas"]["CandidateSignal"]
    assert "id" not in schema.get("properties", {})
    assert set(schema["required"]) >= {
        "symbol",
        "asset_class",
        "setup_type",
        "side",
        "ts_ms",
        "entry",
        "stop",
        "target",
        "timeframe",
        "trigger_event_ids",
    }


def test_validate_session_and_proposed_size():
    http, _ = _client()
    ok = http.post(
        "/risk/validate",
        json=_payload(session_type="ny_am", proposed_position_size=50),
    ).json()
    assert ok["approved"] is True
    assert ok["adjusted_position_size"] == 50.0
    over = http.post(
        "/risk/validate",
        json=_payload(symbol="ETHUSDT", proposed_position_size=10_000),
    ).json()
    assert over["approved"] is False
    assert over["reason"] == "position_size_exceeds_limit"
    assert over["adjusted_position_size"] == 500.0


def test_validate_low_rr_invalid_levels():
    http, _ = _client()
    body = http.post(
        "/risk/validate",
        json=_payload(stop=96.0, target=101.0),
    ).json()
    assert body["approved"] is False
    assert body["reason"] == "invalid_levels"


def test_publish_assigns_id_after_approval():
    http, _ = _client()
    created = http.post("/signals", json=_payload()).json()
    assert created["id"]
    assert created["status"] == "ACTIVE"
    listed = http.get("/signals", params={"symbol": "BTCUSDT", "status": "ACTIVE"}).json()
    assert listed["count"] == 1
    patched = http.patch(f"/signals/{created['id']}", json={"status": "TP_HIT"}).json()
    assert patched["status"] == "TP_HIT"
    assert http.get("/signals", params={"status": "ACTIVE"}).json()["count"] == 0
