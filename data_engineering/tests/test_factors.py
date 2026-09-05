from __future__ import annotations

import pytest

from sniper_data.setup_detection.factors import (
    STABLE_FACTORS,
    add_factor,
    explain,
    factor_row,
    scale_breakdown,
)


def test_stable_names_are_the_frontend_contract():
    assert STABLE_FACTORS == (
        "liquidity_sweep",
        "mss",
        "fvg",
        "order_block",
        "vwap_reclaim",
        "vwap_band_extension",
        "vwap_pullback",
        "first_touch",
        "low_volume",
        "volume_confirm",
        "rejection_candle",
        "engulfing",
        "avwap",
        "htf_ob",
        "kill_zone",
        "multi_pattern",
        "trend_align",
    )


def test_explain_scales_scores_to_conviction():
    names, rows = explain(["liquidity_sweep", "mss", "vwap_reclaim"], conviction=75)
    assert names == ["liquidity_sweep", "mss", "vwap_reclaim"]
    assert abs(sum(r["score"] for r in rows) - 75) <= 0.05
    assert all({"name", "weight", "score", "note"} <= set(r) for r in rows)


def test_unknown_factor_rejected():
    with pytest.raises(ValueError, match="unknown contributing factor"):
        factor_row("trend_vwap")


def test_add_factor_is_idempotent_then_scale():
    rows = []
    add_factor(rows, "kill_zone", 10)
    add_factor(rows, "kill_zone", 99)
    add_factor(rows, "multi_pattern", 10)
    scaled = scale_breakdown(rows, 80)
    assert [r["name"] for r in scaled] == ["kill_zone", "multi_pattern"]
    assert abs(sum(r["score"] for r in scaled) - 80) <= 0.05
