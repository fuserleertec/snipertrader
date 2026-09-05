"""Placeholder enum for the six USME/ICT setups.

ML Researchers have not locked pattern names in-repo yet. The backtester and
risk engine treat ``setup_type`` as a pluggable string — these constants are
the documented Phase 1 vocabulary, not a hard reject list.
"""

from __future__ import annotations

# Six USME / ICT setup names used across product pages (sweep, FVG, OB,
# CHoCH/BOS, Silver Bullet, OTE). Replace when ML publishes the official list.
SETUP_TYPES: tuple[str, ...] = (
    "liquidity_sweep",
    "fvg_entry",
    "order_block",
    "choch_bos",
    "silver_bullet",
    "ote",
)

SETUP_TYPE_NOTES: dict[str, str] = {
    "liquidity_sweep": "Liquidity sweep + reclaim (stop-run).",
    "fvg_entry": "Fair-value gap entry in the direction of bias.",
    "order_block": "Institutional order-block reaction.",
    "choch_bos": "Change of character / break of structure.",
    "silver_bullet": "ICT Silver Bullet killzone window.",
    "ote": "Optimal trade entry (discount/premium OTE).",
}


def is_known_setup(setup_type: str) -> bool:
    return setup_type in SETUP_TYPES
