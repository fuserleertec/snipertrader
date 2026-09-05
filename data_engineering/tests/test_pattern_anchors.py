"""ML Phase 2: swing/MSS → locked DE anchor contract + Redis consumers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sniper_data.api import create_app
from sniper_data.avwap import redis_avwap_key, to_wire
from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.kill_zones import redis_kill_zone_key
from sniper_data.models import (
    AVWAPBands,
    AnchorRegistration,
    AnchorSource,
    AnchoredVWAP,
    AssetClass,
    KillZoneEvent,
    SessionType,
    VolumeNode,
    VolumeProfile,
)
from sniper_data.pattern_detection.anchors import (
    ANCHOR_FIELDS,
    ANCHOR_REQUIRED,
    ANCHOR_SOURCES,
    ANCHOR_TOPIC,
    post_anchor,
    publish_anchor,
    swing_to_registration,
    to_anchor_payload,
)
from sniper_data.pattern_detection.context import (
    get_avwap,
    get_kill_zone,
    get_volume_profile,
    subscribe_kill_zone_events,
)
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.pattern_detection.fixtures import SYM, swing_high_sequence, swing_low_sequence
from sniper_data.pattern_detection.mss import SwingPoint
from sniper_data.pipeline import run_anchor_wiring_demo
from sniper_data.volume_profile import redis_volume_profile_key


def _assert_anchor_contract(payload: dict) -> None:
    assert set(ANCHOR_REQUIRED) <= set(payload)
    assert set(payload) <= set(ANCHOR_FIELDS)
    assert payload["source"] in ANCHOR_SOURCES
    assert "schema_version" not in payload
    assert "created_ts_ms" not in payload
    assert "vwap_value" not in payload


@pytest.mark.asyncio
async def test_swing_high_publishes_exact_anchor_event():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus, swing_lookback=2)
    for b in swing_high_sequence(lookback=2):
        await engine.on_bar(b)

    records = list(bus.topics[ANCHOR_TOPIC])
    assert records, "confirmed swing high must publish anchor_events"
    rec = records[-1]
    assert rec["key"] == SYM
    payload = rec["value"]
    _assert_anchor_contract(payload)
    assert payload["symbol"] == SYM
    assert payload["source"] == "swing_high"
    assert payload["anchor_price"] == 120.0
    pivot = swing_high_sequence(lookback=2)[2]
    assert payload["anchor_time"] == pivot.close_ts_ms
    assert payload["asset_class"] == "crypto"
    assert payload["anchor_id"].startswith("sw-BTCUSDT-swing_high-")
    assert engine.stats.anchors >= 1


@pytest.mark.asyncio
async def test_swing_low_publishes_exact_anchor_event():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus, swing_lookback=2)
    for b in swing_low_sequence(lookback=2):
        await engine.on_bar(b)
    payload = bus.topics[ANCHOR_TOPIC][-1]["value"]
    _assert_anchor_contract(payload)
    assert payload["source"] == "swing_low"
    assert payload["anchor_price"] == 80.0


@pytest.mark.asyncio
async def test_anchor_event_idempotent_on_anchor_id():
    bus = InMemoryBus()
    swing = SwingPoint("high", 64_000.0, 1_725_458_400_000, 2)
    req = swing_to_registration(SYM, swing, AssetClass.CRYPTO)
    first = await publish_anchor(bus, req)
    second = await publish_anchor(bus, req)
    assert first == second
    assert first["anchor_id"] == second["anchor_id"]
    assert len(bus.topics[ANCHOR_TOPIC]) == 2
    assert bus.topics[ANCHOR_TOPIC][0]["value"]["anchor_id"] == bus.topics[ANCHOR_TOPIC][1]["value"]["anchor_id"]


def test_payload_uses_only_locked_fields():
    req = AnchorRegistration(
        symbol="BTCUSDT",
        anchor_time=1_725_458_400_000,
        anchor_price=64_000.0,
        source=AnchorSource.SWING_HIGH,
        asset_class=AssetClass.CRYPTO,
        anchor_id="optional-id",
    )
    payload = to_anchor_payload(req)
    _assert_anchor_contract(payload)
    assert payload == {
        "symbol": "BTCUSDT",
        "anchor_time": 1_725_458_400_000,
        "anchor_price": 64_000.0,
        "source": "swing_high",
        "anchor_id": "optional-id",
        "asset_class": "crypto",
    }


@pytest.mark.asyncio
async def test_http_helper_posts_locked_json():
    store = InMemoryStateStore()
    app = create_app(store=store)
    http = TestClient(app)
    req = AnchorRegistration(
        symbol="BTCUSDT",
        anchor_time=1_725_458_400_000,
        anchor_price=64_000.0,
        source=AnchorSource.SWING_HIGH,
    )
    body = await post_anchor(req, client=http)
    assert body["anchor_id"]
    assert body["source"] == "swing_high"
    assert body["symbol"] == "BTCUSDT"
    assert body["anchor_time"] == 1_725_458_400_000
    assert body["anchor_price"] == 64_000.0
    listed = http.get("/v1/anchors?symbol=BTCUSDT").json()
    assert listed["anchors"]
    assert listed["anchors"][0]["source"] == "swing_high"


@pytest.mark.asyncio
async def test_redis_helpers_parse_landed_phase2_shapes():
    store = InMemoryStateStore()
    snap = AnchoredVWAP(
        anchor_id="a1",
        symbol=SYM,
        anchor_time=1_000,
        anchor_price=64_000.0,
        vwap_value=64_100.0,
        bands=AVWAPBands(
            plus_1_sigma=64_200.0,
            plus_2_sigma=64_300.0,
            plus_3_sigma=64_400.0,
            minus_1_sigma=64_000.0,
            minus_2_sigma=63_900.0,
            minus_3_sigma=63_800.0,
        ),
        asset_class=AssetClass.CRYPTO,
    )
    await store.set(redis_avwap_key(SYM, "a1"), to_wire(snap))
    got = await get_avwap(store, SYM, "a1")
    assert got is not None
    wire = got.model_dump(mode="json")
    assert set(wire) == {
        "anchor_id",
        "symbol",
        "anchor_time",
        "anchor_price",
        "vwap_value",
        "bands",
        "asset_class",
    }
    assert "schema_version" not in wire
    assert set(wire["bands"]) == {
        "plus_1_sigma",
        "plus_2_sigma",
        "plus_3_sigma",
        "minus_1_sigma",
        "minus_2_sigma",
        "minus_3_sigma",
    }

    prof = VolumeProfile(
        symbol=SYM,
        session_type=SessionType.NY_AM,
        high_volume_nodes=[VolumeNode(price=65_000.0, volume=100.0)],
        low_volume_nodes=[VolumeNode(price=64_900.0, volume=10.0)],
        poc=65_000.0,
        timestamp=2_000,
    )
    await store.set(redis_volume_profile_key(SYM, SessionType.NY_AM), prof)
    vp = await get_volume_profile(store, SYM, "ny_am")
    assert vp is not None
    assert vp.poc == 65_000.0
    assert vp.session_type == SessionType.NY_AM
    assert "schema_version" not in vp.model_dump(mode="json")

    kz = KillZoneEvent(
        symbol=SYM,
        kill_zone=SessionType.NY_AM,
        start_time=1,
        end_time=2,
        active=True,
        asset_class=AssetClass.CRYPTO,
    )
    await store.set(redis_kill_zone_key(SYM), kz)
    seen: list[KillZoneEvent] = []

    async def _cb(ev: KillZoneEvent) -> None:
        seen.append(ev)

    bus = InMemoryBus()
    subscribe_kill_zone_events(bus, _cb)
    await bus.publish("kill_zone_events", kz.model_dump(mode="json"), key=SYM)
    book = await get_kill_zone(store, SYM)
    assert book is not None
    assert book.kill_zone == SessionType.NY_AM
    assert seen and seen[0].kill_zone == SessionType.NY_AM


@pytest.mark.asyncio
async def test_inmemory_demo_swing_to_avwap_read():
    result = await run_anchor_wiring_demo()
    ev = result["anchor_event"]
    _assert_anchor_contract(ev)
    assert ev["source"] == "swing_high"
    avwap = result["avwap"]
    assert avwap["anchor_id"] == ev["anchor_id"]
    assert avwap["symbol"] == SYM
    assert "schema_version" not in avwap
    assert avwap["vwap_value"] > 0
    assert set(avwap["bands"]) == {
        "plus_1_sigma",
        "plus_2_sigma",
        "plus_3_sigma",
        "minus_1_sigma",
        "minus_2_sigma",
        "minus_3_sigma",
    }


@pytest.mark.asyncio
async def test_pipeline_registers_pattern_anchor_and_writes_avwap():
    from datetime import datetime, timezone

    from sniper_data.bus.timescaledb import InMemoryOHLCVStore
    from sniper_data.pipeline import Runtime
    from sniper_data.symbols import normalize_tick

    bus = InMemoryBus()
    store = InMemoryStateStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=InMemoryOHLCVStore())
    await rt.start()
    swing = SwingPoint("low", 100.0, 1, 0)
    req = swing_to_registration(SYM, swing, AssetClass.CRYPTO, anchor_id="ml-sw-1")
    await publish_anchor(bus, req)
    ts = int(datetime(2024, 6, 4, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    await rt.handle_tick(normalize_tick(symbol=SYM, price=100, volume=10, ts=ts))
    await rt.handle_tick(normalize_tick(symbol=SYM, price=102, volume=20, ts=ts + 1))
    body = await get_avwap(store, SYM, "ml-sw-1")
    assert body is not None
    assert body.anchor_id == "ml-sw-1"
    assert body.vwap_value == pytest.approx((100 * 10 + 102 * 20) / 30)
    await rt.stop()
