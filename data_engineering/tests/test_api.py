from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import Settings
from sniper_data.models import AssetClass, SessionLevels, SessionType, VWAPValues, AnchorType


@pytest.fixture
def client():
    store = InMemoryStateStore()
    app = create_app(store=store, settings=Settings(USE_INMEMORY=True))
    return TestClient(app), store


def test_health_and_vwap_roundtrip(client):
    http, store = client
    assert http.get("/health").json()["ok"] is True

    snap = VWAPValues(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        anchor_type=AnchorType.SESSION,
        session_type=SessionType.LONDON,
        anchor_start_ms=1,
        vwap=100.0,
        sigma=1.5,
        band_m3=95.5,
        band_m2=97.0,
        band_m1=98.5,
        band_p1=101.5,
        band_p2=103.0,
        band_p3=104.5,
        cum_volume=10.0,
        n_obs=3,
        updated_ts_ms=2,
    )
    store.data["vwap:BTCUSDT:session"] = snap.model_dump_json()
    body = http.get("/v1/vwap/btc-usdt?anchor=session").json()
    assert body["vwap"] == 100.0
    assert body["band_p2"] == 103.0
    assert http.get("/v1/vwap/BTCUSDT?anchor=weekly").status_code == 404


def test_session_endpoints(client):
    http, store = client

    levels = SessionLevels(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        session_type=SessionType.RTH,
        session_start_ms=1,
        session_end_ms=2,
        open=1,
        high=2,
        low=1,
        close=1.5,
        volume=10,
        updated_ts_ms=3,
    )
    store.data["session:AAPL:rth"] = levels.model_dump_json()
    body = http.get("/v1/session/aapl/rth").json()
    assert body["high"] == 2
    listed = http.get("/v1/session/AAPL").json()
    assert listed["sessions"][0]["key"] == "session:AAPL:rth"
