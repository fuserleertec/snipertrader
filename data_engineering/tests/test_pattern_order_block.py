from __future__ import annotations

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import FVG_TTL_MAX_SECONDS
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.pattern_detection.fixtures import bar, order_block_displacement
from sniper_data.pattern_detection.validate import validate_topic


@pytest.mark.asyncio
async def test_bullish_order_block_from_displacement():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus)
    for b in order_block_displacement():
        await engine.on_bar(b)

    created = [r["value"] for r in bus.topics["order_block_zones"] if not r["value"].get("mitigated")]
    assert created
    zone = created[0]
    validate_topic("order_block_zones", zone)
    assert zone["direction"] == "bullish"
    assert zone["high"] == 100.1
    assert zone["low"] == 98.8
    assert zone["origin_open"] == 100.0
    assert zone["origin_close"] == 99.0
    key = f"ob:{zone['symbol']}:{zone['id']}"
    assert key in store.data
    assert 1 <= await store.ttl(key) <= FVG_TTL_MAX_SECONDS


@pytest.mark.asyncio
async def test_order_block_mitigated_on_retrace():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus)
    for b in order_block_displacement():
        await engine.on_bar(b)
    # Trade back into the origin candle [98.8, 100.1]
    await engine.on_bar(bar(4, 103, 103.2, 99.5, 100.0, 40))
    filled = [r["value"] for r in bus.topics["order_block_zones"] if r["value"].get("mitigated")]
    assert filled
    validate_topic("order_block_zones", filled[-1])
    assert filled[-1]["mitigated"] is True
    cached = await store.get(f"ob:{filled[-1]['symbol']}:{filled[-1]['id']}")
    assert cached["mitigated"] is True
