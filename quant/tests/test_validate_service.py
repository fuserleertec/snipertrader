from __future__ import annotations

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.bus import SETUP_SIGNALS_TOPIC, InMemoryBus
from sniper_quant.live import SignalHub
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.store.signals import InMemorySignalStore
from sniper_quant.validate_service import SignalValidationService, run_inmemory_consumer
from tests.conftest import make_settings
from tests.test_validate import _payload


def _msg(**kwargs) -> dict:
    body = _payload()
    body["id"] = "sig-ml-1"
    body["position_size"] = 1.25
    body["status"] = "ACTIVE"
    body.update(kwargs)
    return body


async def test_inmemory_bus_accepts_sane_signal():
    store = InMemorySignalStore()
    hub = SignalHub()
    service = SignalValidationService(store, hub, min_rr=1.5)
    bus = InMemoryBus()
    await run_inmemory_consumer(bus, service)
    accepted = await service.handle(_msg())
    assert accepted is not None
    assert accepted.id == "sig-ml-1"
    assert accepted.status.value == "ACTIVE"
    row = await store.get("sig-ml-1")
    assert row is not None
    assert service.accepted == 1


async def test_bus_publish_invokes_consumer():
    store = InMemorySignalStore()
    service = SignalValidationService(store, SignalHub(), min_rr=1.5)
    bus = InMemoryBus()
    await run_inmemory_consumer(bus, service)
    await bus.publish(SETUP_SIGNALS_TOPIC, _msg(id="via-bus"))
    assert await store.get("via-bus") is not None


async def test_assigns_id_when_missing():
    store = InMemorySignalStore()
    service = SignalValidationService(store, SignalHub())
    body = _msg()
    del body["id"]
    stored = await service.handle(body)
    assert stored is not None
    assert stored.id


async def test_discard_bad_geometry():
    store = InMemorySignalStore()
    service = SignalValidationService(store, SignalHub())
    assert await service.handle(_msg(id="bad-long", stop=104.0, target=108.0)) is None
    assert await service.handle(_msg(id="low-r", stop=96.0, target=101.0)) is None
    assert await store.get("bad-long") is None
    assert service.rejected == 2
    assert service.accepted == 0


async def test_short_geometry_ok_and_inverted_fail():
    store = InMemorySignalStore()
    service = SignalValidationService(store, SignalHub())
    ok = await service.handle(_msg(id="short-ok", side="short", stop=104.0, target=92.0))
    assert ok is not None
    bad = await service.handle(_msg(id="short-bad", side="short", stop=96.0, target=92.0))
    assert bad is None


def test_http_ingest_and_reject():
    settings = make_settings()
    engine = RiskEngine(settings=settings, state=RiskState(equity=100_000))
    app = create_app(settings=settings, signals=InMemorySignalStore(), engine=engine)
    http = TestClient(app)
    ok = http.post("/v1/signals/ingest", json=_msg(id="http-1"))
    assert ok.status_code == 200
    assert ok.json()["id"] == "http-1"
    assert ok.json()["status"] == "ACTIVE"
    bad = http.post("/v1/signals/ingest", json=_msg(id="http-bad", target=101.0))
    assert bad.status_code == 422


async def test_gate_path_validate_then_bus_publish():
    """Second-gate consumer (InMemoryBus) persists only after a sane publish."""
    store = InMemorySignalStore()
    service = SignalValidationService(store, SignalHub(), min_rr=1.5)
    bus = InMemoryBus()
    await run_inmemory_consumer(bus, service)
    await bus.publish(SETUP_SIGNALS_TOPIC, _msg(id="gate-ok"))
    assert await store.get("gate-ok") is not None
    await bus.publish(
        SETUP_SIGNALS_TOPIC,
        _msg(id="gate-bad", stop=96.0, target=101.0),
    )
    assert await store.get("gate-bad") is None
    assert service.accepted == 1
    assert service.rejected == 1
