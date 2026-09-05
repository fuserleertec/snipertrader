from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.kill_zones import (
    KillZoneScheduler,
    apply_killzone_tick,
    redis_kill_zone_active_key,
    redis_kill_zone_key,
)
from sniper_data.models import AssetClass


def _ms(y, m, d, hh, mm) -> int:
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp() * 1000)


def test_crypto_zone_start_and_end():
    sched = KillZoneScheduler(["BTCUSDT"])
    # London 07:00 UTC
    starts = sched.transitions(_ms(2024, 6, 4, 7, 0))
    assert any(
        t.reason == "start" and t.event.kill_zone.value == "london" and t.event.active
        for t in starts
    )
    # Still London — no new start
    assert sched.transitions(_ms(2024, 6, 4, 10, 0)) == []
    # NY AM starts, London ends
    moved = sched.transitions(_ms(2024, 6, 4, 13, 30))
    reasons = {(t.reason, t.event.kill_zone.value, t.event.active) for t in moved}
    assert ("end", "london", False) in reasons
    assert ("start", "ny_am", True) in reasons
    # Gap after NY AM (15:00–18:00) — NY AM ends, nothing active
    gap = sched.transitions(_ms(2024, 6, 4, 15, 0))
    assert any(t.reason == "end" and t.event.kill_zone.value == "ny_am" for t in gap)
    books = sched.current_books(_ms(2024, 6, 4, 15, 0))
    assert books[0].active is False
    assert books[0].kill_zone.value == "ny_am"


def test_equity_rth_over_eth_in_redis_book():
    sched = KillZoneScheduler(["AAPL"])
    # 10:00 EDT = 14:00 UTC on 2024-07-16 — ETH already open, RTH open
    now = _ms(2024, 7, 16, 14, 0)
    tr = sched.transitions(now)
    zones = {t.event.kill_zone.value for t in tr if t.event.active}
    assert zones == {"eth", "rth"}
    book = sched.current_books(now)[0]
    assert book.kill_zone.value == "rth"
    assert book.active is True
    # After RTH close 20:00 UTC (16:00 EDT) ETH remains
    after_rth = _ms(2024, 7, 16, 20, 0)
    later = sched.transitions(after_rth)
    assert any(t.reason == "end" and t.event.kill_zone.value == "rth" for t in later)
    book = sched.current_books(after_rth)[0]
    assert book.kill_zone.value == "eth"
    assert book.active is True


@pytest.mark.asyncio
async def test_apply_tick_writes_redis_and_kafka():
    bus = InMemoryBus()
    store = InMemoryStateStore()
    sched = KillZoneScheduler(["BTCUSDT", "AAPL", "ES"])
    now = _ms(2024, 6, 4, 14, 0)  # crypto NY AM; AAPL/ES RTH
    tr = await apply_killzone_tick(bus, store, sched, now)
    assert tr
    assert bus.latest("kill_zone_events") is not None
    btc = await store.get(redis_kill_zone_key("BTCUSDT"))
    assert btc["kill_zone"] == "ny_am"
    assert btc["active"] is True
    assert btc["asset_class"] == "crypto"
    assert "schema_version" not in btc
    assert set(btc) == {
        "symbol",
        "kill_zone",
        "start_time",
        "end_time",
        "active",
        "asset_class",
    }
    klass = await store.get(redis_kill_zone_active_key(AssetClass.CRYPTO))
    assert klass["kill_zone"] == "ny_am"
    assert "symbol" not in klass
    aapl = await store.get(redis_kill_zone_key("AAPL"))
    assert aapl["kill_zone"] == "rth"
    es = await store.get(redis_kill_zone_key("ES"))
    assert es["kill_zone"] == "rth"
    assert es["asset_class"] == "futures"
