from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.config import Settings
from sniper_data.models import (
    AssetClass,
    OHLCVBar,
    SessionLevels,
    SessionType,
    Timeframe,
    VWAPValues,
    AnchorType,
)


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


def test_ohlcv_http_history():
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    bars.bars.append(
        OHLCVBar(
            symbol="BTCUSDT",
            asset_class=AssetClass.CRYPTO,
            timeframe=Timeframe.M5,
            open_ts_ms=1_717_502_400_000,
            close_ts_ms=1_717_502_700_000,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=20.0,
            n_ticks=8,
            buy_volume=12.0,
            sell_volume=8.0,
        )
    )
    app = create_app(store=store, settings=Settings(use_inmemory=True), bars=bars)
    http = TestClient(app)
    missing_tf = http.get("/v1/ohlcv/BTCUSDT")
    assert missing_tf.status_code == 422
    body = http.get("/v1/ohlcv/btc-usdt?timeframe=5m&limit=200").json()
    assert body["symbol"] == "BTCUSDT"
    assert body["timeframe"] == "5m"
    assert len(body["bars"]) == 1
    assert body["bars"][0]["buy_volume"] == 12.0
    assert body["bars"][0]["sell_volume"] == 8.0
    assert "delta" not in body["bars"][0]
