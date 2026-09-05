"""Risk Pre-Filter + signal query API (FastAPI). OpenAPI at /docs."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from sniper_quant.alerts import CHANNELS, AlertService
from sniper_quant.auth import ApiKeyRateLimitMiddleware
from sniper_quant.config import Settings, get_settings
from sniper_quant.paper import PaperEngine
from sniper_quant.lifecycle import LifecycleMonitor, resolve_close_patch
from sniper_quant.live import SignalHub
from sniper_quant.models import (
    AssetClass,
    CandidateSignal,
    OHLCVBar,
    PerformanceSummary,
    SetupType,
    SignalListResponse,
    Side,
    SignalStatus,
    FactorBreakdownRow,
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
# SniperTrader Quant API — Phase 3 / Rev. 1.1

Risk pre-filter (mandatory before every publish), `setup_signals` second
gate, lifecycle TP/SL, performance, alerts (stubs), paper book.
**No live trading.**

## Locked `setup_type` enum (six values)

`sweep_reclaim` · `fvg_entry` · `po3_judas` · `sd_extension_fade` ·
`vwap_pullback_cont` · `avwap_ob_confluence`

Dormant (`mss_break`, `order_block`, `sweep_mss`, `ob_fvg`) → HTTP **422**.
Do not walk-forward dormant types.

`POST /risk/validate` is required before Kafka `setup_signals` or
`POST /signals`. **Omit `id`.** `contributing_factors` and
`factor_breakdown` are **publish-only** — not on the validate body.

### Setup-specific risk

| setup_type | min RR | min conviction | extra |
|---|---|---|---|
| sweep_reclaim | 2.0 | 60 | |
| fvg_entry | 1.5 | 60 | |
| po3_judas | 1.5 | 60 | |
| sd_extension_fade | 1.5 | 60 | news skip ±15m (stub calendar) |
| vwap_pullback_cont | 2.0 | 60 | |
| avwap_ob_confluence | 2.0 | 70 | |

PM extras on S4–S6 (walk-forward / detectors only; live types
`sd_extension_fade` · `vwap_pullback_cont` · `avwap_ob_confluence`):
kill-zone conviction bonus (+30 when the confirm bar is in KZ);
S6 AVWAP anchors `swing_high` / `swing_low` plus earnings/news stubs;
orchestrator `dedupe_window_sec` default **300**.

`contributing_factors` is `string[]` on publish / signal store only —
**not** on `POST /risk/validate` (`CandidateSignal` `extra=forbid`).

Reject reasons: `ok`, `invalid_levels`, `position_size_exceeds_limit`,
`daily_loss_limit`, `correlation_threshold`, `same_symbol_conflict`,
`news_window`, `low_conviction`.

`adjusted_position_size` is **asset units**. `size_unit` is `"asset"`.

## Frontend

`GET /signals` and **`GET /signals/history`** share the same list
(filters: `symbol`, `status`, `setup_type`, `side`, `from_ts`, `to_ts`,
`limit`, `cursor`).

`GET /performance/summary` → top-level `win_rate`, `average_rr`,
`sharpe_ratio`, `max_drawdown_pct`, `signals_today`, `signals_week`.
`by_setup` is keyed by **`setup_type`**. Always includes `sweep_reclaim`,
`fvg_entry`, `po3_judas`, `mss_break`, `order_block`, `sweep_mss`
(zeros when empty). Each bucket has `product_key` (PM/DE lock):
`1_liquidity_sweep_vwap_reclaim`, `2_fvg_mitigation_vwap`,
`3_po3_asia_range_sweep`, `4_pending_user_confirm`,
`5_pending_user_confirm`, `6_pending_user_confirm`.
`ob_fvg` is omitted (not in the validate enum).

## Alerts / paper / auth

Alert stubs: Telegram, Discord, Email, webhook. Throttle **5/hour/user**.
Immediate when `confidence ≥ 0.80`.

Paper book: `GET /paper/account`, `POST /paper/reset`, `POST /paper/demo-fortnight`.
2-week gate, in-memory, no broker.

Auth: set `SNIPER_API_KEY` to require `X-API-Key`. Default **off** so
tests stay open. Optional `RATE_LIMIT_PER_MIN`.
"""


class StatusBody(BaseModel):
    status: SignalStatus
    closed_ts_ms: int | None = None
    exit_price: float | None = None
    realized_r: float | None = None
    # Storage aliases accepted on PATCH.
    exit_px: float | None = None
    r_multiple: float | None = None
    outcome: str | None = None


class PublishBody(CandidateSignal):
    """Validate candidate plus publish-only factor fields. Server assigns ``id``."""

    contributing_factors: list[str] = Field(
        default_factory=list,
        description="string[]. Publish / signal store only. Not on POST /risk/validate.",
    )
    factor_breakdown: list[FactorBreakdownRow] = Field(default_factory=list)


class AlertSubBody(BaseModel):
    user_id: str
    channel: str
    target: str


class AlertUnsubBody(BaseModel):
    user_id: str
    channel: str | None = None


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
        signals, app.state.hub, min_rr=settings.min_rr, engine=engine
    )
    app.state.monitor = LifecycleMonitor(signals, app.state.hub, ohlcv)
    app.state.alerts = AlertService()
    app.state.paper = PaperEngine(starting_equity=settings.default_equity)
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
            app.state.signals,
            app.state.hub,
            min_rr=app.state.settings.min_rr,
            engine=app.state.engine,
        )
        app.state.monitor = LifecycleMonitor(app.state.signals, app.state.hub, app.state.ohlcv)
        app.state.alerts = AlertService()
        app.state.paper = PaperEngine(starting_equity=app.state.settings.default_equity)

    app.add_middleware(ApiKeyRateLimitMiddleware, settings=settings or get_settings())

    def _engine() -> RiskEngine:
        return app.state.engine

    def _signals() -> SignalStore:
        return app.state.signals

    def _hub() -> SignalHub:
        return app.state.hub

    def _alerts() -> AlertService:
        return app.state.alerts

    def _paper() -> PaperEngine:
        return app.state.paper

    def _view(row: StoredSignal) -> SignalView:
        return SignalView.from_stored(row)

    def _after_upsert(row: StoredSignal) -> None:
        _paper().open_from_signal(row)
        _alerts().dispatch(_view(row), now_ms=row.ts_ms)

    def _after_status(row: StoredSignal) -> None:
        _paper().mark_signal(row)

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
        from sniper_quant.backtest.params import DEFAULT_PARAMS, KZ_CONVICTION_BONUS, S6_ANCHOR_TYPES
        from sniper_quant.setups import (
            DORMANT_SETUP_TYPES,
            PRODUCT_KEYS,
            SETUP_TYPE_TO_PRODUCT,
            WALKFORWARD_S4_S6,
        )

        return {
            "schema_version": "1.1",
            "setup_types": list(SETUP_TYPES),
            "product_keys": list(PRODUCT_KEYS),
            "setup_type_to_product": dict(SETUP_TYPE_TO_PRODUCT),
            "notes": SETUP_TYPE_NOTES,
            "locked": True,
            "walkforward_s4_s6": list(WALKFORWARD_S4_S6),
            "dormant_setup_types": list(DORMANT_SETUP_TYPES),
            "dedupe_window_sec": DEFAULT_PARAMS.dedupe_window_sec,
            "kz_conviction_bonus": KZ_CONVICTION_BONUS,
            "s6_anchors": list(S6_ANCHOR_TYPES),
            "contributing_factors": "publish_only",
        }

    @app.get("/performance/summary", response_model=PerformanceSummary)
    async def performance_summary() -> PerformanceSummary:
        """Live metrics. `by_setup` is keyed by `setup_type` (not product_key).

        Always includes `sweep_reclaim`, `fvg_entry`, `po3_judas`, `mss_break`,
        `order_block`, `sweep_mss` (zeros when empty). `product_key` is the
        PM/DE lock: `1_liquidity_sweep_vwap_reclaim`, `2_fvg_mitigation_vwap`,
        `3_po3_asia_range_sweep`, `4_pending_user_confirm`,
        `5_pending_user_confirm`, `6_pending_user_confirm`. Do not invent
        Setup 4–6 entry-rule names. `ob_fvg` is omitted.
        """
        from sniper_quant.performance import summarize_signals

        rows = await _signals().all()
        frac = float(_engine().settings.risk_fraction)
        return summarize_signals(rows, risk_fraction=frac)

    @app.post("/risk/validate", response_model=ValidateResponse)
    async def risk_validate(body: CandidateSignal) -> ValidateResponse:
        """Candidate setup (no id). Mandatory before publish for every setup_type."""
        engine = _engine()
        active = await _signals().active()
        engine.state.sync_from_signals(active)
        return engine.validate(body)

    async def _list_signals_impl(
        symbol: str | None,
        status: SignalStatus | None,
        setup_type: SetupType | None,
        side: Side | None,
        from_ts: int | None,
        to_ts: int | None,
        limit: int,
        cursor: str | None,
    ) -> SignalListResponse:
        if symbol:
            symbol = normalize_symbol(symbol)
        rows = await _signals().list(
            symbol=symbol,
            status=status,
            setup_type=setup_type,
            side=side,
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

    @app.get("/signals", response_model=SignalListResponse)
    async def list_signals(
        symbol: str | None = None,
        status: SignalStatus | None = None,
        setup_type: SetupType | None = None,
        side: Side | None = None,
        from_ts: int | None = Query(default=None, ge=0, description="Inclusive UTC epoch ms"),
        to_ts: int | None = Query(default=None, ge=0, description="Inclusive UTC epoch ms"),
        limit: int = Query(default=50, ge=1, le=500),
        cursor: str | None = Query(default=None, description="Opaque cursor from next_cursor"),
    ) -> SignalListResponse:
        """Live table + history window."""
        return await _list_signals_impl(
            symbol, status, setup_type, side, from_ts, to_ts, limit, cursor
        )

    @app.get("/signals/history", response_model=SignalListResponse)
    async def signals_history(
        symbol: str | None = None,
        status: SignalStatus | None = None,
        setup_type: SetupType | None = None,
        side: Side | None = None,
        from_ts: int | None = Query(default=None, ge=0),
        to_ts: int | None = Query(default=None, ge=0),
        limit: int = Query(default=50, ge=1, le=500),
        cursor: str | None = Query(default=None),
    ) -> SignalListResponse:
        """Same list as GET /signals — explicit history path for Frontend/PM."""
        return await _list_signals_impl(
            symbol, status, setup_type, side, from_ts, to_ts, limit, cursor
        )

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
            contributing_factors=list(body.contributing_factors or []),
            factor_breakdown=list(body.factor_breakdown or []),
        )
        await _signals().insert(stored)
        engine.state.sync_from_signals(await _signals().active())
        view = _view(stored)
        await _hub().publish("signal.upsert", view)
        _after_upsert(stored)
        return view

    @app.patch("/signals/{signal_id}", response_model=SignalView)
    async def patch_signal(signal_id: str, body: StatusBody) -> SignalView:
        current = await _signals().get(signal_id)
        if current is None:
            raise HTTPException(404, f"signal {signal_id} not found")
        exit_price = body.exit_price if body.exit_price is not None else body.exit_px
        realized_r = body.realized_r if body.realized_r is not None else body.r_multiple
        patch = resolve_close_patch(
            current,
            body.status,
            exit_price=exit_price,
            realized_r=realized_r,
            closed_ts_ms=body.closed_ts_ms,
            outcome=body.outcome,
        )
        row = await _signals().update_status(
            signal_id,
            body.status,
            closed_ts_ms=patch["closed_ts_ms"],
            exit_px=patch["exit_px"],
            r_multiple=patch["r_multiple"],
            outcome=patch["outcome"],
        )
        if row is None:
            raise HTTPException(404, f"signal {signal_id} not found")
        _engine().state.sync_from_signals(await _signals().active())
        view = _view(row)
        await _hub().publish("signal.status", view)
        _after_status(row)
        return view

    @app.post("/v1/signals/ingest", response_model=SignalView)
    async def ingest_setup_signal(body: dict[str, Any]) -> SignalView:
        """Second gate: re-runs risk pre-filter; rejects unapproved publishes."""
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
        _after_upsert(stored)
        return _view(stored)

    @app.post("/v1/lifecycle/bar")
    async def lifecycle_bar(body: OHLCVBar) -> dict[str, Any]:
        """Apply one OHLCV bar to ACTIVE signals (TP/SL + outcome)."""
        monitor: LifecycleMonitor = app.state.monitor
        closed = await monitor.apply_bar(body)
        _engine().state.sync_from_signals(await _signals().active())
        for row in closed:
            _after_status(row)
        return {
            "closed": len(closed),
            "signals": [_view(row).model_dump() for row in closed],
        }

    @app.post("/alerts/subscribe")
    async def alerts_subscribe(body: AlertSubBody) -> dict[str, Any]:
        try:
            _alerts().subscribe(body.user_id, body.channel, body.target)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"ok": True, "channels": list(CHANNELS), **_alerts().dump()}

    @app.post("/alerts/unsubscribe")
    async def alerts_unsubscribe(body: AlertUnsubBody) -> dict[str, Any]:
        removed = _alerts().unsubscribe(body.user_id, body.channel)
        return {"ok": True, "removed": removed}

    @app.get("/alerts")
    async def alerts_status() -> dict[str, Any]:
        return _alerts().dump()

    @app.get("/paper/account")
    async def paper_account() -> dict[str, Any]:
        return _paper().snapshot()

    @app.get("/paper/positions")
    async def paper_positions() -> dict[str, Any]:
        snap = _paper().snapshot()
        return {"positions": snap["positions"], "closed": snap["closed"]}

    @app.post("/paper/reset")
    async def paper_reset() -> dict[str, Any]:
        _paper().reset(_engine().state.equity)
        return _paper().snapshot()

    @app.post("/paper/demo-fortnight")
    async def paper_demo_fortnight() -> dict[str, Any]:
        """Scripted 14-day paper book (no live broker). For the FE/PM 2-week gate."""
        from sniper_quant.backtest.demo import run_inmemory_demo

        book = _paper()
        book.reset(_engine().state.equity)
        result = run_inmemory_demo(book.starting_equity)
        day_ms = 86_400_000
        start = 1_700_000_000_000
        for i, trade in enumerate(result.trades):
            setup = trade.setup_type
            row = StoredSignal(
                id=trade.signal_id or f"paper-{i}",
                symbol=trade.symbol,
                asset_class=AssetClass.CRYPTO,
                setup_type=setup,
                side=trade.side,
                ts_ms=start + (i % 14) * day_ms,
                entry=trade.entry,
                stop=trade.stop,
                target=trade.target,
                position_size=trade.size,
                status=SignalStatus.ACTIVE,
            )
            book.open_from_signal(row)
            closed = row.model_copy(
                update={
                    "status": trade.status,
                    "exit_px": trade.exit_price,
                    "r_multiple": trade.r_multiple,
                    "closed_ts_ms": trade.exit_ts_ms or row.ts_ms + 3_600_000,
                }
            )
            book.close_from_signal(closed)
        snap = book.snapshot()
        snap["days_simulated"] = 14
        snap["demo_trades"] = result.metrics.n_trades
        snap["how_to_run"] = (
            "USE_INMEMORY=1 python -m sniper_quant.cli api --inmemory --port 8001 "
            "then POST /paper/demo-fortnight or POST /risk/validate → POST /signals "
            "→ POST /v1/lifecycle/bar. No live trading."
        )
        return snap

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
                    "Emitted on POST /signals (upsert) and PATCH /signals/{id} / lifecycle close (status). "
                    "Closed frames include realized_r, exit_price, closed_ts_ms."
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
