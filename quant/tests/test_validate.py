from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.models import OpenPosition, Side
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
        "setup_type": "liquidity_sweep",
        "side": "long",
        "confidence": 0.88,
        "ts_ms": 1_700_000_000_000,
        "entry": 100.0,
        "atr": 2.0,
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
    # no id required on the request
    assert "id" not in _payload()


def test_validate_id_optional():
    http, _ = _client()
    resp = http.post("/risk/validate", json=_payload(id="preview-only"))
    assert resp.status_code == 200
    assert resp.json()["approved"] is True


def test_validate_reject_shape_conflict():
    state = RiskState(
        equity=100_000,
        positions=[OpenPosition(symbol="BTCUSDT", side=Side.LONG, size=1, entry=100)],
    )
    http, _ = _client(state)
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
    assert len(params["setup_types"]) == 6


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
