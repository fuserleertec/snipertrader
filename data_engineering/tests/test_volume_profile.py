from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sniper_data.models import AssetClass, SessionType
from sniper_data.volume_profile import (
    VolumeProfileEngine,
    detect_nodes,
    price_bin,
    redis_volume_profile_key,
)


def test_poc_is_max_volume_price():
    bins = {65000.0: 1500.5, 64900.0: 200.0, 65100.0: 400.0}
    hvn, lvn, poc = detect_nodes(bins)
    assert poc == 65000.0
    assert hvn[0].price == 65000.0
    assert hvn[0].volume == 1500.5
    lvn_prices = {n.price for n in lvn}
    assert 64900.0 in lvn_prices or 65100.0 in lvn_prices


def test_hvn_lvn_local_extrema():
    # valley at 10, peaks at 0 and 20
    bins = {0.0: 100.0, 10.0: 10.0, 20.0: 80.0}
    hvn, lvn, poc = detect_nodes(bins)
    assert poc == 0.0
    assert {n.price for n in hvn} >= {0.0}
    assert any(n.price == 10.0 for n in lvn)


def test_single_bin_is_poc_and_hvn():
    hvn, lvn, poc = detect_nodes({100.0: 5.0})
    assert poc == 100.0
    assert len(hvn) == 1
    assert hvn[0].volume == 5.0
    assert lvn == []


def test_price_bin_rounding():
    assert price_bin(65002.4, 5.0) == 65000.0
    assert price_bin(65003.0, 5.0) == 65005.0
    assert price_bin(228.42, 0.05) == pytest.approx(228.40)
    assert price_bin(5812.30, 0.25) == pytest.approx(5812.25)


def test_engine_accumulates_crypto_session():
    engine = VolumeProfileEngine(tick_sizes={"BTCUSDT": 5.0})
    # 2024-06-04 14:00 UTC = NY AM
    t0 = int(datetime(2024, 6, 4, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
    engine.on_tick("BTCUSDT", 65000.0, 1500.5, t0, AssetClass.CRYPTO)
    engine.on_tick("BTCUSDT", 64900.0, 200.0, t0 + 1, AssetClass.CRYPTO)
    snaps = engine.on_tick("BTCUSDT", 65001.0, 10.0, t0 + 2, AssetClass.CRYPTO)
    assert snaps
    prof = snaps[0]
    assert prof.session_type is SessionType.NY_AM
    assert prof.poc == 65000.0
    assert redis_volume_profile_key("BTCUSDT", "ny_am") == "volume_profile:BTCUSDT:ny_am"
    wire = prof.model_dump(mode="json")
    assert set(wire) == {
        "symbol",
        "session_type",
        "high_volume_nodes",
        "low_volume_nodes",
        "poc",
        "timestamp",
    }
    assert "schema_version" not in wire


def test_equity_writes_eth_and_rth():
    engine = VolumeProfileEngine()
    # 2024-07-16 15:00 UTC = 11:00 EDT — ETH + RTH
    t0 = int(datetime(2024, 7, 16, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)
    snaps = engine.on_tick("AAPL", 228.40, 100.0, t0, AssetClass.EQUITY)
    types = {s.session_type for s in snaps}
    assert types == {SessionType.ETH, SessionType.RTH}
