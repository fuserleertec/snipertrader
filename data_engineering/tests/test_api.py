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


def test_phase2_anchor_avwap_volume_profile_kill_zone(client):
    http, store = client
    created = http.post(
        "/v1/anchors",
        json={
            "symbol": "btc-usdt",
            "anchor_time": 1725458400000,
            "anchor_price": 64000.0,
            "source": "manual",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["source"] == "manual"
    anchor_id = body["anchor_id"]
    listed = http.get("/v1/anchors?symbol=BTCUSDT").json()
    assert listed["anchors"][0]["anchor_id"] == anchor_id

    store.data["avwap:BTCUSDT:" + anchor_id] = (
        '{"anchor_id":"%s","symbol":"BTCUSDT","anchor_time":1725458400000,'
        '"anchor_price":64000.0,"vwap_value":64500.0,'
        '"bands":{"plus_1_sigma":64700.0,"plus_2_sigma":64950.0,"plus_3_sigma":65200.0,'
        '"minus_1_sigma":64300.0,"minus_2_sigma":64050.0,"minus_3_sigma":63800.0},'
        '"asset_class":"crypto"}' % anchor_id
    )
    store.data["avwap:latest:BTCUSDT"] = store.data["avwap:BTCUSDT:" + anchor_id]
    latest = http.get("/v1/avwap/BTCUSDT").json()
    assert latest["vwap_value"] == 64500.0
    assert latest["bands"]["plus_1_sigma"] == 64700.0
    assert "schema_version" not in latest
    one = http.get(f"/v1/avwap/BTCUSDT/{anchor_id}").json()
    assert one["anchor_id"] == anchor_id

    store.data["volume_profile:BTCUSDT:ny_am"] = (
        '{"symbol":"BTCUSDT","session_type":"ny_am",'
        '"high_volume_nodes":[{"price":65000.0,"volume":1500.5}],'
        '"low_volume_nodes":[{"price":64900.0,"volume":200.0}],'
        '"poc":65000.0,"timestamp":1725459000000}'
    )
    vp = http.get("/v1/volume-profile/BTCUSDT/ny_am").json()
    assert vp["poc"] == 65000.0
    assert vp["session_type"] == "ny_am"

    store.data["kill_zone:BTCUSDT"] = (
        '{"symbol":"BTCUSDT","kill_zone":"ny_am","start_time":1,'
        '"end_time":2,"active":true,"asset_class":"crypto"}'
    )
    store.data["kill_zone:active:crypto"] = (
        '{"kill_zone":"ny_am","start_time":1,"end_time":2,"active":true,"asset_class":"crypto"}'
    )
    kz = http.get("/v1/kill-zone/BTCUSDT").json()
    assert kz["active"] is True
    klass = http.get("/v1/kill-zone/active/crypto").json()
    assert klass["kill_zone"] == "ny_am"
    metrics = http.get("/metrics")
    assert metrics.status_code == 200
    assert b"sniper_http_request_duration_seconds" in metrics.content
