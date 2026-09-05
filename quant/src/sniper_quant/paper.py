"""In-memory paper book for the 2-week no-live-trading gate.

Opens a virtual position when a signal is published after risk approval.
Closes on lifecycle TP/SL. No broker, no live orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sniper_quant.models import Side, SignalStatus, StoredSignal


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

    def reset(self, equity: float | None = None) -> None:
        if equity is not None:
            self.starting_equity = equity
        self.cash = self.starting_equity
        self.positions.clear()
        self.closed.clear()

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
        return {
            "starting_equity": self.starting_equity,
            "equity": round(self.equity, 6),
            "cash": round(self.cash, 6),
            "realized_pnl": round(self.realized_pnl, 6),
            "open_positions": len(self.positions),
            "closed_trades": len(self.closed),
            "positions": [p.__dict__.copy() for p in self.positions.values()],
            "closed": [p.__dict__.copy() for p in self.closed],
            "live_trading": False,
            "gate": "2-week paper only",
        }
