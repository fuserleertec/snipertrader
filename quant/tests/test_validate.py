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
    assert body.get("size_unit") == "asset"
    assert "id" not in _payload()


def test_validate_omits_id_and_rejects_unknown_setup():
    http, _ = _client()
    resp = http.post("/risk/validate", json=_payload(setup_type="ote"))
    assert resp.status_code == 422


def test_validate_accepts_po3_judas():
    http, _ = _client()
    resp = http.post("/risk/validate", json=_payload(setup_type="po3_judas"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is True
    assert body["reason"] == "ok"


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
    body = http.post(
        "/risk/validate",
        json=_payload(side="short", stop=104.0, target=92.0),
    ).json()
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
    assert "get" in spec["paths"]["/signals"]
    assert "/ws/signals" in spec["paths"]
    assert "/signals/history" in spec["paths"]
    props = spec["components"]["schemas"]["SignalView"]["properties"]
    assert "realized_r" in props
    assert "exit_price" in props
    assert "closed_ts_ms" in props
    assert http.get("/docs").status_code == 200
    params = http.get("/risk/params").json()
    assert params["risk_fraction"] == 0.02
    assert params["max_daily_loss_frac"] == 0.03
    assert params["setup_types"] == [
        "sweep_reclaim",
        "fvg_entry",
        "po3_judas",
        "sd_extension_fade",
        "vwap_pullback_cont",
        "avwap_ob_confluence",
    ]
    for dead in ("mss_break", "order_block", "sweep_mss", "ob_fvg"):
        assert http.post("/risk/validate", json=_payload(setup_type=dead)).status_code == 422
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
    assert listed["items"][0]["id"] == created["id"]
    assert listed["next_cursor"] is None
    patched = http.patch(f"/signals/{created['id']}", json={"status": "TP_HIT"}).json()
    assert patched["status"] == "TP_HIT"
    assert http.get("/signals", params={"status": "ACTIVE"}).json()["items"] == []


def test_e2e_ml_must_validate_before_ingest():
    """ML simulation: /risk/validate first; publish only when approved."""
    http, _ = _client()
    candidate = _payload()
    assert "id" not in candidate
    decision = http.post("/risk/validate", json=candidate).json()
    assert decision["approved"] is True
    assert decision["reason"] == "ok"
    assert decision["size_unit"] == "asset"
    published = {
        **candidate,
        "id": "ml-sim-1",
        "position_size": decision["adjusted_position_size"],
        "status": "ACTIVE",
    }
    stored = http.post("/v1/signals/ingest", json=published)
    assert stored.status_code == 200
    assert stored.json()["id"] == "ml-sim-1"
    assert stored.json()["status"] == "ACTIVE"

    over = http.post(
        "/risk/validate",
        json=_payload(symbol="ETHUSDT", proposed_position_size=10_000),
    ).json()
    assert over["approved"] is False
    assert over["reason"] == "position_size_exceeds_limit"
    # Rejected candidates must not be published.
    assert http.get("/signals/ml-over").status_code == 404

    opposite = http.post(
        "/risk/validate",
        json=_payload(side="short", stop=104.0, target=92.0),
    ).json()
    assert opposite["approved"] is False
    assert opposite["reason"] == "same_symbol_conflict"
    assert opposite["checks"]["same_symbol_conflict"]["rule"] == "opposite_direction"


# Locked bodies from ML E2E sims (PR #7). Omit id; ts_ms is a stand-in for "now".
ML_LOCKED_BODIES = (
    {
        "schema_version": "1.1",
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "setup_type": "sweep_reclaim",
        "side": "long",
        "entry": 100.5,
        "stop": 99.09,
        "target": 104,
        "timeframe": "5m",
        "trigger_event_ids": ["swp-buy-low", "mss-reclaim-long"],
        "confidence": 0.9,
        "ts_ms": 1_700_000_000_000,
    },
    {
        "schema_version": "1.1",
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "setup_type": "fvg_entry",
        "side": "long",
        "entry": 100.45,
        "stop": 99.53,
        "target": 103.5,
        "timeframe": "1m",
        "trigger_event_ids": ["fvg-bull-vwap"],
        "confidence": 1.0,
        "ts_ms": 1_700_000_000_000,
    },
    {
        "schema_version": "1.1",
        "symbol": "BTCUSDT",
        "asset_class": "crypto",
        "setup_type": "po3_judas",
        "side": "short",
        "entry": 100.8,
        "stop": 104.49,
        "target": 90,
        "timeframe": "5m",
        "trigger_event_ids": ["swp-asia-high"],
        "confidence": 1.0,
        "session_type": "ny_am",
        "ts_ms": 1_700_000_000_000,
    },
)


def test_ml_pr7_locked_bodies_approve():
    http, _ = _client()
    for body in ML_LOCKED_BODIES:
        assert "id" not in body
        resp = http.post("/risk/validate", json=body)
        assert resp.status_code == 200, body["setup_type"]
        data = resp.json()
        assert data["approved"] is True, data
        assert data["reason"] == "ok"
        assert data["size_unit"] == "asset"
        assert data["adjusted_position_size"] > 0
    # Validate never persists.
    assert http.get("/signals").json()["items"] == []


def test_rejects_do_not_proceed_to_signals():
    """Oversized / inverted / daily-loss rejects must not create ACTIVE rows."""
    http, _ = _client()
    over = _payload(symbol="ETHUSDT", proposed_position_size=10_000)
    decision = http.post("/risk/validate", json=over).json()
    assert decision["approved"] is False
    assert decision["reason"] == "position_size_exceeds_limit"
    pub = http.post("/signals", json=over)
    assert pub.status_code == 409
    assert pub.json()["detail"]["validate"]["reason"] == "position_size_exceeds_limit"

    inverted = _payload(stop=104.0, target=99.0)
    inv = http.post("/risk/validate", json=inverted).json()
    assert inv["approved"] is False
    assert inv["reason"] == "invalid_levels"
    assert http.post("/signals", json=inverted).status_code == 409
    assert http.get("/signals").json()["items"] == []

    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000, daily_pnl=-3_000))
    lost = TestClient(
        create_app(settings=settings, signals=InMemorySignalStore(), engine=engine)
    )
    hit = _payload(symbol="SOLUSDT")
    daily = lost.post("/risk/validate", json=hit).json()
    assert daily["approved"] is False
    assert daily["reason"] == "daily_loss_limit"
    assert lost.post("/signals", json=hit).status_code == 409
    assert lost.get("/signals").json()["items"] == []
