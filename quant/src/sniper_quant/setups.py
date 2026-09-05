"""Locked setup_type enum from ML Researchers (Phase 2 alignment).

ML publishes to ``setup_signals`` in Phase 2 only after ``POST /risk/validate``
returns ``approved: true``. These seven names are the contract — unknown values
are rejected (422) on the pre-filter.
"""

from __future__ import annotations

SETUP_TYPES: tuple[str, ...] = (
    "sweep_reclaim",
    "fvg_entry",
    "mss_break",
    "order_block",
    "sweep_mss",
    "ob_fvg",
    "po3_judas",
)

SETUP_TYPE_NOTES: dict[str, str] = {
    "sweep_reclaim": "Liquidity sweep + reclaim.",
    "fvg_entry": "Fair-value gap entry.",
    "mss_break": "Market-structure shift / break.",
    "order_block": "Order-block reaction.",
    "sweep_mss": "Sweep followed by market-structure shift.",
    "ob_fvg": "Order block + fair-value gap confluence.",
    "po3_judas": "Power of Three / Judas swing.",
}

SIGNAL_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m")

SESSION_TYPES: tuple[str, ...] = (
    "asia",
    "london",
    "ny_am",
    "ny_pm",
    "rth",
    "eth",
    "globex",
)


def is_known_setup(setup_type: str) -> bool:
    return setup_type in SETUP_TYPES
