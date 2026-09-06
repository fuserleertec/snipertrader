"""Paper Signal History (P2) — outcome join points.

Published ``setup_signals`` stay ``ACTIVE`` until a paper fill arrives.
This module is the stub join: attach ``win`` / ``loss`` / ``unresolved``
/ ``cancelled`` per symbol + setup without touching the live book.

Quant paper fills plug in later via ``PaperFillSource`` (id join, then
``symbol + ts_ms + setup_type + side``). Inactive setups are never in
the published set — see ``activity.must_skip_symbol``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

PaperOutcome = Literal["win", "loss", "unresolved", "cancelled"]

STATUS_TO_OUTCOME: dict[str, PaperOutcome] = {
    "TP_HIT": "win",
    "SL_HIT": "loss",
    "CANCELLED": "cancelled",
    "ACTIVE": "unresolved",
}


class PaperFillSource(Protocol):
    """Quant paper-book join. Return ``win`` / ``loss`` / None (unresolved)."""

    def outcome_for(self, signal: dict[str, Any]) -> PaperOutcome | None: ...


@dataclass
class StaticFillSource:
    """Test / paper stub: ``{signal_id: outcome}`` or a callable."""

    by_id: dict[str, PaperOutcome] | None = None
    hook: Any = None

    def outcome_for(self, signal: dict[str, Any]) -> PaperOutcome | None:
        if self.hook is not None:
            return self.hook(signal)
        if self.by_id is None:
            return None
        sid = signal.get("id")
        if sid and sid in self.by_id:
            return self.by_id[sid]
        return None


def outcome_of(signal: dict[str, Any], fills: PaperFillSource | None = None) -> PaperOutcome:
    if fills is not None:
        joined = fills.outcome_for(signal)
        if joined is not None:
            return joined
    status = signal.get("status") or "ACTIVE"
    return STATUS_TO_OUTCOME.get(str(status), "unresolved")


def history_row(signal: dict[str, Any], *, outcome: PaperOutcome) -> dict[str, Any]:
    return {
        "id": signal.get("id"),
        "symbol": signal.get("symbol"),
        "setup_type": signal.get("setup_type"),
        "side": signal.get("side"),
        "ts_ms": signal.get("ts_ms"),
        "entry": signal.get("entry"),
        "stop": signal.get("stop"),
        "target": signal.get("target"),
        "status": signal.get("status"),
        "outcome": outcome,
        "ensemble_score": signal.get("ensemble_score"),
        "category": signal.get("category") or signal.get("asset_class"),
        "live_trading": False,
    }


def join_paper_history(
    signals: list[dict[str, Any]],
    fills: PaperFillSource | None = None,
) -> list[dict[str, Any]]:
    rows = [history_row(s, outcome=outcome_of(s, fills)) for s in signals]
    rows.sort(key=lambda r: int(r.get("ts_ms") or 0), reverse=True)
    return rows


def history_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for r in rows if r.get("outcome") == "win")
    losses = sum(1 for r in rows if r.get("outcome") == "loss")
    cancelled = sum(1 for r in rows if r.get("outcome") == "cancelled")
    unresolved = sum(1 for r in rows if r.get("outcome") == "unresolved")
    resolved = wins + losses
    by_symbol: dict[str, dict[str, int]] = {}
    for row in rows:
        sym = str(row.get("symbol") or "?")
        bucket = by_symbol.setdefault(sym, {"win": 0, "loss": 0, "unresolved": 0, "cancelled": 0})
        bucket[str(row.get("outcome") or "unresolved")] = bucket.get(str(row.get("outcome") or "unresolved"), 0) + 1
    return {
        "published": len(rows),
        "wins": wins,
        "losses": losses,
        "cancelled": cancelled,
        "unresolved": unresolved,
        "accuracy": (wins / resolved) if resolved else None,
        "by_symbol": by_symbol,
        "live_trading": False,
    }
