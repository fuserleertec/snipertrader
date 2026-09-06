"""Corrected sweep: delta divergence + reclaim. Low volume must NOT gate."""

from __future__ import annotations

import inspect

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import FVG_TTL_MAX_SECONDS
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.pattern_detection.fixtures import (
    london_session,
    sell_side_sweep_sequence,
    buy_side_sweep_sequence,
)
from sniper_data.pattern_detection.sweep import SweepDetector
from sniper_data.pattern_detection.validate import validate_topic


def _engine() -> tuple[PatternEngine, InMemoryBus, InMemoryStateStore]:
    bus = InMemoryBus()
    store = InMemoryStateStore()
    return PatternEngine(store, bus), bus, store


async def _run_sell(volume: float):
    engine, bus, store = _engine()
    engine.sweep.on_session(london_session(high=100.0, low=90.0))
    for b in sell_side_sweep_sequence(sweep_volume=volume):
        await engine.on_bar(b)
    return engine, bus, store


@pytest.mark.asyncio
async def test_low_volume_does_not_gate_sell_side_sweep():
    """A 0.01-volume stop-run still emits. Fails if volume is reintroduced as a gate."""
    engine, bus, store = await _run_sell(0.01)
    sweeps = [r["value"] for r in bus.topics["sweep_events"]]
    assert sweeps, "low-volume sweep with delta divergence must still publish"
    first = sweeps[0]
    validate_topic("sweep_events", first)
    assert first["side"] == "sell"
    assert first["swept_level"] == 100.0
    assert first["delta_divergence"] is True
    assert first["volume_profile"] == "low_volume"
    assert "direction" not in first
    assert "sweep_level" not in first
    assert any(k.startswith("sweep:BTCUSDT:") for k in store.data)
    key = next(k for k in store.data if k.startswith("sweep:BTCUSDT:"))
    assert 1 <= await store.ttl(key) <= FVG_TTL_MAX_SECONDS
    confirmed = [s for s in sweeps if s.get("confirmed")]
    assert confirmed
    assert confirmed[-1]["reclaim"] is True
    assert confirmed[-1]["time_to_reclaim_ms"] == 60_000


@pytest.mark.asyncio
async def test_aggressive_volume_also_emits():
    engine, bus, _store = await _run_sell(180.0)
    first = bus.topics["sweep_events"][0]["value"]
    assert first["volume_profile"] == "aggressive"
    assert first["delta_divergence"] is True
    assert first["side"] == "sell"


@pytest.mark.asyncio
async def test_buy_side_sweep_session_low():
    engine, bus, store = _engine()
    engine.sweep.on_session(london_session(high=100.0, low=90.0))
    for b in buy_side_sweep_sequence(sweep_volume=0.02):
        await engine.on_bar(b)
    first = bus.topics["sweep_events"][0]["value"]
    validate_topic("sweep_events", first)
    assert first["side"] == "buy"
    assert first["swept_level"] == 90.0
    assert first["delta_divergence"] is True
    assert first["volume_profile"] == "low_volume"
    confirmed = [r["value"] for r in bus.topics["sweep_events"] if r["value"].get("confirmed")]
    assert confirmed and confirmed[-1]["reclaim"] is True
    assert any(k.startswith("sweep:BTCUSDT:") for k in store.data)


def test_detect_break_source_has_no_volume_gate():
    """Regression: _detect_break must not branch on low_volume / bar.volume."""
    src = inspect.getsource(SweepDetector._detect_break)
    code = "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))
    assert "_score_volume_profile" in code
    assert "if bar.volume" not in code
    assert "low_volume" not in code
    assert "if profile" not in code


@pytest.mark.asyncio
async def test_break_without_delta_divergence_is_not_a_sweep():
    from sniper_data.pattern_detection.fixtures import bar, range_bars

    engine, bus, _store = _engine()
    engine.sweep.on_session(london_session())
    for b in range_bars(6):
        await engine.on_bar(b)
    # Break the high on *rising* buy delta — a continuation, not a stop-run.
    await engine.on_bar(bar(6, 99, 102, 99, 101.5, 80.0, buy=80.0, sell=0.0))
    assert list(bus.topics["sweep_events"]) == []
