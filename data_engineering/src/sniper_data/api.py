"""HTTP + WebSocket API for Quant Developers (VWAP and session levels)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore, StateStore, decode
from sniper_data.config import KAFKA_TOPICS, Settings, get_settings
from sniper_data.sessions import redis_session_key
from sniper_data.symbols import normalize_symbol
from sniper_data.vwap import redis_vwap_key

log = logging.getLogger(__name__)

API_DESCRIPTION = """
# SniperTrader market-data API (Phase 1 / Rev. 1.1)

Real-time state is served from Redis. Kafka is the durable stream;
TimescaleDB holds historical OHLCV.

## VWAP

`GET /v1/vwap/{symbol}?anchor=session|weekly|rolling`

Bands are **volume-weighted**:

    σ = sqrt( Σ v_i (p_i − VWAP)² / Σ v_i )

Redis key: `vwap:{symbol}:{anchor}`

## Sessions

`GET /v1/session/{symbol}/{session_type}`

`GET /v1/session/{symbol}` — all cached session books for the symbol.

Redis key: `session:{symbol}:{session_type}`

## WebSocket

`WS /v1/ws/vwap?symbol=BTCUSDT` — pushes every VWAP update published on
Redis channel `vwap:{symbol}`.
"""


def _store_from_settings(settings: Settings) -> StateStore:
    if settings.use_inmemory:
        return InMemoryStateStore()
    return RedisStateStore(settings.redis_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.store = _store_from_settings(settings)
    yield
    await app.state.store.close()


def create_app(store: StateStore | None = None, settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="SniperTrader Data API",
        version="1.1.0",
        description=API_DESCRIPTION,
        lifespan=None if store is not None else lifespan,
    )
    if store is not None:
        app.state.store = store
        app.state.settings = settings or get_settings()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        ok = await app.state.store.ping()
        return {
            "ok": ok,
            "inmemory": isinstance(app.state.store, InMemoryStateStore),
            "topics": list(KAFKA_TOPICS),
        }

    @app.get("/v1/vwap/{symbol}")
    async def get_vwap(
        symbol: str,
        anchor: str = Query(default="session", pattern="^(session|weekly|rolling)$"),
    ) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        key = redis_vwap_key(symbol, anchor)
        payload = await app.state.store.get(key)
        if payload is None:
            raise HTTPException(404, f"no VWAP for {key}")
        return JSONResponse(payload)

    @app.get("/v1/session/{symbol}/{session_type}")
    async def get_session(symbol: str, session_type: str) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        key = redis_session_key(symbol, session_type)
        payload = await app.state.store.get(key)
        if payload is None:
            raise HTTPException(404, f"no session book for {key}")
        return JSONResponse(payload)

    @app.get("/v1/session/{symbol}")
    async def list_sessions(symbol: str) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        keys = await app.state.store.scan(f"session:{symbol}:*")
        books = []
        for key in keys:
            val = await app.state.store.get(key)
            if val is not None:
                books.append({"key": key, "value": val})
        return JSONResponse({"symbol": symbol, "sessions": books})

    @app.websocket("/v1/ws/vwap")
    async def ws_vwap(websocket: WebSocket, symbol: str = Query(...)) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        store = app.state.store
        # Seed with current snapshot if present.
        for anchor in ("session", "weekly", "rolling"):
            snap = await store.get(redis_vwap_key(symbol, anchor))
            if snap is not None:
                await websocket.send_json(snap)

        if isinstance(store, InMemoryStateStore):
            last = 0
            channel = f"vwap:{symbol}"
            try:
                while True:
                    msgs = store.channels.get(channel, [])
                    if last < len(msgs):
                        for item in msgs[last:]:
                            await websocket.send_json(item)
                        last = len(msgs)
                    await asyncio.sleep(0.05)
            except WebSocketDisconnect:
                return

        import redis.asyncio as redis

        client = redis.from_url(app.state.settings.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(f"vwap:{symbol}")
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("data"):
                    await websocket.send_json(decode(msg["data"]))
                else:
                    await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            pass
        finally:
            await pubsub.unsubscribe(f"vwap:{symbol}")
            await pubsub.aclose()
            await client.aclose()

    return app


app = create_app()
