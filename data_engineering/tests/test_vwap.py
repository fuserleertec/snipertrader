"""Hand-calculated fixtures for volume-weighted VWAP + σ bands.

TradingView comparison
----------------------
TradingView's built-in VWAP study typically plots VWAP from
``sum(src * volume) / sum(volume)`` (often ``src = hlc3`` on bars) and
then draws bands with an *unweighted* ``stdev`` of ``src − vwap``.

This engine uses the volume-weighted population variance

    σ = sqrt( Σ v_i (p_i − VWAP)² / Σ v_i )

Consequences:

* Equal volume on every print → our σ matches the *population* stdev of
  price (and matches TV if TV is configured for population stdev and
  equal volume).
* Unequal volume → our bands sit closer to the heavy-volume prints than
  TV's unweighted bands. That is the Rev. 1.1 correction, not a bug.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from sniper_data.models import AnchorType, AssetClass
from sniper_data.vwap import VWAPEngine, volume_weighted_vwap_sigma


def test_hand_calculated_unequal_volume():
    prices = [100.0, 102.0, 98.0]
    volumes = [10.0, 20.0, 30.0]
    # W = 60
    # S = 100*10 + 102*20 + 98*30 = 5980
    # VWAP = 5980/60 = 299/3
    # Q = 100^2*10 + 102^2*20 + 98^2*30 = 596200
    # σ² = 596200/60 − (5980/60)² = 29/9
    vwap, sigma = volume_weighted_vwap_sigma(prices, volumes)
    assert vwap == pytest.approx(5980 / 60)
    assert sigma == pytest.approx(math.sqrt(29 / 9))


def test_equal_volume_matches_population_stdev():
    prices = [10.0, 20.0, 30.0]
    volumes = [1.0, 1.0, 1.0]
    vwap, sigma = volume_weighted_vwap_sigma(prices, volumes)
    mean = 20.0
    pop_var = ((10 - 20) ** 2 + (20 - 20) ** 2 + (30 - 20) ** 2) / 3
    assert vwap == pytest.approx(mean)
    assert sigma == pytest.approx(math.sqrt(pop_var))


def test_unequal_volume_diverges_from_unweighted_stdev():
    """Documents the TradingView mismatch on unequal volume."""
    prices = [100.0, 110.0]
    volumes = [99.0, 1.0]
    vwap, sigma = volume_weighted_vwap_sigma(prices, volumes)
    unweighted_mean = 105.0
    unweighted_sigma = math.sqrt(((100 - 105) ** 2 + (110 - 105) ** 2) / 2)
    assert vwap != pytest.approx(unweighted_mean)
    assert sigma != pytest.approx(unweighted_sigma)
    # Heavy volume at 100 pulls VWAP toward 100.
    assert vwap == pytest.approx((100 * 99 + 110 * 1) / 100)


def test_incremental_engine_matches_oracle():
    prices = [100.0, 102.0, 98.0, 101.5, 99.25]
    volumes = [10.0, 20.0, 30.0, 5.0, 15.0]
    # Crypto Tuesday 10:00 UTC is London session — session VWAP stays open.
    base = datetime(2024, 6, 4, 10, 0, tzinfo=timezone.utc)
    engine = VWAPEngine(rolling_periods=20)
    last = None
    for i, (p, v) in enumerate(zip(prices, volumes, strict=True)):
        ts_ms = int(base.timestamp() * 1000) + i * 1000
        snaps = engine.on_tick("BTCUSDT", p, v, ts_ms, AssetClass.CRYPTO)
        last = {s.anchor_type: s for s in snaps}
    assert last is not None
    oracle_v, oracle_s = volume_weighted_vwap_sigma(prices, volumes)
    sess = last[AnchorType.SESSION]
    weekly = last[AnchorType.WEEKLY]
    rolling = last[AnchorType.ROLLING]
    for snap in (sess, weekly, rolling):
        assert snap.vwap == pytest.approx(oracle_v)
        assert snap.sigma == pytest.approx(oracle_s)
        assert snap.band_p2 == pytest.approx(oracle_v + 2 * oracle_s)
        assert snap.band_m3 == pytest.approx(oracle_v - 3 * oracle_s)


def test_rolling_window_drops_oldest():
    engine = VWAPEngine(rolling_periods=2)
    ts = int(datetime(2024, 6, 4, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    engine.on_tick("BTCUSDT", 10.0, 1.0, ts, AssetClass.CRYPTO)
    engine.on_tick("BTCUSDT", 20.0, 1.0, ts + 1, AssetClass.CRYPTO)
    snaps = engine.on_tick("BTCUSDT", 30.0, 1.0, ts + 2, AssetClass.CRYPTO)
    rolling = next(s for s in snaps if s.anchor_type is AnchorType.ROLLING)
    vwap, sigma = volume_weighted_vwap_sigma([20.0, 30.0], [1.0, 1.0])
    assert rolling.n_obs == 2
    assert rolling.vwap == pytest.approx(vwap)
    assert rolling.sigma == pytest.approx(sigma)


def test_session_vwap_resets_on_boundary():
    engine = VWAPEngine()
    # Asia 06:59 → London 07:00 UTC
    asia = int(datetime(2024, 6, 4, 6, 59, tzinfo=timezone.utc).timestamp() * 1000)
    london = int(datetime(2024, 6, 4, 7, 0, tzinfo=timezone.utc).timestamp() * 1000)
    engine.on_tick("BTCUSDT", 100.0, 10.0, asia, AssetClass.CRYPTO)
    snaps = engine.on_tick("BTCUSDT", 200.0, 10.0, london, AssetClass.CRYPTO)
    sess = next(s for s in snaps if s.anchor_type is AnchorType.SESSION)
    assert sess.vwap == pytest.approx(200.0)
    assert sess.n_obs == 1
    assert sess.session_type.value == "london"


def test_zero_volume_ignored():
    engine = VWAPEngine()
    ts = int(datetime(2024, 6, 4, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
    out = engine.on_tick("BTCUSDT", 100.0, 0.0, ts, AssetClass.CRYPTO)
    # Session/weekly have no weight yet; rolling may also be empty.
    assert all(s.cum_volume > 0 for s in out)


def test_rejects_negative_volume_in_oracle():
    with pytest.raises(ValueError):
        volume_weighted_vwap_sigma([1.0], [-1.0])
