"""Locked setup_type enum (PM + ML STOP).

Six live values on ``POST /risk/validate``. Dormant names
(``mss_break``, ``order_block``, ``sweep_mss``, ``ob_fvg``) are **not**
in the enum — 422 if sent. Do not walk-forward dormant types.

``contributing_factors`` is publish-only (Kafka / ingest). It is **not**
on the validate candidate.
"""

from __future__ import annotations

SETUP_TYPES: tuple[str, ...] = (
    "sweep_reclaim",
    "fvg_entry",
    "po3_judas",
    "sd_extension_fade",
    "vwap_pullback_cont",
    "avwap_ob_confluence",
)

WALKFORWARD_SETUP_TYPES: tuple[str, ...] = SETUP_TYPES

# Removed from validate. Do not replay / walk-forward.
DORMANT_SETUP_TYPES: tuple[str, ...] = (
    "mss_break",
    "order_block",
    "sweep_mss",
    "ob_fvg",
)

# Frontend GET /performance/summary — by_setup is keyed by setup_type.
# These six always appear (zeros when empty). ob_fvg is omitted (not in enum).
# product_key strings are the PM/DE lock (do not invent Setup 4–6 names).
PERFORMANCE_SETUP_TYPES: tuple[str, ...] = (
    "sweep_reclaim",
    "fvg_entry",
    "po3_judas",
    "mss_break",
    "order_block",
    "sweep_mss",
)
PERFORMANCE_BY_SETUP_KEYS: tuple[str, ...] = PERFORMANCE_SETUP_TYPES

SETUP_TYPE_TO_PRODUCT: dict[str, str] = {
    "sweep_reclaim": "1_liquidity_sweep_vwap_reclaim",
    "fvg_entry": "2_fvg_mitigation_vwap",
    "po3_judas": "3_po3_asia_range_sweep",
    "mss_break": "4_pending_user_confirm",
    "order_block": "5_pending_user_confirm",
    "sweep_mss": "6_pending_user_confirm",
}
PRODUCT_KEYS: tuple[str, ...] = tuple(SETUP_TYPE_TO_PRODUCT[k] for k in PERFORMANCE_BY_SETUP_KEYS)
PRODUCT_TO_SETUP_TYPE: dict[str, str] = {v: k for k, v in SETUP_TYPE_TO_PRODUCT.items()}

# Setup-specific risk floors (validate). Conviction is 0–100; compare to confidence×100.
SETUP_MIN_RR: dict[str, float] = {
    "sweep_reclaim": 2.0,
    "fvg_entry": 1.5,
    "po3_judas": 1.5,
    "sd_extension_fade": 1.5,
    "vwap_pullback_cont": 2.0,
    "avwap_ob_confluence": 2.0,
}
SETUP_MIN_CONVICTION: dict[str, int] = {
    "sweep_reclaim": 60,
    "fvg_entry": 60,
    "po3_judas": 60,
    "sd_extension_fade": 60,
    "vwap_pullback_cont": 60,
    "avwap_ob_confluence": 70,
}
NEWS_SKIP_SETUP_TYPES: frozenset[str] = frozenset({"sd_extension_fade"})
NEWS_SKIP_MINUTES: int = 15

SETUP_TYPE_NOTES: dict[str, str] = {
    "sweep_reclaim": "Setup 1 — Liquidity sweep + VWAP reclaim.",
    "fvg_entry": "Setup 2 — Fair-value gap at VWAP / HVN.",
    "po3_judas": "Setup 3 — Power of Three / Judas swing.",
    "sd_extension_fade": "Setup 4 — SD extension fade (2σ/3σ → session VWAP).",
    "vwap_pullback_cont": "Setup 5 — VWAP / 1σ pullback continuation.",
    "avwap_ob_confluence": "Setup 6 — Anchored VWAP + HTF order-block confluence.",
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


def product_key_for(setup_type: str) -> str | None:
    name = setup_type.value if hasattr(setup_type, "value") else str(setup_type)
    return SETUP_TYPE_TO_PRODUCT.get(name)


def setup_name(setup_type: object) -> str:
    return setup_type.value if hasattr(setup_type, "value") else str(setup_type)


def min_rr_for(setup_type: object) -> float:
    return SETUP_MIN_RR.get(setup_name(setup_type), 1.5)


def min_conviction_for(setup_type: object) -> int:
    return SETUP_MIN_CONVICTION.get(setup_name(setup_type), 60)


def is_known_setup(setup_type: str) -> bool:
    return setup_type in SETUP_TYPES
