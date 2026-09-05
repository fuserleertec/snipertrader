"""Canonical six-setup key map for Performance Snapshot.

Project Manager lock (Phase 3). These six ``by_setup`` keys are **frozen**.
Rename a key **here only** — never scatter string literals across API /
Kafka / Redis writers.

``GET /performance/summary`` always returns exactly ``SETUP_KEYS`` (zeros OK).
"""

from __future__ import annotations

from typing import Final

SETUP_1_LIQUIDITY_SWEEP_VWAP_RECLAIM: Final = "1_liquidity_sweep_vwap_reclaim"
SETUP_2_FVG_MITIGATION_VWAP: Final = "2_fvg_mitigation_vwap"
SETUP_3_PO3_ASIA_RANGE_SWEEP: Final = "3_po3_asia_range_sweep"
SETUP_4_SD_EXTENSION_FADE: Final = "4_sd_extension_fade"
SETUP_5_VWAP_PULLBACK_CONT: Final = "5_vwap_pullback_cont"
SETUP_6_AVWAP_OB_CONFLUENCE: Final = "6_avwap_ob_confluence"

SETUP_KEYS: Final[tuple[str, ...]] = (
    SETUP_1_LIQUIDITY_SWEEP_VWAP_RECLAIM,
    SETUP_2_FVG_MITIGATION_VWAP,
    SETUP_3_PO3_ASIA_RANGE_SWEEP,
    SETUP_4_SD_EXTENSION_FADE,
    SETUP_5_VWAP_PULLBACK_CONT,
    SETUP_6_AVWAP_OB_CONFLUENCE,
)

# Quant / ML ``setup_type`` aliases → canonical ``by_setup`` key.
SETUP_TYPE_ALIASES: Final[dict[str, str]] = {
    "po3_judas": SETUP_3_PO3_ASIA_RANGE_SWEEP,
    "sd_extension_fade": SETUP_4_SD_EXTENSION_FADE,
    "vwap_pullback_cont": SETUP_5_VWAP_PULLBACK_CONT,
    "avwap_ob_confluence": SETUP_6_AVWAP_OB_CONFLUENCE,
    "1": SETUP_1_LIQUIDITY_SWEEP_VWAP_RECLAIM,
    "2": SETUP_2_FVG_MITIGATION_VWAP,
    "3": SETUP_3_PO3_ASIA_RANGE_SWEEP,
    "4": SETUP_4_SD_EXTENSION_FADE,
    "5": SETUP_5_VWAP_PULLBACK_CONT,
    "6": SETUP_6_AVWAP_OB_CONFLUENCE,
}

SETUP_STATS_FIELDS: Final[tuple[str, ...]] = ("win_rate", "average_rr", "signals")


class UnknownSetupError(ValueError):
    """Raised when a writer sends a setup key that is not in the map."""


def empty_setup_stats() -> dict[str, float | int]:
    return {"win_rate": 0.0, "average_rr": 0.0, "signals": 0}


def empty_by_setup() -> dict[str, dict[str, float | int]]:
    return {key: empty_setup_stats() for key in SETUP_KEYS}


def resolve_setup_key(raw: str | None) -> str:
    """Map a wire ``setup`` / ``setup_type`` onto a canonical by_setup key."""
    if raw is None or not str(raw).strip():
        raise UnknownSetupError("setup is required")
    token = str(raw).strip()
    if token in SETUP_KEYS:
        return token
    alias = SETUP_TYPE_ALIASES.get(token) or SETUP_TYPE_ALIASES.get(token.lower())
    if alias is not None:
        return alias
    raise UnknownSetupError(
        f"unknown setup {token!r}; expected one of {list(SETUP_KEYS)} "
        f"or aliases {sorted(SETUP_TYPE_ALIASES)}"
    )


def is_setup_key(raw: str) -> bool:
    return raw in SETUP_KEYS
