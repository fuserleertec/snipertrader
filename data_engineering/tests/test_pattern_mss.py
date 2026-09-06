from __future__ import annotations

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import FVG_TTL_MAX_SECONDS
from sniper_data.models import SweepEvent, AssetClass
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.pattern_detection.fixtures import (
    SYM,
    mss_after_buy_sweep_bars,
    mss_after_sell_sweep_bars,
)
from sniper_data.pattern_detection.validate import validate_topic


@pytest.mark.asyncio
async def test_bullish_mss_after_sell_side_sweep():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus, swing_lookback=2)
    sweep, bars = mss_after_sell_sweep_bars()
    engine.mss.on_sweep(sweep)
    for b in bars:
        await engine.on_bar(b)

    events = [r["value"] for r in bus.topics["mss_events"]]
    assert events, "MSS must fire after a real sell-side sweep + LH break"
    ev = events[-1]
    validate_topic("mss_events", ev)
    assert ev["direction"] == "bullish"
    assert ev["trigger_sweep_id"] == sweep.id
    assert ev["trigger_sweep_side"] == "sell"
    assert ev["broken_level"] == 95.0
    key = f"mss:{ev['symbol']}:{ev['id']}"
    assert key in store.data
    assert 1 <= await store.ttl(key) <= FVG_TTL_MAX_SECONDS


@pytest.mark.asyncio
async def test_bearish_mss_after_buy_side_sweep():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus, swing_lookback=2)
    sweep, bars = mss_after_buy_sweep_bars()
    engine.mss.on_sweep(sweep)
    for b in bars:
        await engine.on_bar(b)
    ev = bus.topics["mss_events"][-1]["value"]
    validate_topic("mss_events", ev)
    assert ev["direction"] == "bearish"
    assert ev["trigger_sweep_id"] == sweep.id
    assert ev["trigger_sweep_side"] == "buy"
    assert ev["broken_level"] == 92.0


@pytest.mark.asyncio
async def test_mss_does_not_invent_sweeps():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus, swing_lookback=2)
    # Same bar path as the bullish fixture, but no sweep was consumed.
    _, bars = mss_after_sell_sweep_bars()
    for b in bars:
        await engine.on_bar(b)
    assert list(bus.topics["mss_events"]) == []

    with pytest.raises(ValueError):
        engine.mss.on_sweep(
            SweepEvent(
                id="",
                symbol=SYM,
                asset_class=AssetClass.CRYPTO,
                side="sell",
                swept_level=100.0,
                ts_ms=1,
            )
        )
