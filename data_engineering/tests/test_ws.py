from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.config import Settings
from sniper_data.models import AssetClass, OHLCVBar, SessionLevels, SessionType, Timeframe


def _app(store=None, bars=None):
    store = store or InMemoryStateStore()
    app = create_app(
        store=store,
        settings=Settings(use_inmemory=True),
        bars=bars if bars is not None else InMemoryOHLCVStore(),
    )
    return TestClient(app), store, app.state.bars


def test_websocket_receives_vwap_updates():
    client, store, _ = _app()
    with client.websocket_connect("/v1/ws/vwap?symbol=btc-usdt") as ws:
        store.channels.setdefault("vwap:BTCUSDT", []).append(
            {"symbol": "BTCUSDT", "anchor_type": "session", "vwap": 101.25}
        )
        msg = ws.receive_json()
        assert msg["vwap"] == 101.25
        assert msg["symbol"] == "BTCUSDT"


def test_websocket_session_seeds_and_follows_channel():
    store = InMemoryStateStore()
    book = SessionLevels(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        session_type=SessionType.LONDON,
        session_start_ms=1,
        session_end_ms=2,
        open=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=10.0,
        updated_ts_ms=3,
    )
    store.data["session:BTCUSDT:london"] = book.model_dump_json()
    client, store, _ = _app(store=store)
    with client.websocket_connect("/v1/ws/session?symbol=btc-usdt") as ws:
        seeded = ws.receive_json()
        assert seeded["session_type"] == "london"
        assert seeded["high"] == 102.0
        live = book.model_copy(update={"close": 103.0, "high": 103.0})
        store.channels.setdefault("session:BTCUSDT", []).append(live.model_dump(mode="json"))
        nxt = ws.receive_json()
        assert nxt["close"] == 103.0
        assert nxt["session_type"] == "london"


def test_websocket_ohlcv_seeds_and_follows_channel():
    bars = InMemoryOHLCVStore()
    seed = OHLCVBar(
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        timeframe=Timeframe.M1,
        open_ts_ms=1_717_502_400_000,
        close_ts_ms=1_717_502_460_000,
        open=100.0,
        high=101.0,
        low=99.5,
        close=100.5,
        volume=14.0,
        n_ticks=2,
        buy_volume=10.0,
        sell_volume=4.0,
    )
    bars.bars.append(seed)
    client, store, _ = _app(bars=bars)
    with client.websocket_connect("/v1/ws/ohlcv?symbol=BTCUSDT&timeframe=1m") as ws:
        seeded = ws.receive_json()
        assert seeded["timeframe"] == "1m"
        assert seeded["buy_volume"] == 10.0
        assert seeded["sell_volume"] == 4.0
        live = seed.model_copy(update={"open_ts_ms": seed.open_ts_ms + 60_000, "close": 102.0})
        store.channels.setdefault("ohlcv:BTCUSDT:1m", []).append(live.model_dump(mode="json"))
        nxt = ws.receive_json()
        assert nxt["close"] == 102.0
        assert nxt["symbol"] == "BTCUSDT"


def test_websocket_ohlcv_requires_timeframe():
    client, _, _ = _app()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/ws/ohlcv?symbol=BTCUSDT"):
            pass
