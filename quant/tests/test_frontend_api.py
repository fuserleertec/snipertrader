from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.models import SIGNAL_VIEW_FIELDS
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings
from tests.test_validate import _payload


SIGNAL_KEYS = set(SIGNAL_VIEW_FIELDS)


def _client():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    app = create_app(settings=settings, signals=InMemorySignalStore(), engine=engine)
    return TestClient(app)


def test_list_items_and_signal_shape():
    http = _client()
    created = http.post("/signals", json=_payload(ref_session="ny_am")).json()
    assert SIGNAL_KEYS <= set(created)
    assert created["setup_type"] == "sweep_reclaim"
    assert created["status"] == "ACTIVE"
    assert created["timeframe"] == "15m"
    assert created["trigger_event_ids"] == ["evt-1"]
    assert created["ref_session"] == "ny_am"

    listed = http.get("/signals").json()
    assert set(listed) == {"items", "next_cursor"}
    assert listed["next_cursor"] is None
    assert SIGNAL_KEYS <= set(listed["items"][0])

    one = http.get(f"/signals/{created['id']}").json()
    assert one["id"] == created["id"]
    assert SIGNAL_KEYS <= set(one)


def test_filters_setup_type_status_time():
    http = _client()
    http.post("/signals", json=_payload(symbol="BTCUSDT", setup_type="sweep_reclaim", ts_ms=1000))
    http.post("/signals", json=_payload(symbol="ETHUSDT", setup_type="fvg_entry", ts_ms=2000))
    http.post("/signals", json=_payload(symbol="AAPL", setup_type="sd_extension_fade", ts_ms=3000, asset_class="equity"))

    by_setup = http.get("/signals", params={"setup_type": "fvg_entry"}).json()["items"]
    assert [r["symbol"] for r in by_setup] == ["ETHUSDT"]

    by_sym = http.get("/signals", params={"symbol": "aapl"}).json()["items"]
    assert [r["setup_type"] for r in by_sym] == ["sd_extension_fade"]

    window = http.get("/signals", params={"from_ts": 1500, "to_ts": 2500}).json()["items"]
    assert [r["symbol"] for r in window] == ["ETHUSDT"]


def test_cursor_pagination():
    http = _client()
    for i, setup in enumerate(("sweep_reclaim", "fvg_entry", "sd_extension_fade")):
        http.post(
            "/signals",
            json=_payload(symbol=f"S{i}USDT", setup_type=setup, ts_ms=1000 + i, asset_class="crypto"),
        )
    page1 = http.get("/signals", params={"limit": 2}).json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"]
    page2 = http.get("/signals", params={"limit": 2, "cursor": page1["next_cursor"]}).json()
    assert len(page2["items"]) == 1
    ids = {r["id"] for r in page1["items"]} | {r["id"] for r in page2["items"]}
    assert len(ids) == 3


def test_ws_upsert_and_status():
    http = _client()
    with http.websocket_connect("/ws/signals") as ws:
        created = http.post("/signals", json=_payload()).json()
        upsert = ws.receive_json()
        assert upsert["type"] == "signal.upsert"
        assert SIGNAL_KEYS <= set(upsert["signal"])
        assert upsert["signal"]["id"] == created["id"]
        assert upsert["signal"]["status"] == "ACTIVE"
        assert upsert["signal"]["realized_r"] is None
        assert upsert["signal"]["exit_price"] is None
        assert upsert["signal"]["closed_ts_ms"] is None

        patched = http.patch(
            f"/signals/{created['id']}",
            json={"status": "SL_HIT", "exit_price": 96.0, "realized_r": -1.0, "closed_ts_ms": 9},
        ).json()
        status = ws.receive_json()
        assert status["type"] == "signal.status"
        assert status["signal"]["status"] == "SL_HIT"
        assert status["signal"]["realized_r"] == -1.0
        assert status["signal"]["exit_price"] == 96.0
        assert status["signal"]["closed_ts_ms"] == 9
        assert patched["status"] == "SL_HIT"
        assert patched["realized_r"] == -1.0
        assert patched["exit_price"] == 96.0
        assert patched["closed_ts_ms"] == 9


def test_history_route_matches_list():
    http = _client()
    spec = http.get("/openapi.json").json()
    assert "/signals" in spec["paths"]
    assert "/signals/history" in spec["paths"]
    http.post("/signals", json=_payload(ts_ms=5000))
    listed = http.get("/signals").json()
    hist = http.get("/signals/history").json()
    assert [r["id"] for r in listed["items"]] == [r["id"] for r in hist["items"]]


def test_close_fields_on_list_detail_and_cancelled_null():
    http = _client()
    created = http.post("/signals", json=_payload()).json()
    assert created["realized_r"] is None
    assert created["exit_price"] is None
    assert created["closed_ts_ms"] is None

    closed = http.patch(
        f"/signals/{created['id']}",
        json={"status": "TP_HIT", "exit_price": 108.0, "realized_r": 2.0, "closed_ts_ms": 42},
    ).json()
    assert closed["realized_r"] == 2.0
    assert closed["exit_price"] == 108.0
    assert closed["closed_ts_ms"] == 42

    listed = http.get("/signals", params={"status": "TP_HIT"}).json()["items"]
    assert listed[0]["realized_r"] == 2.0
    assert listed[0]["exit_price"] == 108.0
    assert listed[0]["closed_ts_ms"] == 42

    one = http.get(f"/signals/{created['id']}").json()
    assert one["realized_r"] == 2.0
    assert one["exit_price"] == 108.0
    assert one["closed_ts_ms"] == 42

    other = http.post("/signals", json=_payload(symbol="ETHUSDT")).json()
    cancelled = http.patch(f"/signals/{other['id']}", json={"status": "CANCELLED"}).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["realized_r"] is None
    assert cancelled["r_multiple"] is None
