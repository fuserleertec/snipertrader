"""In-memory paper book for the 2-week no-live-trading gate.

Opens a virtual position when a signal is published after risk approval.
Closes on lifecycle TP/SL from the continuous DE **1m/5m** bar feed
(Kafka ``ohlcv_bars``, ``WS /v1/ws/ohlcv``, ``GET /v1/ohlcv``). Not 15m
``universe/top`` or dashboard snapshots. No broker. ``live_trading`` is
always ``False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from typing import Any

from sniper_quant.models import Side, SignalStatus, StoredSignal

DAY_MS = 86_400_000
GATE_DAYS = 14


def _env_ms(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _iso(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _account_body(data: dict[str, Any]) -> dict[str, Any]:
    """Accept GET /paper/account or a ``{meta, account}`` bundle."""
    if not isinstance(data, dict):
        raise TypeError("paper snapshot must be a dict")
    inner = data.get("account")
    if isinstance(inner, dict) and any(
        key in inner for key in ("closed", "positions", "cash", "starting_equity")
    ):
        return inner
    return data


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def paper_position_from_dict(raw: dict[str, Any]) -> PaperPosition | None:
    if not isinstance(raw, dict):
        return None
    signal_id = raw.get("signal_id")
    if not signal_id:
        return None
    entry = raw.get("entry")
    if entry is None:
        return None
    opened = raw.get("opened_ts_ms")
    return PaperPosition(
        signal_id=str(signal_id),
        symbol=str(raw.get("symbol") or ""),
        setup_type=str(raw.get("setup_type") or ""),
        side=str(raw.get("side") or "long"),
        size=float(raw.get("size") or 0.0),
        entry=float(entry),
        stop=_opt_float(raw.get("stop")),
        target=_opt_float(raw.get("target")),
        opened_ts_ms=int(opened) if opened is not None else 0,
        status=str(raw.get("status") or "OPEN"),
        exit_price=_opt_float(raw.get("exit_price")),
        realized_pnl=_opt_float(raw.get("realized_pnl")),
        realized_r=_opt_float(raw.get("realized_r")),
        closed_ts_ms=_opt_int(raw.get("closed_ts_ms")),
    )


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

    def start_gate(
        self,
        *,
        now_ms: int | None = None,
        days: int = GATE_DAYS,
        keep_existing: bool = False,
    ) -> None:
        """Stamp the 14-day paper clock. Never enables live trading.

        If both ``PAPER_GATE_STARTED_AT_MS`` and ``PAPER_GATE_ENDS_AT_MS`` are
        set, restore that window (host cutover; env always wins). Else if
        ``keep_existing`` and a window is already stamped (snapshot hydrate),
        leave it. Otherwise ``now + 14d``.
        """
        started = _env_ms("PAPER_GATE_STARTED_AT_MS")
        ends = _env_ms("PAPER_GATE_ENDS_AT_MS")
        if started is not None and ends is not None:
            self.gate_started_at_ms = started
            self.gate_ends_at_ms = ends
            return
        if (
            keep_existing
            and self.gate_started_at_ms is not None
            and self.gate_ends_at_ms is not None
        ):
            return
        now = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
        self.gate_started_at_ms = now
        self.gate_ends_at_ms = now + days * DAY_MS

    def load_snapshot(self, data: dict[str, Any]) -> None:
        """Rebuild the in-memory book from a paper account snapshot.

        Accepts ``GET /paper/account`` JSON or a ``{meta, account}`` bundle.
        Never sets ``live_trading`` true. Gate fields restore from the
        snapshot only when ``PAPER_GATE_*`` env is not fully set.
        """
        acct = _account_body(data)
        starting = acct.get("starting_equity")
        if starting is not None:
            self.starting_equity = float(starting)
        cash = acct.get("cash")
        if cash is not None:
            self.cash = float(cash)
        else:
            self.cash = self.starting_equity
        self.positions.clear()
        self.closed.clear()
        raw_positions = acct.get("positions") or []
        if isinstance(raw_positions, dict):
            raw_positions = list(raw_positions.values())
        for raw in raw_positions:
            pos = paper_position_from_dict(raw)
            if pos is not None:
                self.positions[pos.signal_id] = pos
        for raw in acct.get("closed") or []:
            pos = paper_position_from_dict(raw)
            if pos is not None:
                self.closed.append(pos)
        env_started = _env_ms("PAPER_GATE_STARTED_AT_MS")
        env_ends = _env_ms("PAPER_GATE_ENDS_AT_MS")
        if env_started is None or env_ends is None:
            started = acct.get("gate_started_at_ms")
            ends = acct.get("gate_ends_at_ms")
            if started is not None:
                self.gate_started_at_ms = int(started)
            if ends is not None:
                self.gate_ends_at_ms = int(ends)

    def from_snapshot(self, data: dict[str, Any]) -> "PaperEngine":
        """Alias for :meth:`load_snapshot`. Returns ``self``."""
        self.load_snapshot(data)
        return self

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
            if row.id not in self.positions:
                self.open_from_signal(row)
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
