from __future__ import annotations

import pytest

from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import FVG_TTL_MAX_SECONDS
from sniper_data.models import AssetClass, FVGZone, MssEvent, OrderBlock, SweepEvent
from sniper_data.zones import evict_expired_zones, store_fvg, store_mss, store_ob, store_sweep


@pytest.mark.asyncio
async def test_fvg_write_requires_and_clamps_ttl():
    store = InMemoryStateStore()
    zone = FVGZone(
        id="z1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        direction="bullish",
        high=100.0,
        low=99.0,
        created_ts_ms=1_717_500_000_000,
    )
    key = await store_fvg(store, zone, ttl_seconds=72 * 3600)
    assert key == "fvg:BTCUSDT:z1"
    assert await store.ttl(key) == FVG_TTL_MAX_SECONDS
    with pytest.raises(ValueError, match="TTL"):
        await store.set("fvg:BTCUSDT:bare", {"id": "bare"})


@pytest.mark.asyncio
async def test_sweep_key_and_eviction_repairs_missing_ttl():
    store = InMemoryStateStore()
    event = SweepEvent(
        id="s1",
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        side="sell",
        swept_level=228.0,
        ts_ms=1_717_500_000_000,
    )
    key = await store_sweep(store, event, ttl_seconds=3600)
    assert key == "sweep:AAPL:s1"
    assert await store.ttl(key) == 3600

    # Simulate a write that lost its TTL (unreliable Redis).
    store.data["fvg:ES:old"] = '{"id":"old","created_ts_ms":1717500000000}'
    store.ttls.pop("fvg:ES:old", None)
    assert await store.ttl("fvg:ES:old") == -1
    stats = await evict_expired_zones(store, now_ms=1_717_500_000_000 + 1000)
    assert stats["ttl_repaired"] >= 1
    assert 1 <= await store.ttl("fvg:ES:old") <= FVG_TTL_MAX_SECONDS


@pytest.mark.asyncio
async def test_eviction_deletes_older_than_48h():
    store = InMemoryStateStore()
    created = 1_000_000_000_000
    await store.set(
        "fvg:BTCUSDT:stale",
        {"id": "stale", "created_ts_ms": created},
        ttl=FVG_TTL_MAX_SECONDS,
    )
    now = created + (48 * 3600 + 10) * 1000
    stats = await evict_expired_zones(store, now_ms=now)
    assert stats["expired_deleted"] == 1
    assert await store.get("fvg:BTCUSDT:stale") is None


@pytest.mark.asyncio
async def test_mss_and_ob_ttl_enforced_and_clamped():
    store = InMemoryStateStore()
    mss = MssEvent(
        id="m1",
        symbol="BTCUSDT",
        asset_class=AssetClass.CRYPTO,
        ts_ms=1_717_500_000_000,
        direction="bullish",
        broken_level=99.0,
        swing_high=101.0,
        swing_low=98.0,
        trigger_sweep_id="s1",
        trigger_sweep_side="buy",
    )
    ob = OrderBlock(
        id="ob1",
        symbol="ES",
        asset_class=AssetClass.FUTURES,
        direction="bearish",
        high=5100.0,
        low=5080.0,
        created_ts_ms=1_717_500_000_000,
    )
    mss_key = await store_mss(store, mss, ttl_seconds=72 * 3600)
    ob_key = await store_ob(store, ob, ttl_seconds=72 * 3600)
    assert mss_key == "mss:BTCUSDT:m1"
    assert ob_key == "ob:ES:ob1"
    assert await store.ttl(mss_key) == FVG_TTL_MAX_SECONDS
    assert await store.ttl(ob_key) == FVG_TTL_MAX_SECONDS
    with pytest.raises(ValueError, match="TTL"):
        await store.set("mss:BTCUSDT:bare", {"id": "bare"})
    with pytest.raises(ValueError, match="TTL"):
        await store.set("ob:ES:bare", {"id": "bare"})


@pytest.mark.asyncio
async def test_eviction_scans_mss_and_ob():
    store = InMemoryStateStore()
    created = 1_000_000_000_000
    await store.set("mss:BTCUSDT:stale", {"id": "stale", "ts_ms": created}, ttl=FVG_TTL_MAX_SECONDS)
    await store.set("ob:ES:stale", {"id": "stale", "created_ts_ms": created}, ttl=FVG_TTL_MAX_SECONDS)
    now = created + (48 * 3600 + 10) * 1000
    stats = await evict_expired_zones(store, now_ms=now)
    assert stats["expired_deleted"] == 2
    assert await store.get("mss:BTCUSDT:stale") is None
    assert await store.get("ob:ES:stale") is None
