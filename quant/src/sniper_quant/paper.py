"""In-memory paper book for the 2-week no-live-trading gate.

Opens a virtual position when a signal is published after risk approval.
Closes on lifecycle TP/SL. No broker, no live orders. ``live_trading`` is
always ``False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sniper_quant.models import Side, SignalStatus, StoredSignal

DAY_MS = 86_400_000
GATE_DAYS = 14


def _iso(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class PaperPosition:
    signal_id: str
    symbol: str
    setup_type: str
    side: str
    size: float
    entry: float
    stop: float | None
    target: float | None
    opened_ts_ms: int
    status: str = "OPEN"
    exit_price: float | None = None
    realized_pnl: float | None = None
    realized_r: float | None = None
    closed_ts_ms: int | None = None


@dataclass
class PaperEngine:
    starting_equity: float = 100_000.0
    cash: float = 100_000.0
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    closed: list[PaperPosition] = field(default_factory=list)
    gate_started_at_ms: int | None = None
    gate_ends_at_ms: int | None = None

    def reset(self, equity: float | None = None, *, clear_gate: bool = False) -> None:
        if equity is not None:
            self.starting_equity = equity
        self.cash = self.starting_equity
        self.positions.clear()
        self.closed.clear()
        if clear_gate:
            self.gate_started_at_ms = None
            self.gate_ends_at_ms = None

    def start_gate(self, *, now_ms: int | None = None, days: int = GATE_DAYS) -> None:
        now = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
        self.gate_started_at_ms = now
        self.gate_ends_at_ms = now + days * DAY_MS

    def open_from_signal(self, row: StoredSignal) -> PaperPosition | None:
        if row.id in self.positions:
            return self.positions[row.id]
        if row.entry is None:
            return None
        size = float(row.position_size or 0.0)
        setup = row.setup_type.value if hasattr(row.setup_type, "value") else str(row.setup_type)
        side = row.side.value if hasattr(row.side, "value") else str(row.side)
        pos = PaperPosition(
            signal_id=row.id,
            symbol=row.symbol,
            setup_type=setup,
            side=side,
            size=size,
            entry=row.entry,
            stop=row.stop,
            target=row.target,
            opened_ts_ms=row.ts_ms,
        )
        notional = size * row.entry
        self.cash -= notional
        self.positions[row.id] = pos
        return pos

    def close_from_signal(self, row: StoredSignal) -> PaperPosition | None:
        pos = self.positions.pop(row.id, None)
        if pos is None:
            return None
        exit_px = row.exit_px if row.exit_px is not None else row.entry or pos.entry
        side = Side(pos.side)
        if side is Side.LONG:
            pnl = (exit_px - pos.entry) * pos.size
        else:
            pnl = (pos.entry - exit_px) * pos.size
        pos.status = row.status.value if hasattr(row.status, "value") else str(row.status)
        pos.exit_price = exit_px
        pos.realized_pnl = pnl
        pos.realized_r = row.r_multiple
        pos.closed_ts_ms = row.closed_ts_ms
        self.cash += pos.size * exit_px
        self.closed.append(pos)
        return pos

    def mark_signal(self, row: StoredSignal) -> None:
        if row.status is SignalStatus.ACTIVE:
            self.open_from_signal(row)
        elif row.status in {SignalStatus.TP_HIT, SignalStatus.SL_HIT, SignalStatus.CANCELLED}:
            if row.id in self.positions:
                self.close_from_signal(row)

    @property
    def realized_pnl(self) -> float:
        return sum(p.realized_pnl or 0.0 for p in self.closed)

    @property
    def equity(self) -> float:
        open_mtm = sum(p.size * p.entry for p in self.positions.values())
        return self.cash + open_mtm

    def snapshot(self) -> dict[str, Any]:
        closed = self.closed
        n = len(closed)
        wins = [
            p
            for p in closed
            if p.status == "TP_HIT" or (p.realized_r is not None and p.realized_r > 0)
        ]
        rs = [p.realized_r for p in closed if p.realized_r is not None]
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        remaining = None
        if self.gate_ends_at_ms is not None:
            remaining = max(0.0, (self.gate_ends_at_ms - now_ms) / DAY_MS)
        return {
            "starting_equity": self.starting_equity,
            "equity": round(self.equity, 6),
            "cash": round(self.cash, 6),
            "realized_pnl": round(self.realized_pnl, 6),
            "open_positions": len(self.positions),
            "closed_trades": n,
            "win_rate": (len(wins) / n) if n else 0.0,
            "average_rr": (sum(rs) / len(rs)) if rs else 0.0,
            "positions": [p.__dict__.copy() for p in self.positions.values()],
            "closed": [p.__dict__.copy() for p in self.closed],
            "live_trading": False,
            "gate": "2-week paper only",
            "gate_started_at_ms": self.gate_started_at_ms,
            "gate_ends_at_ms": self.gate_ends_at_ms,
            "gate_started_at_utc": _iso(self.gate_started_at_ms),
            "gate_ends_at_utc": _iso(self.gate_ends_at_ms),
            "gate_days_remaining": remaining,
        }
