"""HTTP + WebSocket API for Quant Developers and frontend streams."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore, StateStore, decode
from sniper_data.bus.timescaledb import InMemoryOHLCVStore, OHLCVStore, TimescaleStore
from sniper_data.config import KAFKA_TOPICS, Settings, get_settings
from sniper_data.ohlcv import redis_ohlcv_channel
from sniper_data.sessions import redis_session_channel, redis_session_key
from sniper_data.symbols import normalize_symbol
from sniper_data.vwap import redis_vwap_key

log = logging.getLogger(__name__)

TIMEFRAME_RE = r"^(1m|5m|15m|1h|4h)$"

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

## OHLCV

`GET /v1/ohlcv/{symbol}?timeframe=1m&limit=200` — closed bars for chart bootstrap
(`timeframe` ∈ `1m` · `5m` · `15m` · `1h` · `4h`). Each bar matches
`ohlcv_bar.schema.json` (optional `buy_volume` / `sell_volume`).

## WebSocket

`WS /v1/ws/vwap?symbol=BTCUSDT` — seed current VWAP snapshots, then
Redis channel `vwap:{symbol}`.

`WS /v1/ws/session?symbol=BTCUSDT` — seed all `session:{symbol}:*` books,
then Redis channel `session:{symbol}`. Frames are `SessionLevels` JSON.

`WS /v1/ws/ohlcv?symbol=BTCUSDT&timeframe=1m` — optionally seed last `limit`
closed bars, then Redis channel `ohlcv:{symbol}:{timeframe}`. Frames are
`OHLCVBar` JSON (including optional `buy_volume` / `sell_volume`).
"""


def _store_from_settings(settings: Settings) -> StateStore:
    if settings.use_inmemory:
        return InMemoryStateStore()
    return RedisStateStore(settings.redis_url)


def _bars_from_settings(settings: Settings) -> OHLCVStore:
    if settings.use_inmemory:
        return InMemoryOHLCVStore()
    return TimescaleStore(settings.database_url)


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), 2000))


async def _ws_follow_channel(
    websocket: WebSocket,
    store: StateStore,
    settings: Settings,
    channel: str,
) -> None:
    if isinstance(store, InMemoryStateStore):
        last = 0
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
        return

    import redis.asyncio as redis

    client = redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
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
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.store = _store_from_settings(settings)
    bars = _bars_from_settings(settings)
    if isinstance(bars, TimescaleStore):
        try:
            await bars.start()
        except Exception as exc:  # noqa: BLE001
            log.warning("ohlcv store unavailable: %s", exc)
    app.state.bars = bars
    yield
    await app.state.store.close()
    await app.state.bars.close()


def create_app(
    store: StateStore | None = None,
    settings: Settings | None = None,
    bars: OHLCVStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="SniperTrader Data API",
        version="1.1.0",
        description=API_DESCRIPTION,
        lifespan=None if store is not None else lifespan,
    )
    if store is not None:
        app.state.store = store
        app.state.settings = settings or get_settings()
        app.state.bars = bars if bars is not None else InMemoryOHLCVStore()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        ok = await app.state.store.ping()
        return {
            "ok": ok,
            "inmemory": isinstance(app.state.store, InMemoryStateStore),
            "topics": list(KAFKA_TOPICS),
            "bars": app.state.bars is not None,
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

    @app.get("/v1/ohlcv/{symbol}")
    async def get_ohlcv(
        symbol: str,
        timeframe: str = Query(..., pattern=TIMEFRAME_RE),
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        store: OHLCVStore | None = getattr(app.state, "bars", None)
        if store is None:
            raise HTTPException(503, "ohlcv store unavailable")
        try:
            rows = await store.fetch(symbol, timeframe, limit=_clamp_limit(limit))
        except Exception as exc:  # noqa: BLE001
            log.warning("ohlcv fetch failed: %s", exc)
            raise HTTPException(503, "ohlcv store unavailable") from exc
        return JSONResponse(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": [b.model_dump(mode="json") for b in rows],
            }
        )

    @app.websocket("/v1/ws/vwap")
    async def ws_vwap(websocket: WebSocket, symbol: str = Query(...)) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        store = app.state.store
        for anchor in ("session", "weekly", "rolling"):
            snap = await store.get(redis_vwap_key(symbol, anchor))
            if snap is not None:
                await websocket.send_json(snap)
        await _ws_follow_channel(
            websocket, store, app.state.settings, f"vwap:{symbol}"
        )

    @app.websocket("/v1/ws/session")
    async def ws_session(websocket: WebSocket, symbol: str = Query(...)) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        store = app.state.store
        keys = await store.scan(f"session:{symbol}:*")
        for key in sorted(keys):
            book = await store.get(key)
            if book is not None:
                await websocket.send_json(book)
        await _ws_follow_channel(
            websocket, store, app.state.settings, redis_session_channel(symbol)
        )

    @app.websocket("/v1/ws/ohlcv")
    async def ws_ohlcv(
        websocket: WebSocket,
        symbol: str = Query(...),
        timeframe: str = Query(..., pattern=TIMEFRAME_RE),
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        bars: OHLCVStore | None = getattr(app.state, "bars", None)
        if bars is not None:
            try:
                history = await bars.fetch(symbol, timeframe, limit=_clamp_limit(limit))
            except Exception as exc:  # noqa: BLE001
                log.warning("ohlcv ws seed skipped: %s", exc)
                history = []
            for bar in history:
                await websocket.send_json(bar.model_dump(mode="json"))
        await _ws_follow_channel(
            websocket,
            app.state.store,
            app.state.settings,
            redis_ohlcv_channel(symbol, timeframe),
        )

    return app


app = create_app()
