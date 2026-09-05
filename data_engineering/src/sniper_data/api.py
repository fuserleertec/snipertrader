"""HTTP + WebSocket API for Quant Developers and frontend streams."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
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
from sniper_data.bus.resilience import Backoff
from sniper_data.bus.timescaledb import InMemoryOHLCVStore, OHLCVStore, TimescaleStore
from sniper_data.config import KAFKA_TOPICS, Settings, get_settings
from sniper_data.kill_zones import redis_kill_zone_active_key, redis_kill_zone_channel, redis_kill_zone_key
from sniper_data.metrics import (
    metrics_response,
    record_http,
    record_ws_connect,
    record_ws_disconnect,
    record_ws_drop,
    record_ws_message,
)
from sniper_data.models import AnchorRegistration
from sniper_data.performance import PerformanceStore, SignalOutcome
from sniper_data.setups import SETUP_KEYS, UnknownSetupError, resolve_setup_key
from sniper_data.ohlcv import redis_ohlcv_channel
from sniper_data.sessions import redis_session_channel, redis_session_key
from sniper_data.symbols import infer_asset_class, normalize_symbol
from sniper_data.volume_profile import redis_volume_profile_channel, redis_volume_profile_key
from sniper_data.vwap import redis_vwap_key
from sniper_data.zones import (
    fvg_channel,
    mss_channel,
    ob_channel,
    sweep_channel,
    zone_scan_pattern,
)

log = logging.getLogger(__name__)

TIMEFRAME_RE = r"^(1m|5m|15m|1h|4h)$"

API_DESCRIPTION = """
# SniperTrader market-data API (Phase 1 / Rev. 1.1 + Phase 2 + Phase 3)

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

`WS /v1/ws/sweep?symbol=BTCUSDT` — seed `sweep:{symbol}:*`, then channel `sweep:{symbol}`.
Frames are `SweepEvent` (`schema_version` `"1.1"`).

`WS /v1/ws/fvg?symbol=BTCUSDT` — seed `fvg:{symbol}:*`, then channel `fvg:{symbol}`.
Frames are `FVGZone` (`schema_version` `"1.1"`).

`WS /v1/ws/mss?symbol=BTCUSDT` — seed `mss:{symbol}:*`, then channel `mss:{symbol}`.
Frames are `MssEvent` (`schema_version` `"1.1"`).

`WS /v1/ws/ob?symbol=BTCUSDT` — seed `ob:{symbol}:*`, then channel `ob:{symbol}`.
Frames are `OrderBlock` (`schema_version` `"1.1"`).

`store_sweep` / `store_fvg` / `store_mss` / `store_ob` PUBLISH the same
payload to `prefix:{symbol}` after SET+EX (including mitigation updates).

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

## Phase 3 — Performance Snapshot (Frontend + Quant)

`GET /performance/summary` — exact envelope (`timestamp`, `overall`, `by_setup`).
Always includes the six Project Manager keys (zeros OK):

    1_liquidity_sweep_vwap_reclaim
    2_fvg_mitigation_vwap
    3_po3_asia_range_sweep      (setup_type `po3_judas`)
    4_sd_extension_fade
    5_vwap_pullback_cont
    6_avwap_ob_confluence

`GET /performance/summary?setup=1_liquidity_sweep_vwap_reclaim` — optional filter
on `overall` only; `by_setup` still returns all six keys.

`POST /performance/outcomes` — Quant / ML write a resolved signal:
`{setup|setup_type, won, rr, ts_ms?, signal_id?, symbol?}`.
Also accepted on Kafka topic `performance_outcomes`. **No Kafka-side risk
filter** — Quant `POST /risk/validate` stays at the publisher boundary.
"""


def _store_from_settings(settings: Settings) -> StateStore:
    if settings.use_inmemory:
        return InMemoryStateStore()
    return RedisStateStore(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        retries=settings.redis_retries,
    )


def _bars_from_settings(settings: Settings) -> OHLCVStore:
    if settings.use_inmemory:
        return InMemoryOHLCVStore()
    return TimescaleStore(settings.database_url)


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), 2000))


async def _ws_send(websocket: WebSocket, payload: Any, route: str, pending: list[int]) -> None:
    """Send one JSON frame; drop when the client backlog exceeds ``WS_BACKLOG``."""
    cap = pending[1] if len(pending) > 1 else 64
    if pending[0] >= cap:
        record_ws_drop(route)
        return
    pending[0] += 1
    start = time.perf_counter()
    try:
        await websocket.send_json(payload)
        record_ws_message(route, time.perf_counter() - start)
    finally:
        pending[0] -= 1


async def _ws_heartbeat(websocket: WebSocket, last: float, interval_s: float) -> float:
    if interval_s <= 0:
        return last
    now = time.monotonic()
    if now - last < interval_s:
        return last
    try:
        await websocket.send({"type": "websocket.ping"})
    except Exception:  # noqa: BLE001
        pass
    return now


async def _ws_follow_channel(
    websocket: WebSocket,
    store: StateStore,
    settings: Settings,
    channel: str,
    *,
    route: str = "channel",
    match: Callable[[Any], bool] | None = None,
) -> None:
    pending = [0, int(getattr(settings, "ws_backlog", 64) or 64)]
    hb_s = float(getattr(settings, "ws_heartbeat_s", 15.0) or 15.0)
    last_hb = time.monotonic()

    async def _emit(item: Any) -> None:
        if match is not None and not match(item):
            return
        await _ws_send(websocket, item, route, pending)

    if isinstance(store, InMemoryStateStore):
        last = 0
        try:
            while True:
                msgs = store.channels.get(channel, [])
                if last < len(msgs):
                    for item in msgs[last:]:
                        await _emit(item)
                    last = len(msgs)
                last_hb = await _ws_heartbeat(websocket, last_hb, hb_s)
                await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            return
        return

    import redis.asyncio as redis

    backoff = Backoff(base_s=0.2, max_s=4.0)
    while True:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(channel)
            backoff.reset()
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("data"):
                    await _emit(decode(msg["data"]))
                else:
                    last_hb = await _ws_heartbeat(websocket, last_hb, hb_s)
                    await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            return
        except Exception as exc:  # noqa: BLE001
            delay = backoff.next()
            log.warning("ws redis %s: %s; reconnect in %.2fs", channel, exc, delay)
            await asyncio.sleep(delay)
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:  # noqa: BLE001
                pass
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
    app.state.performance = PerformanceStore(app.state.store)
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
        version="3.0.0",
        description=API_DESCRIPTION,
        lifespan=None if store is not None else lifespan,
    )
    if store is not None:
        app.state.store = store
        app.state.settings = settings or get_settings()
        app.state.bars = bars if bars is not None else InMemoryOHLCVStore()
        app.state.performance = PerformanceStore(store)

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
            "phase": 3,
            "setups": list(SETUP_KEYS),
        }

    @app.get("/performance/summary")
    async def performance_summary(
        setup: str | None = Query(default=None),
    ) -> JSONResponse:
        filt = None
        if setup:
            try:
                filt = resolve_setup_key(setup)
            except UnknownSetupError as exc:
                raise HTTPException(400, str(exc)) from exc
        body = await app.state.performance.summary(setup=filt)
        return JSONResponse(body)

    @app.post("/performance/outcomes", status_code=201)
    async def performance_outcomes(body: dict[str, Any] | list[dict[str, Any]] = Body(...)) -> JSONResponse:
        store: PerformanceStore = app.state.performance
        items = body if isinstance(body, list) else [body]
        try:
            outcomes = [SignalOutcome.model_validate(item) for item in items]
            stored = await store.record_many(outcomes)
        except UnknownSetupError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc
        return JSONResponse(
            {"ok": True, "n": len(stored), "setups": [s.setup for s in stored]},
            status_code=201,
        )

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
        await _ws_session(
            websocket, "vwap", store, app.state.settings, f"vwap:{symbol}"
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
        await _ws_session(
            websocket, "session", store, app.state.settings, redis_session_channel(symbol)
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
        await _ws_session(
            websocket,
            "ohlcv",
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
            await _ws_session(
                websocket,
                "avwap",
                store,
                app.state.settings,
                redis_avwap_channel(symbol),
                match=lambda item, aid=anchor_id: isinstance(item, dict) and item.get("anchor_id") == aid,
            )
        else:
            await _ws_session(
                websocket, "avwap", store, app.state.settings, redis_avwap_channel(symbol)
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
        await _ws_session(
            websocket, "volume-profile", store, app.state.settings, redis_volume_profile_channel(symbol)
        )

    @app.websocket("/v1/ws/kill-zone")
    async def ws_kill_zone(websocket: WebSocket, symbol: str = Query(...)) -> None:
        symbol = normalize_symbol(symbol)
        await websocket.accept()
        store = app.state.store
        current = await store.get(redis_kill_zone_key(symbol))
        if current is not None:
            await websocket.send_json(current)
        await _ws_session(
            websocket, "kill-zone", store, app.state.settings, redis_kill_zone_channel(symbol)
        )

    @app.websocket("/v1/ws/sweep")
    async def ws_sweep(websocket: WebSocket, symbol: str = Query(...)) -> None:
        await _ws_zone_overlay(websocket, app, symbol, "sweep", sweep_channel)

    @app.websocket("/v1/ws/fvg")
    async def ws_fvg(websocket: WebSocket, symbol: str = Query(...)) -> None:
        await _ws_zone_overlay(websocket, app, symbol, "fvg", fvg_channel)

    @app.websocket("/v1/ws/mss")
    async def ws_mss(websocket: WebSocket, symbol: str = Query(...)) -> None:
        await _ws_zone_overlay(websocket, app, symbol, "mss", mss_channel)

    @app.websocket("/v1/ws/ob")
    async def ws_ob(websocket: WebSocket, symbol: str = Query(...)) -> None:
        await _ws_zone_overlay(websocket, app, symbol, "ob", ob_channel)

    return app


async def _ws_zone_overlay(
    websocket: WebSocket,
    app: FastAPI,
    symbol: str,
    prefix: str,
    channel_fn: Callable[[str], str],
) -> None:
    """Seed SCAN ``{prefix}:{symbol}:*`` then follow ``{prefix}:{symbol}``."""
    symbol = normalize_symbol(symbol)
    await websocket.accept()
    store = app.state.store
    keys = await store.scan(zone_scan_pattern(prefix, symbol))
    for key in sorted(keys):
        payload = await store.get(key)
        if payload is not None:
            await websocket.send_json(payload)
    await _ws_session(
        websocket, prefix, store, app.state.settings, channel_fn(symbol)
    )


def _metric_route(path: str) -> str:
    for prefix in (
        "/performance",
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


async def _ws_session(
    websocket: WebSocket,
    route: str,
    store: StateStore,
    settings: Settings,
    channel: str,
    match: Callable[[Any], bool] | None = None,
) -> None:
    record_ws_connect(route)
    try:
        await _ws_follow_channel(
            websocket, store, settings, channel, route=route, match=match
        )
    finally:
        record_ws_disconnect(route)


app = create_app()
