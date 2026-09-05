from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import Settings


def test_websocket_receives_vwap_updates():
    store = InMemoryStateStore()
    app = create_app(store=store, settings=Settings(use_inmemory=True))
    client = TestClient(app)
    with client.websocket_connect("/v1/ws/vwap?symbol=btc-usdt") as ws:
        store.channels.setdefault("vwap:BTCUSDT", []).append(
            {"symbol": "BTCUSDT", "anchor_type": "session", "vwap": 101.25}
        )
        msg = ws.receive_json()
        assert msg["vwap"] == 101.25
        assert msg["symbol"] == "BTCUSDT"
