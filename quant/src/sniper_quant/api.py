"""Risk Pre-Filter + signal query API (FastAPI). OpenAPI at /docs."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from sniper_quant.config import Settings, get_settings
from sniper_quant.lifecycle import LifecycleMonitor
from sniper_quant.live import SignalHub
from sniper_quant.models import (
    CandidateSignal,
    OHLCVBar,
    SetupType,
    SignalListResponse,
    SignalStatus,
    SignalView,
    StoredSignal,
    ValidateResponse,
    normalize_symbol,
)
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import SETUP_TYPE_NOTES, SETUP_TYPES
from sniper_quant.store.ohlcv import InMemoryOHLCVLoader, OHLCVLoader, TimescaleOHLCVLoader
from sniper_quant.store.signals import (
    InMemorySignalStore,
    SignalStore,
    TimescaleSignalStore,
    encode_cursor,
)

API_DESCRIPTION = """
# SniperTrader Quant API — Phase 2 / Rev. 1.1

Risk pre-filter, `setup_signals` second gate, lifecycle TP/SL, and
Setups 1–3 backtests. Lives beside `data_engineering/`.
Shares TimescaleDB (`ohlcv_bars`, `signals`) when `USE_INMEMORY` is false.

## ML Researchers — Risk Pre-Filter (required before Phase 2 `setup_signals`)

`POST /risk/validate`

Send a **candidate** (`schemas/risk_validate_request.schema.json`).
**Omit `id`.** Do **not** publish to Kafka `setup_signals` unless `approved`
is `true`. After approval, assign `id` and persist `adjusted_position_size`.

### Locked `setup_type` enum

`sweep_reclaim` · `fvg_entry` · `mss_break` · `order_block` · `sweep_mss` · `ob_fvg` · `po3_judas`

### Required stub fields

`schema_version` (`"1.1"`), `symbol`, `asset_class`, `setup_type`, `side`,
`ts_ms`. Optional stubs: `confidence`, `ref_vwap`, `ref_session`.

### Required for risk

`entry`, `stop`, `target` (numbers), `timeframe` ∈ {`1m`,`5m`,`15m`},
`trigger_event_ids` (string[]).

### Optional

`session_type` — same enum as Data Engineers
(`asia`/`london`/`ny_am`/`ny_pm`/`rth`/`eth`/`globex`).

`proposed_position_size` — engine may overwrite via `adjusted_position_size`.

Required response keys: `approved`, `reason`, `adjusted_position_size`.

Reject reasons:

- `invalid_levels` — stop/target on the wrong side of entry, or R:R below 1.5
- `position_size_exceeds_limit` — proposed size > 2% equity risk
- `daily_loss_limit` — 3% daily loss already hit or this trade would breach
- `correlation_threshold` — 60-day |ρ| vs an open symbol > 0.70
- `same_symbol_conflict` — an ACTIVE position on the same symbol in the **opposite** direction (same-direction pyramid is allowed)
- `ok` — approved

`adjusted_position_size` is in **asset units** (coins / shares / contracts), not USD.
`size_unit` is always `"asset"`.

Phase 2 second gate: Kafka `setup_signals` (or `POST /v1/signals/ingest`)
re-checks geometry + 1.5R and persists ACTIVE. `POST /v1/lifecycle/bar`
moves ACTIVE → TP_HIT / SL_HIT and records `outcome` + `r_multiple`.

Unknown `setup_type` or `timeframe` → HTTP 422.

## Frontend — dashboard signal table

`GET /signals?symbol=&status=&setup_type=&from_ts=&to_ts=&limit=&cursor=`

Returns `{ "items": Signal[], "next_cursor": string | null }`.
`from_ts` / `to_ts` are UTC epoch milliseconds (same unit as `ts_ms`).
Pass `cursor` from the previous page's `next_cursor`.

`GET /signals/{id}` → `Signal`

`Signal` fields: `id`, `ts_ms`, `symbol`, `asset_class`, `setup_type`
(seven locked values), `side`, `entry`, `stop`, `target`,
`status` (`ACTIVE`|`TP_HIT`|`SL_HIT`|`CANCELLED`), `confidence`,
`timeframe`, `ref_session`, `trigger_event_ids`.

`WS /ws/signals` pushes `{ "type": "signal.upsert"|"signal.status", "signal": Signal }`
on create (`upsert`) and status change (`status`).
"""


class StatusBody(BaseModel):
    status: SignalStatus
    closed_ts_ms: int | None = None
    exit_px: float | None = None
    r_multiple: float | None = None
    outcome: str | None = None


class PublishBody(CandidateSignal):
    """Same locked candidate as validate. Server assigns ``id`` after approval."""


def _build_stores(settings: Settings) -> tuple[SignalStore, OHLCVLoader, RiskEngine]:
    if settings.use_inmemory:
        signals: SignalStore = InMemorySignalStore()
        ohlcv: OHLCVLoader = InMemoryOHLCVLoader()
    else:
        signals = TimescaleSignalStore(settings.database_url)
        ohlcv = TimescaleOHLCVLoader(settings.database_url)
    engine = RiskEngine(settings=settings, state=RiskState(equity=settings.default_equity))
    return signals, ohlcv, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    signals, ohlcv, engine = _build_stores(settings)
    app.state.settings = settings
    app.state.signals = signals
    app.state.ohlcv = ohlcv
    app.state.engine = engine
    app.state.hub = SignalHub()
    from sniper_quant.validate_service import SignalValidationService

    app.state.validator = SignalValidationService(
        signals, app.state.hub, min_rr=settings.min_rr
    )
    app.state.monitor = LifecycleMonitor(signals, app.state.hub, ohlcv)
    yield
    await signals.close()
    await ohlcv.close()


def create_app(
    *,
    settings: Settings | None = None,
    signals: SignalStore | None = None,
    ohlcv: OHLCVLoader | None = None,
    engine: RiskEngine | None = None,
) -> FastAPI:
    injected = signals is not None
    app = FastAPI(
        title="SniperTrader Quant API",
        version="1.2.0",
        description=API_DESCRIPTION,
        lifespan=None if injected else lifespan,
    )
    if injected:
        app.state.settings = settings or get_settings()
        app.state.signals = signals
        app.state.ohlcv = ohlcv or InMemoryOHLCVLoader()
        app.state.engine = engine or RiskEngine(settings=app.state.settings)
        app.state.hub = SignalHub()
        from sniper_quant.validate_service import SignalValidationService

        app.state.validator = SignalValidationService(
            app.state.signals, app.state.hub, min_rr=app.state.settings.min_rr
        )
        app.state.monitor = LifecycleMonitor(app.state.signals, app.state.hub, app.state.ohlcv)

    def _engine() -> RiskEngine:
        return app.state.engine

    def _signals() -> SignalStore:
        return app.state.signals

    def _hub() -> SignalHub:
        return app.state.hub

    def _view(row: StoredSignal) -> SignalView:
        return SignalView.from_stored(row)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "inmemory": isinstance(app.state.signals, InMemorySignalStore),
            "schema_version": "1.1",
        }

    @app.get("/risk/params")
    async def risk_params() -> dict[str, Any]:
        body = _engine().params().model_dump()
        body["setup_type_notes"] = SETUP_TYPE_NOTES
        return body

    @app.get("/v1/setups")
    async def list_setups() -> dict[str, Any]:
        return {
            "schema_version": "1.1",
            "setup_types": list(SETUP_TYPES),
            "notes": SETUP_TYPE_NOTES,
            "locked": True,
        }

    @app.post("/risk/validate", response_model=ValidateResponse)
    async def risk_validate(body: CandidateSignal) -> ValidateResponse:
        """Candidate setup (no id). Call before Phase 2 publish to setup_signals."""
        engine = _engine()
        active = await _signals().active()
        engine.state.sync_from_signals(active)
        return engine.validate(body)

    @app.get("/signals", response_model=SignalListResponse)
    async def list_signals(
        symbol: str | None = None,
        status: SignalStatus | None = None,
        setup_type: SetupType | None = None,
        from_ts: int | None = Query(default=None, ge=0, description="Inclusive UTC epoch ms"),
        to_ts: int | None = Query(default=None, ge=0, description="Inclusive UTC epoch ms"),
        limit: int = Query(default=50, ge=1, le=500),
        cursor: str | None = Query(default=None, description="Opaque cursor from next_cursor"),
    ) -> SignalListResponse:
        """Dashboard table: filter + cursor page of Signal rows."""
        if symbol:
            symbol = normalize_symbol(symbol)
        rows = await _signals().list(
            symbol=symbol,
            status=status,
            setup_type=setup_type,
            from_ts=from_ts,
            to_ts=to_ts,
            cursor=cursor,
            limit=limit + 1,
        )
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last.ts_ms, last.id)
            rows = rows[:limit]
        return SignalListResponse(items=[_view(r) for r in rows], next_cursor=next_cursor)

    @app.get("/signals/{signal_id}", response_model=SignalView)
    async def get_signal(signal_id: str) -> SignalView:
        row = await _signals().get(signal_id)
        if row is None:
            raise HTTPException(404, f"signal {signal_id} not found")
        return _view(row)

    @app.post("/signals", status_code=201, response_model=SignalView)
    async def publish_signal(body: PublishBody) -> SignalView:
        """Persist an approved signal (ACTIVE). Emits ``signal.upsert`` on the WS."""
        engine = _engine()
        active = await _signals().active()
        engine.state.sync_from_signals(active)
        decision = engine.validate(body)
        if not decision.approved:
            raise HTTPException(
                409,
                {
                    "detail": "risk_rejected",
                    "validate": decision.model_dump(),
                },
            )
        signal_id = str(uuid.uuid4())
        stored = StoredSignal(
            id=signal_id,
            symbol=body.symbol,
            asset_class=body.asset_class,
            setup_type=body.setup_type,
            side=body.side,
            confidence=body.confidence,
            ref_vwap=body.ref_vwap,
            ref_session=body.ref_session,
            ts_ms=body.ts_ms,
            entry=decision.entry,
            stop=decision.stop,
            target=decision.target,
            timeframe=body.timeframe,
            trigger_event_ids=list(body.trigger_event_ids),
            session_type=body.session_type,
            position_size=decision.adjusted_position_size,
            status=SignalStatus.ACTIVE,
        )
        await _signals().insert(stored)
        engine.state.sync_from_signals(await _signals().active())
        view = _view(stored)
        await _hub().publish("signal.upsert", view)
        return view

    @app.patch("/signals/{signal_id}", response_model=SignalView)
    async def patch_signal(signal_id: str, body: StatusBody) -> SignalView:
        row = await _signals().update_status(
            signal_id,
            body.status,
            closed_ts_ms=body.closed_ts_ms,
            exit_px=body.exit_px,
            r_multiple=body.r_multiple,
            outcome=body.outcome,
        )
        if row is None:
            raise HTTPException(404, f"signal {signal_id} not found")
        _engine().state.sync_from_signals(await _signals().active())
        view = _view(row)
        await _hub().publish("signal.status", view)
        return view

    @app.post("/v1/signals/ingest", response_model=SignalView)
    async def ingest_setup_signal(body: dict[str, Any]) -> SignalView:
        """Second gate (same as the Kafka ``setup_signals`` consumer). Sanity only."""
        from sniper_quant.validate_service import SignalValidationService

        validator: SignalValidationService = app.state.validator
        stored = await validator.handle(body)
        if stored is None:
            raise HTTPException(
                422,
                {
                    "detail": "sanity_rejected",
                    "reason": "invalid_levels_or_parse",
                },
            )
        _engine().state.sync_from_signals(await _signals().active())
        return _view(stored)

    @app.post("/v1/lifecycle/bar")
    async def lifecycle_bar(body: OHLCVBar) -> dict[str, Any]:
        """Apply one OHLCV bar to ACTIVE signals (TP/SL + outcome)."""
        monitor: LifecycleMonitor = app.state.monitor
        closed = await monitor.apply_bar(body)
        _engine().state.sync_from_signals(await _signals().active())
        return {
            "closed": len(closed),
            "signals": [_view(row).model_dump() for row in closed],
        }

    @app.websocket("/ws/signals")
    async def ws_signals(websocket: WebSocket) -> None:
        """Live dashboard feed: signal.upsert on create, signal.status on patch."""
        await websocket.accept()
        _hub().subscribe(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            _hub().unsubscribe(websocket)

    @app.post("/backtest/demo")
    async def backtest_demo() -> dict[str, Any]:
        from sniper_quant.backtest.demo import run_inmemory_demo

        result = run_inmemory_demo(_engine().state.equity)
        return {
            "metrics": result.metrics.model_dump(),
            "n_trades": result.metrics.n_trades,
            "inmemory": True,
        }

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("paths", {})["/ws/signals"] = {
            "get": {
                "tags": ["signals"],
                "summary": "WS /ws/signals — live Signal feed",
                "description": (
                    "WebSocket upgrade. Each frame is "
                    '`{ "type": "signal.upsert" | "signal.status", "signal": Signal }`. '
                    "Emitted on POST /signals (upsert) and PATCH /signals/{id} (status)."
                ),
                "operationId": "ws_signals",
                "responses": {
                    "101": {
                        "description": "Switching Protocols — SignalWsEvent frames",
                    }
                },
            }
        }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()
