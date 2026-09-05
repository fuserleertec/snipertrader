"""Second-gate consumer for Kafka ``setup_signals``.

Risk Pre-Filter is **mandatory** for every locked ``setup_type`` before a
row is persisted. ML must call ``POST /risk/validate`` first and publish
only when ``approved`` is true. This consumer **re-runs** the same
pre-filter so a publish that skipped validate is discarded.

Failed checks are logged and never stored as ACTIVE.
Tests use :class:`sniper_quant.bus.InMemoryBus` (no Kafka).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sniper_quant.bus import SETUP_SIGNALS_TOPIC, InMemoryBus, consume_topic
from sniper_quant.config import Settings, get_settings
from sniper_quant.live import SignalHub
from sniper_quant.models import (
    AssetClass,
    CandidateSignal,
    SessionType,
    SetupType,
    Side,
    SignalStatus,
    SignalTimeframe,
    SignalView,
    StoredSignal,
    normalize_symbol,
)
from sniper_quant.risk.engine import RiskEngine
from sniper_quant.store.signals import SignalStore
from sniper_quant.usme import check_provided_levels

log = logging.getLogger(__name__)


def _enum_or_none(cls, value):
    if value is None or value == "":
        return None
    return cls(value)


class SignalValidationService:
    """Re-run risk pre-filter, then persist on pass."""

    def __init__(
        self,
        store: SignalStore,
        hub: SignalHub | None = None,
        *,
        min_rr: float = 1.5,
        engine: RiskEngine | None = None,
    ) -> None:
        self.store = store
        self.hub = hub or SignalHub()
        self.min_rr = min_rr
        self.engine = engine
        self.accepted = 0
        self.rejected = 0

    async def handle(self, payload: dict[str, Any]) -> StoredSignal | None:
        try:
            stored = self._to_stored(payload)
            candidate = self._to_candidate(payload, stored)
        except (KeyError, TypeError, ValueError) as exc:
            self.rejected += 1
            log.warning("setup_signals discarded (parse): %s payload=%s", exc, payload)
            return None
        if stored.entry is None or stored.stop is None or stored.target is None:
            self.rejected += 1
            log.warning("setup_signals discarded (missing levels) id=%s", stored.id)
            return None
        if self.engine is not None:
            active = await self.store.active()
            self.engine.state.sync_from_signals(active)
            decision = self.engine.validate(candidate)
            if not decision.approved:
                self.rejected += 1
                log.warning(
                    "setup_signals discarded (risk %s) id=%s symbol=%s",
                    decision.reason,
                    stored.id,
                    stored.symbol,
                )
                return None
            if decision.adjusted_position_size is not None:
                stored.position_size = decision.adjusted_position_size
        else:
            try:
                check_provided_levels(
                    side=stored.side,
                    entry=stored.entry,
                    stop=stored.stop,
                    target=stored.target,
                    min_rr=self.min_rr,
                )
            except ValueError as exc:
                self.rejected += 1
                log.warning(
                    "setup_signals discarded (sanity) id=%s symbol=%s: %s",
                    stored.id,
                    stored.symbol,
                    exc,
                )
                return None
        stored.status = SignalStatus.ACTIVE
        await self.store.insert(stored)
        self.accepted += 1
        await self.hub.publish("signal.upsert", SignalView.from_stored(stored))
        log.info("setup_signals accepted id=%s %s %s", stored.id, stored.symbol, stored.setup_type)
        return stored

    def _to_candidate(self, payload: dict[str, Any], stored: StoredSignal) -> CandidateSignal:
        size = payload.get("proposed_position_size")
        if size is None:
            size = payload.get("position_size")
        return CandidateSignal(
            schema_version=payload.get("schema_version") or "1.1",
            symbol=stored.symbol,
            asset_class=stored.asset_class,
            setup_type=stored.setup_type
            if isinstance(stored.setup_type, SetupType)
            else SetupType(str(stored.setup_type)),
            side=stored.side,
            confidence=stored.confidence,
            ref_vwap=stored.ref_vwap,
            ref_session=stored.ref_session,
            ts_ms=stored.ts_ms,
            entry=stored.entry,
            stop=stored.stop,
            target=stored.target,
            timeframe=stored.timeframe
            if isinstance(stored.timeframe, SignalTimeframe)
            else SignalTimeframe(str(stored.timeframe or "5m")),
            trigger_event_ids=list(stored.trigger_event_ids or []),
            session_type=stored.session_type
            if stored.session_type is None or isinstance(stored.session_type, SessionType)
            else None,
            proposed_position_size=size,
        )

    def _to_stored(self, payload: dict[str, Any]) -> StoredSignal:
        setup = payload.get("setup_type")
        if setup is None:
            raise ValueError("setup_type is required")
        if setup not in SetupType._value2member_map_:
            raise ValueError(f"unknown setup_type {setup!r}")
        signal_id = payload.get("id") or payload.get("signal_id") or str(uuid.uuid4())
        tf = payload.get("timeframe")
        session = payload.get("session_type")
        return StoredSignal(
            schema_version=payload.get("schema_version") or "1.1",
            id=str(signal_id),
            symbol=normalize_symbol(payload["symbol"]),
            asset_class=AssetClass(payload.get("asset_class") or "crypto"),
            setup_type=SetupType(setup),
            side=Side(payload["side"]),
            confidence=payload.get("confidence"),
            ref_vwap=payload.get("ref_vwap"),
            ref_session=payload.get("ref_session"),
            ts_ms=int(payload["ts_ms"]),
            entry=payload.get("entry"),
            stop=payload.get("stop") if payload.get("stop") is not None else payload.get("stop_px"),
            target=payload.get("target"),
            timeframe=_enum_or_none(SignalTimeframe, tf) or tf,
            trigger_event_ids=list(payload.get("trigger_event_ids") or []),
            session_type=_enum_or_none(SessionType, session) or session,
            position_size=payload.get("position_size"),
            status=SignalStatus.ACTIVE,
            contributing_factors=list(payload.get("contributing_factors") or []),
            factor_breakdown=list(payload.get("factor_breakdown") or []),
        )


async def run_inmemory_consumer(
    bus: InMemoryBus,
    service: SignalValidationService,
    *,
    topic: str = SETUP_SIGNALS_TOPIC,
) -> None:
    """Attach the service to an in-memory bus (tests / no Kafka)."""

    async def _on(payload: dict) -> None:
        await service.handle(payload)

    bus.subscribe(topic, _on)
    await bus.start()


async def run_kafka_consumer(service: SignalValidationService, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    log.info(
        "consuming %s at %s group=%s",
        SETUP_SIGNALS_TOPIC,
        settings.kafka_bootstrap,
        settings.kafka_group,
    )
    async for payload in consume_topic(
        settings.kafka_bootstrap,
        SETUP_SIGNALS_TOPIC,
        settings.kafka_group,
    ):
        await service.handle(payload)
