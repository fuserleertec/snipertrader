from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.dashboard import (
    DASHBOARD_SNAPSHOT_TOPIC,
    REDIS_SNAPSHOT_INDEX,
    publish_snapshots,
    redis_snapshot_key,
    refresh_paper_state,
)
from sniper_data.models import AssetClass
from sniper_data.pipeline import Runtime
from sniper_data.symbols import infer_asset_class, normalize_tick
from sniper_data.universe import DEFAULT_UNIVERSE_CSV, REDIS_UNIVERSE_ACTIVE, parse_universe


MIXED = parse_universe(DEFAULT_UNIVERSE_CSV)


@pytest.mark.asyncio
async def test_ten_plus_mixed_symbols_process_and_snapshot():
    assert len(MIXED) >= 10
    assert {"ES", "CL", "GC", "NQ"} <= set(MIXED)
    classes = {infer_asset_class(s) for s in MIXED}
    assert AssetClass.CRYPTO in classes
    assert AssetClass.EQUITY in classes
    assert AssetClass.FUTURES in classes

    bus = InMemoryBus()
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=bars)
    await rt.start()
    t0 = int(datetime(2024, 6, 4, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
    prices = {
        "BTCUSDT": 65000.0,
        "ETHUSDT": 3400.0,
        "SOLUSDT": 148.0,
        "BNBUSDT": 580.0,
        "AAPL": 228.0,
        "MSFT": 415.0,
        "NVDA": 118.0,
        "SPY": 542.0,
        "ES": 5812.0,
        "NQ": 20140.0,
        "CL": 78.0,
        "GC": 2364.0,
    }
    for i, symbol in enumerate(MIXED):
        px = prices.get(symbol, 100.0)
        await rt.handle_tick(normalize_tick(symbol=symbol, price=px, volume=10.0, ts=t0 + i * 50))
        await rt.handle_tick(
            normalize_tick(symbol=symbol, price=px + 0.5, volume=8.0, ts=t0 + i * 50 + 20)
        )
    await rt.stop()

    for symbol in MIXED:
        assert rt.ticks_by_class[infer_asset_class(symbol).value] >= 2
        weekly = await store.get(f"vwap:{symbol}:weekly")
        assert weekly is not None

    result = await publish_snapshots(store, MIXED, bus=bus, now_ms=t0, cadence_s=900)
    assert result["live_trading"] is False
    assert set(result["symbols"]) == set(MIXED)
    assert len(result["snapshots"]) == len(MIXED)
    for symbol in MIXED:
        key = redis_snapshot_key(symbol)
        body = await store.get(key)
        assert body is not None
        assert body["symbol"] == symbol
        assert body["live_trading"] is False
        assert body["cadence_s"] == 900
        assert "pointers" in body
        assert set(body["pointers"]) == {
            "vwap",
            "session",
            "avwap_latest",
            "kill_zone",
            "volume_profile",
        }
    index = await store.get(REDIS_SNAPSHOT_INDEX)
    assert index["count"] == len(MIXED)
    active = await store.get(REDIS_UNIVERSE_ACTIVE)
    assert active["live_trading"] is False
    assert {row["symbol"] for row in active["symbols"]} == set(MIXED)
    assert all(set(row) >= {"symbol", "asset_class"} for row in active["symbols"])
    kafka_keys = {rec["key"] for rec in bus.topics[DASHBOARD_SNAPSHOT_TOPIC]}
    assert set(MIXED) <= kafka_keys
    assert "_index" in kafka_keys
    assert "_universe" in kafka_keys


@pytest.mark.asyncio
async def test_refresh_seeds_history_and_patterns_for_futures():
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    bus = InMemoryBus()
    symbols = ["ES", "CL", "GC", "NQ", "BTCUSDT", "AAPL"]
    out = await refresh_paper_state(
        store,
        symbols,
        bus=bus,
        bars=bars,
        now_ms=1_717_502_400_000,
        cadence_s=900,
    )
    assert set(out["symbols"]) == set(symbols)
    for symbol in symbols:
        hist = await bars.fetch(symbol, "1m", limit=50)
        assert len(hist) >= 20
        sweep = await store.get(f"sweep:{symbol}:sw-{symbol}-1")
        assert sweep is not None
        signals = await store.get(f"setup:index:{symbol}")
        assert signals and len(signals) == 3
    assert await store.get(REDIS_UNIVERSE_ACTIVE) is not None
