"""Second-gate consumer for Kafka ``setup_signals``.

ML must call ``POST /risk/validate`` before publishing. This service only
re-checks geometry / min R:R, then persists ACTIVE rows and fans out WS.

Failed sanity checks are logged and discarded — they are never stored as
ACTIVE. Tests use :class:`sniper_quant.bus.InMemoryBus` (no Kafka).
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
    SessionType,
    SetupType,
    Side,
    SignalStatus,
    SignalTimeframe,
    SignalView,
    StoredSignal,
    normalize_symbol,
)
from sniper_quant.store.signals import SignalStore
from sniper_quant.usme import check_provided_levels

log = logging.getLogger(__name__)


def _enum_or_none(cls, value):
    if value is None or value == "":
        return None
    return cls(value)


class SignalValidationService:
    """Sanity-check a setup_signals payload and persist on pass."""

    def __init__(
        self,
        store: SignalStore,
        hub: SignalHub | None = None,
        *,
        min_rr: float = 1.5,
    ) -> None:
        self.store = store
        self.hub = hub or SignalHub()
        self.min_rr = min_rr
        self.accepted = 0
        self.rejected = 0

    async def handle(self, payload: dict[str, Any]) -> StoredSignal | None:
        try:
            stored = self._to_stored(payload)
        except (KeyError, TypeError, ValueError) as exc:
            self.rejected += 1
            log.warning("setup_signals discarded (parse): %s payload=%s", exc, payload)
            return None
        if stored.entry is None or stored.stop is None or stored.target is None:
            self.rejected += 1
            log.warning("setup_signals discarded (missing levels) id=%s", stored.id)
            return None
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

    def _to_stored(self, payload: dict[str, Any]) -> StoredSignal:
        setup = payload.get("setup_type")
        if setup is None:
            raise ValueError("setup_type is required")
        signal_id = payload.get("id") or payload.get("signal_id") or str(uuid.uuid4())
        tf = payload.get("timeframe")
        session = payload.get("session_type")
        return StoredSignal(
            schema_version=payload.get("schema_version") or "1.1",
            id=str(signal_id),
            symbol=normalize_symbol(payload["symbol"]),
            asset_class=AssetClass(payload.get("asset_class") or "crypto"),
            setup_type=SetupType(setup) if setup in SetupType._value2member_map_ else setup,
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
