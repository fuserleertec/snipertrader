from __future__ import annotations

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import FVG_TTL_MAX_SECONDS
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.pattern_detection.fixtures import fvg_create_and_fill
from sniper_data.pattern_detection.validate import validate_topic


@pytest.mark.asyncio
async def test_fvg_create_and_fill():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus)
    for b in fvg_create_and_fill():
        await engine.on_bar(b)

    created = [r["value"] for r in bus.topics["fvg_zones"] if not r["value"].get("mitigated")]
    filled = [r["value"] for r in bus.topics["fvg_zones"] if r["value"].get("mitigated")]
    assert created
    zone = created[0]
    validate_topic("fvg_zones", zone)
    assert zone["direction"] == "bullish"
    assert zone["low"] == 100.0
    assert zone["high"] == 102.0
    assert zone["mitigated"] is False
    assert filled
    validate_topic("fvg_zones", filled[-1])
    assert filled[-1]["id"] == zone["id"]
    assert filled[-1]["mitigated"] is True

    key = f"fvg:{zone['symbol']}:{zone['id']}"
    assert key in store.data
    assert 1 <= await store.ttl(key) <= FVG_TTL_MAX_SECONDS
    cached = await store.get(key)
    assert cached["mitigated"] is True
