"""HTTP + WebSocket API for Quant Developers and frontend streams."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from sniper_data.avwap import (
    index_ids,
    persist_anchor,
    redis_avwap_channel,
    redis_avwap_key,
    redis_avwap_latest_key,
    redis_avwap_meta_key,
)
from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore, StateStore, decode
from sniper_data.bus.timescaledb import InMemoryOHLCVStore, OHLCVStore, TimescaleStore
from sniper_data.config import KAFKA_TOPICS, Settings, get_settings
from sniper_data.kill_zones import redis_kill_zone_active_key, redis_kill_zone_channel, redis_kill_zone_key
from sniper_data.metrics import metrics_response, record_http
from sniper_data.models import AnchorRegistration
from sniper_data.ohlcv import redis_ohlcv_channel
from sniper_data.sessions import redis_session_channel, redis_session_key
from sniper_data.symbols import infer_asset_class, normalize_symbol
from sniper_data.volume_profile import redis_volume_profile_channel, redis_volume_profile_key
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

## Phase 2 — Anchored VWAP (ML + Frontend)

`POST /v1/anchors` — register a manual / swing / earnings / news anchor.
Body: `{symbol, anchor_time, anchor_price, source?, asset_class?, anchor_id?}`.
`source` ∈ `manual` · `swing_high` · `swing_low` · `earnings` · `news`.
ML may also publish the same JSON to Kafka `anchor_events`.

`GET /v1/anchors?symbol=BTCUSDT` — registered anchor metadata.

`GET /v1/avwap/{symbol}` — latest AVWAP snapshot (`avwap:latest:{symbol}`).

`GET /v1/avwap/{symbol}/{anchor_id}` — Redis `avwap:{symbol}:{anchor_id}`.

`WS /v1/ws/avwap?symbol=BTCUSDT` — seed snapshots, then channel `avwap:{symbol}`.
Optional `anchor_id` filters frames to one anchor.

Payload fields (exact): `anchor_id`, `symbol`, `anchor_time`, `anchor_price`,
`vwap_value`, `bands.{plus|minus}_{1,2,3}_sigma`, `asset_class`.

## Phase 2 — Volume profile

`GET /v1/volume-profile/{symbol}` — all cached session profiles.

`GET /v1/volume-profile/{symbol}/{session_type}` — Redis
`volume_profile:{symbol}:{session_type}`.

`WS /v1/ws/volume-profile?symbol=BTCUSDT`

## Phase 2 — Kill zones

`GET /v1/kill-zone/{symbol}` — Redis `kill_zone:{symbol}`.

`GET /v1/kill-zone/active/{asset_class}` — Redis `kill_zone:active:{asset_class}`.

`WS /v1/ws/kill-zone?symbol=BTCUSDT`

## Metrics

`GET /metrics` — Prometheus scrape (API process).
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
        version="2.0.0",
        description=API_DESCRIPTION,
        lifespan=None if store is not None else lifespan,
    )
    if store is not None:
        app.state.store = store
        app.state.settings = settings or get_settings()
        app.state.bars = bars if bars is not None else InMemoryOHLCVStore()

    @app.middleware("http")
    async def _prometheus_http(request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        response = await call_next(request)
        record_http(request.method, _metric_route(request.url.path), time.perf_counter() - start)
        return response

    @app.get("/health")
    async def health() -> dict[str, Any]:
        ok = await app.state.store.ping()
        return {
            "ok": ok,
            "inmemory": isinstance(app.state.store, InMemoryStateStore),
            "topics": list(KAFKA_TOPICS),
            "bars": app.state.bars is not None,
            "phase": 2,
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

    @app.get("/metrics")
    async def prometheus_metrics() -> Response:
        payload, content_type = metrics_response()
        return Response(content=payload, media_type=content_type)

    @app.post("/v1/anchors", status_code=201)
    async def post_anchor(body: AnchorRegistration) -> JSONResponse:
        symbol = normalize_symbol(body.symbol)
        klass = infer_asset_class(symbol, body.asset_class)
        req = body.model_copy(update={"symbol": symbol, "asset_class": klass})
        from sniper_data.avwap import AnchoredVWAPEngine

        engine = AnchoredVWAPEngine()
        meta = engine.register(req)
        await persist_anchor(app.state.store, meta)
        return JSONResponse(
            {
                "anchor_id": meta.anchor_id,
                "symbol": meta.symbol,
                "anchor_time": meta.anchor_time,
                "anchor_price": meta.anchor_price,
                "source": meta.source.value,
                "asset_class": meta.asset_class.value,
                "created_ts_ms": meta.created_ts_ms,
                "redis_key": redis_avwap_key(meta.symbol, meta.anchor_id),
                "meta_key": redis_avwap_meta_key(meta.symbol, meta.anchor_id),
            },
            status_code=201,
        )

    @app.get("/v1/anchors")
    async def list_anchors(symbol: str = Query(...)) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        ids = await index_ids(app.state.store, symbol)
        anchors = []
        for anchor_id in ids:
            raw = await app.state.store.get(redis_avwap_meta_key(symbol, anchor_id))
            if raw is not None:
                anchors.append(raw)
        return JSONResponse({"symbol": symbol, "anchors": anchors})

    @app.get("/v1/avwap/{symbol}/{anchor_id}")
    async def get_avwap_one(symbol: str, anchor_id: str) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        payload = await app.state.store.get(redis_avwap_key(symbol, anchor_id))
        if payload is None:
            raise HTTPException(404, f"no AVWAP for {redis_avwap_key(symbol, anchor_id)}")
        return JSONResponse(payload)

    @app.get("/v1/avwap/{symbol}")
    async def get_avwap_latest(symbol: str) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        payload = await app.state.store.get(redis_avwap_latest_key(symbol))
        if payload is None:
            raise HTTPException(404, f"no AVWAP for {symbol}")
        return JSONResponse(payload)

    @app.get("/v1/volume-profile/{symbol}/{session_type}")
    async def get_volume_profile_one(symbol: str, session_type: str) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        key = redis_volume_profile_key(symbol, session_type)
        payload = await app.state.store.get(key)
        if payload is None:
            raise HTTPException(404, f"no volume profile for {key}")
        return JSONResponse(payload)

    @app.get("/v1/volume-profile/{symbol}")
    async def list_volume_profiles(symbol: str) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        keys = await app.state.store.scan(f"volume_profile:{symbol}:*")
        profiles = []
        for key in keys:
            if key.startswith("volume_profile:acc:"):
                continue
            val = await app.state.store.get(key)
            if val is not None:
                profiles.append({"key": key, "value": val})
        return JSONResponse({"symbol": symbol, "profiles": profiles})

    @app.get("/v1/kill-zone/active/{asset_class}")
    async def get_kill_zone_class(asset_class: str) -> JSONResponse:
        key = redis_kill_zone_active_key(asset_class)
        payload = await app.state.store.get(key)
        if payload is None:
            raise HTTPException(404, f"no active kill zone for {key}")
        return JSONResponse(payload)

    @app.get("/v1/kill-zone/{symbol}")
    async def get_kill_zone(symbol: str) -> JSONResponse:
        symbol = normalize_symbol(symbol)
        payload = await app.state.store.get(redis_kill_zone_key(symbol))
        if payload is None:
            raise HTTPException(404, f"no kill zone for {redis_kill_zone_key(symbol)}")
        return JSONResponse(payload)

    @app.websocket("/v1/ws/avwap")
    async def ws_avwap(
        websocket: WebSocket,
        symbol: str = Query(...),
        anchor_id: str | None = Query(default=None),
    ) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        store = app.state.store
        if anchor_id:
            snap = await store.get(redis_avwap_key(symbol, anchor_id))
            if snap is not None:
                await websocket.send_json(snap)
        else:
            latest = await store.get(redis_avwap_latest_key(symbol))
            if latest is not None:
                await websocket.send_json(latest)
            for aid in await index_ids(store, symbol):
                snap = await store.get(redis_avwap_key(symbol, aid))
                if snap is not None and (latest is None or snap.get("anchor_id") != latest.get("anchor_id")):
                    await websocket.send_json(snap)
        if anchor_id:
            await _ws_follow_filtered(
                websocket, store, app.state.settings, redis_avwap_channel(symbol), anchor_id
            )
        else:
            await _ws_follow_channel(
                websocket, store, app.state.settings, redis_avwap_channel(symbol)
            )

    @app.websocket("/v1/ws/volume-profile")
    async def ws_volume_profile(websocket: WebSocket, symbol: str = Query(...)) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        store = app.state.store
        keys = await store.scan(f"volume_profile:{symbol}:*")
        for key in sorted(keys):
            if key.startswith("volume_profile:acc:"):
                continue
            book = await store.get(key)
            if book is not None:
                await websocket.send_json(book)
        await _ws_follow_channel(
            websocket, store, app.state.settings, redis_volume_profile_channel(symbol)
        )

    @app.websocket("/v1/ws/kill-zone")
    async def ws_kill_zone(websocket: WebSocket, symbol: str = Query(...)) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        store = app.state.store
        current = await store.get(redis_kill_zone_key(symbol))
        if current is not None:
            await websocket.send_json(current)
        await _ws_follow_channel(
            websocket, store, app.state.settings, redis_kill_zone_channel(symbol)
        )

    return app


def _metric_route(path: str) -> str:
    for prefix in (
        "/v1/vwap",
        "/v1/avwap",
        "/v1/session",
        "/v1/ohlcv",
        "/v1/anchors",
        "/v1/volume-profile",
        "/v1/kill-zone",
        "/health",
        "/docs",
        "/openapi.json",
    ):
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return "other"


async def _ws_follow_filtered(
    websocket: WebSocket,
    store: StateStore,
    settings: Settings,
    channel: str,
    anchor_id: str,
) -> None:
    """Like ``_ws_follow_channel`` but only forward frames for one anchor."""

    def _match(item: Any) -> bool:
        return isinstance(item, dict) and item.get("anchor_id") == anchor_id

    if isinstance(store, InMemoryStateStore):
        last = 0
        try:
            while True:
                msgs = store.channels.get(channel, [])
                if last < len(msgs):
                    for item in msgs[last:]:
                        if _match(item):
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
                item = decode(msg["data"])
                if _match(item):
                    await websocket.send_json(item)
            else:
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


app = create_app()
