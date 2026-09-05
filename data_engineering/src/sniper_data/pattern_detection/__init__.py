"""ICT pattern detectors (ML Research Phase 1 / Rev. 1.1).

Consumes DE-normalized topics and Redis keys only. Publishes
``sweep_events``, ``fvg_zones``, ``mss_events``, ``order_block_zones``.
Uses landed models (``SweepEvent``, ``MssEvent``, ``OrderBlock``, ``FVGZone``)
and ``sniper_data.zones`` helpers — no field-name aliases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sniper_data.pattern_detection.engine import PatternEngine, PatternStats
    from sniper_data.pattern_detection.fvg import FVGDetector
    from sniper_data.pattern_detection.mss import DEFAULT_SWING_LOOKBACK, MSSDetector
    from sniper_data.pattern_detection.order_block import OrderBlockDetector
    from sniper_data.pattern_detection.sweep import SweepDetector

__all__ = [
    "DEFAULT_SWING_LOOKBACK",
    "FVGDetector",
    "MSSDetector",
    "OrderBlockDetector",
    "PatternEngine",
    "PatternStats",
    "SweepDetector",
]


def __getattr__(name: str) -> Any:
    if name in {"PatternEngine", "PatternStats"}:
        from sniper_data.pattern_detection.engine import PatternEngine, PatternStats

        return PatternEngine if name == "PatternEngine" else PatternStats
    if name == "FVGDetector":
        from sniper_data.pattern_detection.fvg import FVGDetector

        return FVGDetector
    if name in {"MSSDetector", "DEFAULT_SWING_LOOKBACK"}:
        from sniper_data.pattern_detection.mss import DEFAULT_SWING_LOOKBACK, MSSDetector

        return DEFAULT_SWING_LOOKBACK if name == "DEFAULT_SWING_LOOKBACK" else MSSDetector
    if name == "OrderBlockDetector":
        from sniper_data.pattern_detection.order_block import OrderBlockDetector

        return OrderBlockDetector
    if name == "SweepDetector":
        from sniper_data.pattern_detection.sweep import SweepDetector

        return SweepDetector
    raise AttributeError(name)
