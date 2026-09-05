"""Risk Pre-Filter + signal query API (FastAPI). OpenAPI at /docs."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from sniper_quant.config import Settings, get_settings
from sniper_quant.models import (
    CandidateSignal,
    SignalStatus,
    StoredSignal,
    ValidateResponse,
    normalize_symbol,
)
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import SETUP_TYPE_NOTES, SETUP_TYPES
from sniper_quant.store.ohlcv import InMemoryOHLCVLoader, OHLCVLoader, TimescaleOHLCVLoader
from sniper_quant.store.signals import InMemorySignalStore, SignalStore, TimescaleSignalStore

API_DESCRIPTION = """
# SniperTrader Quant API — Phase 1 / Rev. 1.1

Risk management and signal lifecycle. Lives beside `data_engineering/`.
Shares TimescaleDB (`ohlcv_bars`, `signals`) when `USE_INMEMORY` is false.

## ML Researchers — Risk Pre-Filter (required before `setup_signals`)

`POST /risk/validate`

Send a **candidate** setup signal (`schemas/risk_validate_request.schema.json`).
`id` is **optional**. Do **not** publish to Kafka topic `setup_signals` unless
`approved` is `true`. After approval, assign `id` and include the returned
`adjusted_position_size`, `stop`, and `target`.

Required response keys: `approved`, `reason`, `adjusted_position_size`.

Reject reasons:

- `missing_entry` — need `entry` or `ref_vwap`
- `invalid_levels` — stop/target on the wrong side of entry
- `position_size_exceeds_limit` — requested size > 2% equity risk
- `daily_loss_limit` — 3% daily loss already hit or this trade would breach
- `correlation_threshold` — 60-day |ρ| vs an open symbol > 0.70
- `same_symbol_conflict` — an ACTIVE position already exists on the symbol
- `ok` — approved

## Frontend — signal query

`GET /signals?symbol=&status=&from_ms=&to_ms=`

Status: `ACTIVE` → `TP_HIT` | `SL_HIT` | `CANCELLED`.
"""


class StatusBody(BaseModel):
    status: SignalStatus
    closed_ts_ms: int | None = None


class PublishBody(CandidateSignal):
    id: str | None = None


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
        version="1.1.0",
        description=API_DESCRIPTION,
        lifespan=None if injected else lifespan,
    )
    if injected:
        app.state.settings = settings or get_settings()
        app.state.signals = signals
        app.state.ohlcv = ohlcv or InMemoryOHLCVLoader()
        app.state.engine = engine or RiskEngine(settings=app.state.settings)

    def _engine() -> RiskEngine:
        return app.state.engine

    def _signals() -> SignalStore:
        return app.state.signals

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
            "pluggable": True,
        }

    @app.post("/risk/validate", response_model=ValidateResponse)
    async def risk_validate(body: CandidateSignal) -> ValidateResponse:
        """ML must call this before publishing a high-conviction signal."""
        engine = _engine()
        active = await _signals().active()
        engine.state.sync_from_signals(active)
        return engine.validate(body)

    @app.get("/signals")
    async def list_signals(
        symbol: str | None = None,
        status: SignalStatus | None = None,
        from_ms: int | None = Query(default=None, ge=0),
        to_ms: int | None = Query(default=None, ge=0),
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> dict[str, Any]:
        if symbol:
            symbol = normalize_symbol(symbol)
        rows = await _signals().list(
            symbol=symbol, status=status, from_ms=from_ms, to_ms=to_ms, limit=limit
        )
        return {"signals": [r.model_dump() for r in rows], "count": len(rows)}

    @app.get("/signals/{signal_id}")
    async def get_signal(signal_id: str) -> dict[str, Any]:
        row = await _signals().get(signal_id)
        if row is None:
            raise HTTPException(404, f"signal {signal_id} not found")
        return row.model_dump()

    @app.post("/signals", status_code=201)
    async def publish_signal(body: PublishBody) -> dict[str, Any]:
        """Persist an approved signal (ACTIVE). Frontend / ML helper — not Kafka."""
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
        signal_id = body.id or str(uuid.uuid4())
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
            position_size=decision.adjusted_position_size,
            status=SignalStatus.ACTIVE,
        )
        await _signals().insert(stored)
        engine.state.sync_from_signals(await _signals().active())
        return stored.model_dump()

    @app.patch("/signals/{signal_id}")
    async def patch_signal(signal_id: str, body: StatusBody) -> dict[str, Any]:
        row = await _signals().update_status(
            signal_id, body.status, closed_ts_ms=body.closed_ts_ms
        )
        if row is None:
            raise HTTPException(404, f"signal {signal_id} not found")
        _engine().state.sync_from_signals(await _signals().active())
        return row.model_dump()

    @app.post("/backtest/demo")
    async def backtest_demo() -> dict[str, Any]:
        from sniper_quant.backtest.demo import run_inmemory_demo

        result = run_inmemory_demo(_engine().state.equity)
        return {
            "metrics": result.metrics.model_dump(),
            "n_trades": result.metrics.n_trades,
            "inmemory": True,
        }

    return app


app = create_app()
