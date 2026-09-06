"""Skip / cancel when a symbol has no active DE levels (paper).

A symbol is **inactive** when there is no session book and no unmitigated
FVG / order-block / sweep zone. Mitigated-only zones do not count.

Reasons (logged, never published as ``setup_signals``):

* ``no_session_book``
* ``no_active_zones``
* ``mitigated_only``
* ``no_active_levels`` (none of the above books exist)

Uses landed DE key prefixes only: ``session:{symbol}:*``,
``fvg:{symbol}:*``, ``ob:{symbol}:*``, ``sweep:{symbol}:*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import FVGZone, OrderBlock, SweepEvent
from sniper_data.symbols import normalize_symbol

log = logging.getLogger(__name__)


@dataclass
class ActiveLevels:
    symbol: str
    has_session: bool = False
    active_fvgs: int = 0
    active_obs: int = 0
    active_sweeps: int = 0
    mitigated_only: bool = False
    session_keys: list[str] = field(default_factory=list)
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.has_session or self.has_unmitigated_zones

    @property
    def has_unmitigated_zones(self) -> bool:
        return (self.active_fvgs + self.active_obs + self.active_sweeps) > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ok": self.ok,
            "reason": self.reason,
            "has_session": self.has_session,
            "active_fvgs": self.active_fvgs,
            "active_obs": self.active_obs,
            "active_sweeps": self.active_sweeps,
            "mitigated_only": self.mitigated_only,
        }


def _mitigated(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, dict):
        return bool(raw.get("mitigated"))
    return bool(getattr(raw, "mitigated", False))


async def inspect_active_levels(store: StateStore, symbol: str) -> ActiveLevels:
    symbol = normalize_symbol(symbol)
    info = ActiveLevels(symbol=symbol)
    session_keys = await store.scan(f"session:{symbol}:*")
    info.session_keys = list(session_keys)
    info.has_session = bool(session_keys)

    zone_hits = 0
    mitigated_hits = 0
    for prefix, attr, model in (
        ("fvg", "active_fvgs", FVGZone),
        ("ob", "active_obs", OrderBlock),
        ("sweep", "active_sweeps", SweepEvent),
    ):
        keys = await store.scan(f"{prefix}:{symbol}:*")
        active = 0
        for key in keys:
            raw = await store.get(key)
            if raw is None:
                continue
            zone_hits += 1
            if _mitigated(raw):
                mitigated_hits += 1
                continue
            active += 1
        setattr(info, attr, active)

    info.mitigated_only = (
        zone_hits > 0
        and not info.has_unmitigated_zones
        and mitigated_hits == zone_hits
    )

    if info.ok:
        info.reason = None
    elif info.mitigated_only and not info.has_session:
        info.reason = "mitigated_only"
    elif not info.has_session and zone_hits == 0:
        info.reason = "no_active_levels"
    elif not info.has_unmitigated_zones:
        info.reason = "no_active_zones"
    else:
        info.reason = "no_active_levels"
    return info


async def must_skip_symbol(store: StateStore, symbol: str) -> tuple[bool, str | None, ActiveLevels]:
    info = await inspect_active_levels(store, symbol)
    if info.ok:
        return False, None, info
    reason = info.reason or "no_active_levels"
    log.info("setup skip inactive symbol=%s reason=%s levels=%s", symbol, reason, info.as_dict())
    return True, reason, info
