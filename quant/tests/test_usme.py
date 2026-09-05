from __future__ import annotations

import pytest

from sniper_quant.usme import atr_from_bars, check_provided_levels, compute_usme_levels


def test_short_2x_atr():
    levels = compute_usme_levels(side="short", entry=50.0, atr=1.5)
    assert levels.stop == 53.0
    assert levels.target == 44.0  # 2R of 3.0


def test_invalidation_beyond_structure_long():
    # Structure at 99 is tighter than 2×ATR (96); engine takes the further stop (96).
    levels = compute_usme_levels(side="long", entry=100.0, atr=2.0, invalidation=99.0)
    assert levels.stop <= 96.0
    assert levels.source == "invalidation_beyond"


def test_invalidation_wider_than_atr():
    # Swing low far away → stop beyond that structure, further than 2×ATR.
    levels = compute_usme_levels(side="long", entry=100.0, atr=1.0, invalidation=90.0)
    assert levels.stop < 90.0
    assert levels.stop < 98.0


def test_provided_target_below_min_rr_replaced():
    levels = compute_usme_levels(side="long", entry=100.0, atr=2.0, target=101.0, min_rr=1.5)
    assert levels.target == 108.0


def test_provided_levels_accepted():
    levels = check_provided_levels(side="long", entry=100.0, stop=96.0, target=108.0)
    assert levels.source == "provided"
    assert levels.risk_per_unit == 4.0
    assert abs(levels.r_multiple - 2.0) < 1e-9


def test_provided_levels_low_rr_rejected():
    with pytest.raises(ValueError, match="below USME minimum"):
        check_provided_levels(side="long", entry=100.0, stop=96.0, target=101.0)


def test_inverted_stop_raises():
    with pytest.raises(ValueError):
        compute_usme_levels(side="long", entry=100.0, stop=101.0)


def test_atr_from_bars_wilder_window():
    highs = [10, 11, 12, 13] + [14] * 14
    lows = [9, 9.5, 10, 11] + [13] * 14
    closes = [9.5, 10.5, 11.5, 12.5] + [13.5] * 14
    atr = atr_from_bars(highs, lows, closes, period=14)
    assert atr is not None and atr > 0
