"""Final DE delta contract: no wire/Redis `delta`; compute in the detector."""

from __future__ import annotations

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.models import OHLCVBar, Timeframe
from sniper_data.pattern_detection.delta import (
    bar_delta,
    classify_tick,
    resolve_bar_delta,
    signed_tick_volume,
)
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.pattern_detection.fixtures import london_session, range_bars, bar
from sniper_data.pattern_detection.validate import to_payload, validate_topic
from sniper_data.symbols import normalize_tick


def test_no_delta_field_on_tick_or_bar_models():
    tick = normalize_tick(symbol="BTCUSDT", price=100, volume=1, ts=1, aggressor="buy")
    dumped = tick.model_dump()
    assert "delta" not in dumped
    assert dumped["aggressor"] == "buy"
    bar_m = OHLCVBar(
        symbol="BTCUSDT",
        asset_class=tick.asset_class,
        timeframe=Timeframe.M1,
        open_ts_ms=0,
        close_ts_ms=60_000,
        open=1,
        high=1,
        low=1,
        close=1,
        volume=5,
        n_ticks=1,
        buy_volume=3,
        sell_volume=2,
    )
    bd = bar_m.model_dump()
    assert "delta" not in bd
    assert bar_delta(bar_m) == 1.0


def test_signed_tick_volume_buy_plus_sell_minus():
    buy = normalize_tick(symbol="BTCUSDT", price=100, volume=4, ts=1, aggressor="buy")
    sell = normalize_tick(symbol="BTCUSDT", price=100, volume=3, ts=1, aggressor="sell")
    assert signed_tick_volume(buy) == 4
    assert signed_tick_volume(sell) == -3


def test_missing_aggressor_classifies_vs_mid():
    above = normalize_tick(symbol="BTCUSDT", price=101, volume=2, ts=1, bid=99, ask=101)
    below = normalize_tick(symbol="BTCUSDT", price=99, volume=2, ts=1, bid=99, ask=101)
    assert classify_tick(above) == "buy"
    assert classify_tick(below) == "sell"
    assert signed_tick_volume(above) == 2
    assert signed_tick_volume(below) == -2


def test_missing_aggressor_and_book_classifies_vs_last():
    first = normalize_tick(symbol="BTCUSDT", price=100, volume=1, ts=1)
    assert classify_tick(first) is None
    up = normalize_tick(symbol="BTCUSDT", price=101, volume=5, ts=2)
    down = normalize_tick(symbol="BTCUSDT", price=99, volume=7, ts=3)
    assert classify_tick(up, last_price=100) == "buy"
    assert classify_tick(down, last_price=100) == "sell"
    assert signed_tick_volume(up, last_price=100) == 5
    assert signed_tick_volume(down, last_price=100) == -7


def test_resolve_bar_delta_prefers_bar_over_tick_fallback():
    classified = bar(0, 100, 101, 99, 100, 10, buy=1.0, sell=9.0)
    assert bar_delta(classified) == -8.0
    # Tick fallback would be the opposite sign — must be ignored.
    assert resolve_bar_delta(classified, tick_fallback=50.0) == -8.0
    unclassified = bar(1, 100, 101, 99, 100, 10, buy=None, sell=None)
    # fixtures.bar() fills buy/sell from close vs open when both None...
    # Build a true unclassified bar:
    raw = classified.model_copy(update={"buy_volume": None, "sell_volume": None})
    assert bar_delta(raw) is None
    assert resolve_bar_delta(raw, tick_fallback=-3.0) == -3.0
    assert resolve_bar_delta(raw, tick_fallback=None) is None


@pytest.mark.asyncio
async def test_cum_delta_uses_bars_not_ticks_and_no_redis_delta_key():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    engine = PatternEngine(store, bus)
    engine.sweep.on_session(london_session())
    for b in range_bars(6):
        # Opposite signed ticks must not override bar buy/sell.
        await engine.on_tick(
            normalize_tick(
                symbol="BTCUSDT",
                price=b.close,
                volume=1_000,
                ts=b.open_ts_ms,
                aggressor="buy",
            )
        )
        await engine.on_bar(b)
    # Break the high on net-sell bar volume (divergence) despite buy ticks.
    sweep_bar = bar(6, 99, 101.5, 98.5, 101.0, 0.01, buy=0.0, sell=0.01)
    await engine.on_tick(
        normalize_tick(symbol="BTCUSDT", price=101.5, volume=9_000, ts=sweep_bar.open_ts_ms, aggressor="buy")
    )
    await engine.on_bar(sweep_bar)
    sweeps = [r["value"] for r in bus.topics["sweep_events"]]
    assert sweeps
    first = sweeps[0]
    validate_topic("sweep_events", first)
    assert "delta" not in first
    assert first["delta_divergence"] is True
    assert first["side"] == "sell"
    dumped = to_payload(sweeps[0])
    assert "delta" not in dumped
    assert not any("delta" in k for k in store.data)


def test_unclassified_bar_uses_last_print_tick_fallback():
    from sniper_data.pattern_detection.delta import DeltaBook

    book = DeltaBook()
    t1 = normalize_tick(symbol="ES", price=5000, volume=2, ts=1)
    t2 = normalize_tick(symbol="ES", price=5001, volume=3, ts=2)
    assert book.on_tick(t1) is None
    assert book.on_tick(t2) == 3  # uptick vs last
    unclassified = OHLCVBar(
        symbol="ES",
        asset_class=t1.asset_class,
        timeframe=Timeframe.M1,
        open_ts_ms=0,
        close_ts_ms=60_000,
        open=5000,
        high=5001,
        low=5000,
        close=5001,
        volume=5,
        n_ticks=2,
        buy_volume=None,
        sell_volume=None,
    )
    assert book.consume_bar(unclassified) == 3
