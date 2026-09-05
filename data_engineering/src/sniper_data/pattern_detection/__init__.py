"""ICT pattern detectors (ML Research Phase 1 + Phase 2 anchor wiring).

Consumes DE-normalized topics and Redis keys only. Publishes
``sweep_events``, ``fvg_zones``, ``mss_events``, ``order_block_zones``,
and Phase 2 ``anchor_events`` (same JSON as ``POST /v1/anchors``).
Uses landed models — no field-name aliases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sniper_data.pattern_detection.anchors import (
        ANCHOR_TOPIC,
        post_anchor,
        publish_anchor,
        swing_to_registration,
        to_anchor_payload,
    )
    from sniper_data.pattern_detection.context import (
        get_active_kill_zone,
        get_avwap,
        get_kill_zone,
        get_latest_avwap,
        get_volume_profile,
        list_volume_profiles,
        subscribe_kill_zone_events,
    )
    from sniper_data.pattern_detection.engine import PatternEngine, PatternStats
    from sniper_data.pattern_detection.fvg import FVGDetector
    from sniper_data.pattern_detection.mss import DEFAULT_SWING_LOOKBACK, MSSDetector, SwingPoint
    from sniper_data.pattern_detection.order_block import OrderBlockDetector
    from sniper_data.pattern_detection.sweep import SweepDetector

__all__ = [
    "ANCHOR_TOPIC",
    "DEFAULT_SWING_LOOKBACK",
    "FVGDetector",
    "MSSDetector",
    "OrderBlockDetector",
    "PatternEngine",
    "PatternStats",
    "SweepDetector",
    "SwingPoint",
    "get_active_kill_zone",
    "get_avwap",
    "get_kill_zone",
    "get_latest_avwap",
    "get_volume_profile",
    "list_volume_profiles",
    "post_anchor",
    "publish_anchor",
    "subscribe_kill_zone_events",
    "swing_to_registration",
    "to_anchor_payload",
]


def __getattr__(name: str) -> Any:
    if name in {"PatternEngine", "PatternStats"}:
        from sniper_data.pattern_detection.engine import PatternEngine, PatternStats

        return PatternEngine if name == "PatternEngine" else PatternStats
    if name == "FVGDetector":
        from sniper_data.pattern_detection.fvg import FVGDetector

        return FVGDetector
    if name in {"MSSDetector", "DEFAULT_SWING_LOOKBACK", "SwingPoint"}:
        from sniper_data.pattern_detection.mss import DEFAULT_SWING_LOOKBACK, MSSDetector, SwingPoint

        return {"DEFAULT_SWING_LOOKBACK": DEFAULT_SWING_LOOKBACK, "MSSDetector": MSSDetector, "SwingPoint": SwingPoint}[
            name
        ]
    if name == "OrderBlockDetector":
        from sniper_data.pattern_detection.order_block import OrderBlockDetector

        return OrderBlockDetector
    if name == "SweepDetector":
        from sniper_data.pattern_detection.sweep import SweepDetector

        return SweepDetector
    if name in {
        "ANCHOR_TOPIC",
        "post_anchor",
        "publish_anchor",
        "swing_to_registration",
        "to_anchor_payload",
    }:
        from sniper_data.pattern_detection import anchors as _anchors

        return getattr(_anchors, name)
    if name in {
        "get_active_kill_zone",
        "get_avwap",
        "get_kill_zone",
        "get_latest_avwap",
        "get_volume_profile",
        "list_volume_profiles",
        "subscribe_kill_zone_events",
    }:
        from sniper_data.pattern_detection import context as _context

        return getattr(_context, name)
    raise AttributeError(name)
