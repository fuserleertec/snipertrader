from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.config import Settings
from sniper_data.zones import store_sweep
from sniper_data.models import (
    AssetClass,
    FVGZone,
    MssEvent,
    OHLCVBar,
    OrderBlock,
    SessionLevels,
    SessionType,
    SweepEvent,
    Timeframe,
)


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


def test_websocket_avwap_seeds_and_follows():
    store = InMemoryStateStore()
    snap = {
        "anchor_id": "a1",
        "symbol": "BTCUSDT",
        "anchor_time": 1,
        "anchor_price": 64000.0,
        "vwap_value": 64500.0,
        "bands": {
            "plus_1_sigma": 64700.0,
            "plus_2_sigma": 64950.0,
            "plus_3_sigma": 65200.0,
            "minus_1_sigma": 64300.0,
            "minus_2_sigma": 64050.0,
            "minus_3_sigma": 63800.0,
        },
        "asset_class": "crypto",
    }
    store.data["avwap:latest:BTCUSDT"] = __import__("json").dumps(snap)
    store.data["avwap:index:BTCUSDT"] = '["a1"]'
    store.data["avwap:BTCUSDT:a1"] = __import__("json").dumps(snap)
    client, store, _ = _app(store=store)
    with client.websocket_connect("/v1/ws/avwap?symbol=btc-usdt") as ws:
        seeded = ws.receive_json()
        assert seeded["vwap_value"] == 64500.0
        live = {**snap, "vwap_value": 64600.0}
        store.channels.setdefault("avwap:BTCUSDT", []).append(live)
        nxt = ws.receive_json()
        assert nxt["vwap_value"] == 64600.0


def test_websocket_ohlcv_requires_timeframe():
    client, _, _ = _app()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/ws/ohlcv?symbol=BTCUSDT"):
            pass


def _sweep() -> SweepEvent:
    return SweepEvent(
        id="s1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        side="sell",
        swept_level=65000.0,
        ts_ms=1_717_500_000_000,
        volume_profile="aggressive",
        confirmed=True,
    )


def _fvg() -> FVGZone:
    return FVGZone(
        id="z1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        direction="bullish",
        high=65010.0,
        low=64980.0,
        created_ts_ms=1_717_500_000_000,
        ttl_seconds=3600,
    )


def _mss() -> MssEvent:
    return MssEvent(
        id="m1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        ts_ms=1_717_500_000_000,
        direction="bullish",
        broken_level=64950.0,
        swing_high=65100.0,
        swing_low=64900.0,
        trigger_sweep_id="s1",
        trigger_sweep_side="buy",
        timeframe="5m",
    )


def _ob() -> OrderBlock:
    return OrderBlock(
        id="ob1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        direction="bearish",
        high=65100.0,
        low=65050.0,
        created_ts_ms=1_717_500_000_000,
        ttl_seconds=3600,
        timeframe=Timeframe.M15,
    )


@pytest.mark.parametrize(
    "route,prefix,seed_fn,live_update,expect_id,expect_field",
    [
        ("/v1/ws/sweep", "sweep", _sweep, {"confirmed": False}, "s1", ("side", "sell")),
        ("/v1/ws/fvg", "fvg", _fvg, {"mitigated": True}, "z1", ("direction", "bullish")),
        ("/v1/ws/mss", "mss", _mss, {"confirmed": True}, "m1", ("trigger_sweep_side", "buy")),
        ("/v1/ws/ob", "ob", _ob, {"mitigated": True}, "ob1", ("direction", "bearish")),
    ],
)
def test_websocket_zone_overlay_seeds_and_follows(
    route, prefix, seed_fn, live_update, expect_id, expect_field
):
    store = InMemoryStateStore()
    seed = seed_fn()
    key = f"{prefix}:{seed.symbol}:{seed.id}"
    store.data[key] = seed.model_dump_json()
    client, store, _ = _app(store=store)
    field, expected = expect_field
    with client.websocket_connect(f"{route}?symbol=btc-usdt") as ws:
        seeded = ws.receive_json()
        assert seeded["schema_version"] == "1.1"
        assert seeded["id"] == expect_id
        assert seeded["symbol"] == "BTCUSDT"
        assert seeded[field] == expected
        live = seed.model_copy(update=live_update)
        store.channels.setdefault(f"{prefix}:BTCUSDT", []).append(live.model_dump(mode="json"))
        nxt = ws.receive_json()
        assert nxt["schema_version"] == "1.1"
        assert nxt["id"] == expect_id
        for k, v in live_update.items():
            assert nxt[k] == v


def test_websocket_sweep_receives_store_publish():
    """store_sweep SET+EX then PUBLISH — WS client sees the live frame."""
    store = InMemoryStateStore()
    seed = _sweep()
    store.data["sweep:BTCUSDT:s1"] = seed.model_dump_json()
    client, store, _ = _app(store=store)
    with client.websocket_connect("/v1/ws/sweep?symbol=btc-usdt") as ws:
        seeded = ws.receive_json()
        assert seeded["id"] == "s1"
        live = seed.model_copy(update={"id": "s2", "confirmed": True, "reclaim": True})
        asyncio.run(store_sweep(store, live, ttl_seconds=3600))
        nxt = ws.receive_json()
        assert nxt["schema_version"] == "1.1"
        assert nxt["id"] == "s2"
        assert nxt["confirmed"] is True
        assert nxt["reclaim"] is True
        assert nxt["side"] == "sell"
