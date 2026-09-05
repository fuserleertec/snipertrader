"""Anchored VWAP: volume-weighted bands from an explicit anchor."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from sniper_data.avwap import (
    AnchoredVWAPEngine,
    bands_from_sigma,
    redis_avwap_key,
    to_wire,
)
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.models import AnchorRegistration, AnchorSource, AssetClass
from sniper_data.pipeline import Runtime
from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.symbols import normalize_tick
from sniper_data.vwap import volume_weighted_vwap_sigma


def test_bands_match_phase1_sigma_formula():
    prices = [100.0, 102.0, 98.0]
    volumes = [10.0, 20.0, 30.0]
    vwap, sigma = volume_weighted_vwap_sigma(prices, volumes)
    bands = bands_from_sigma(vwap, sigma)
    assert bands.plus_1_sigma == pytest.approx(vwap + sigma)
    assert bands.plus_2_sigma == pytest.approx(vwap + 2 * sigma)
    assert bands.plus_3_sigma == pytest.approx(vwap + 3 * sigma)
    assert bands.minus_1_sigma == pytest.approx(vwap - sigma)
    assert bands.minus_2_sigma == pytest.approx(vwap - 2 * sigma)
    assert bands.minus_3_sigma == pytest.approx(vwap - 3 * sigma)
    # Hand-calc from Phase 1 fixture: VWAP = 5980/60, σ = sqrt(29/9)
    assert vwap == pytest.approx(5980 / 60)
    assert sigma == pytest.approx(math.sqrt(29 / 9))


def test_engine_from_anchor_time_matches_oracle():
    engine = AnchoredVWAPEngine()
    meta = engine.register(
        AnchorRegistration(
            symbol="BTCUSDT",
            anchor_time=1_000,
            anchor_price=64_000.0,
            source=AnchorSource.MANUAL,
            asset_class=AssetClass.CRYPTO,
            anchor_id="anchor-1",
        )
    )
    assert meta.anchor_id == "anchor-1"
    prices = [64_000.0, 64_100.0, 63_900.0]
    volumes = [10.0, 20.0, 30.0]
    last = None
    for i, (p, v) in enumerate(zip(prices, volumes, strict=True)):
        snaps = engine.on_tick("BTCUSDT", p, v, 1_000 + i * 100, AssetClass.CRYPTO)
        last = snaps[0]
    oracle_v, oracle_s = volume_weighted_vwap_sigma(prices, volumes)
    assert last is not None
    assert last.vwap_value == pytest.approx(oracle_v)
    assert last.bands.plus_2_sigma == pytest.approx(oracle_v + 2 * oracle_s)
    assert last.bands.minus_3_sigma == pytest.approx(oracle_v - 3 * oracle_s)
    wire = to_wire(last)
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
    assert redis_avwap_key("BTCUSDT", "anchor-1") == "avwap:BTCUSDT:anchor-1"


def test_ticks_before_anchor_are_ignored():
    engine = AnchoredVWAPEngine()
    engine.register(
        AnchorRegistration(
            symbol="AAPL",
            anchor_time=5_000,
            anchor_price=200.0,
            asset_class=AssetClass.EQUITY,
            anchor_id="a",
        )
    )
    assert engine.on_tick("AAPL", 199.0, 10.0, 4_999, AssetClass.EQUITY) == []
    snaps = engine.on_tick("AAPL", 201.0, 10.0, 5_000, AssetClass.EQUITY)
    assert len(snaps) == 1
    assert snaps[0].vwap_value == pytest.approx(201.0)
    assert snaps[0].bands.plus_1_sigma == pytest.approx(201.0)


@pytest.mark.asyncio
async def test_pipeline_writes_avwap_redis_key():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=InMemoryOHLCVStore())
    await rt.start()
    from sniper_data.avwap import persist_anchor

    meta = rt.avwap.register(
        AnchorRegistration(
            symbol="BTCUSDT",
            anchor_time=1,
            anchor_price=100.0,
            anchor_id="pipe-1",
            asset_class=AssetClass.CRYPTO,
        )
    )
    await persist_anchor(store, meta)
    ts = int(datetime(2024, 6, 4, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    await rt.handle_tick(normalize_tick(symbol="BTCUSDT", price=100, volume=10, ts=ts))
    await rt.handle_tick(normalize_tick(symbol="BTCUSDT", price=102, volume=20, ts=ts + 1))
    body = await store.get("avwap:BTCUSDT:pipe-1")
    assert body["vwap_value"] == pytest.approx((100 * 10 + 102 * 20) / 30)
    assert body["anchor_id"] == "pipe-1"
    assert "schema_version" not in body
    latest = await store.get("avwap:latest:BTCUSDT")
    assert latest["anchor_id"] == "pipe-1"
    await rt.stop()
