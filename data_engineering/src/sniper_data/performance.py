"""Performance Snapshot store — Redis / in-memory outcomes → GET envelope.

Quant / ML write resolved signal outcomes via ``POST /performance/outcomes``
or Kafka topic ``performance_outcomes``. This module never filters risk;
risk stays at Quant ``POST /risk/validate`` on the publisher boundary.

Redis key: ``perf:outcomes`` (JSON list, newest first, capped).
"""

from __future__ import annotations

import math
import statistics
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from sniper_data.bus.redis_store import StateStore
from sniper_data.setups import (
    SETUP_KEYS,
    UnknownSetupError,
    empty_by_setup,
    empty_setup_stats,
    resolve_setup_key,
)

REDIS_OUTCOMES_KEY = "perf:outcomes"
MAX_OUTCOMES = 10_000
MS_PER_DAY = 86_400_000
MS_PER_WEEK = 7 * MS_PER_DAY


class SignalOutcome(BaseModel):
    """Ingestion record. ``setup`` is a canonical key or a ``setup_type`` alias."""

    setup: str | None = None
    setup_type: str | None = None
    won: bool
    rr: float
    ts_ms: int | None = None
    signal_id: str | None = None
    symbol: str | None = None

    def canonical_setup(self) -> str:
        return resolve_setup_key(self.setup or self.setup_type)

    def event_ts_ms(self) -> int:
        return int(self.ts_ms) if self.ts_ms is not None else utc_now_ms()


class StoredOutcome(BaseModel):
    setup: str
    won: bool
    rr: float
    ts_ms: int
    signal_id: str | None = None
    symbol: str | None = None


class SetupStats(BaseModel):
    win_rate: float = 0.0
    average_rr: float = 0.0
    signals: int = 0


class OverallStats(BaseModel):
    win_rate: float = 0.0
    average_rr: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    signals_today: int = 0
    signals_week: int = 0


class PerformanceSummary(BaseModel):
    timestamp: int
    overall: OverallStats = Field(default_factory=OverallStats)
    by_setup: dict[str, SetupStats] = Field(default_factory=lambda: {
        k: SetupStats() for k in SETUP_KEYS
    })


def utc_now_ms() -> int:
    return int(time.time() * 1000)


def _day_start_utc_ms(ts_ms: int) -> int:
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    start = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000)


def _signed_rr(won: bool, rr: float) -> float:
    mag = abs(float(rr))
    return mag if won else -mag


def _sharpe(signed: list[float]) -> float:
    if len(signed) < 2:
        return 0.0
    stdev = statistics.pstdev(signed)
    if stdev <= 0:
        return 0.0
    return float(statistics.fmean(signed) / stdev)


def _max_drawdown_pct(signed: list[float]) -> float:
    """Peak-to-trough of a cumulative-R equity curve starting at 0, as percent of peak."""
    if not signed:
        return 0.0
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in signed:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    if peak <= 0:
        # All losing / flat — report absolute R-drawdown as a percent of 1R.
        return float(max_dd * 100.0) if max_dd else 0.0
    return float(max_dd / peak * 100.0)


def _setup_stats(rows: list[StoredOutcome]) -> SetupStats:
    if not rows:
        return SetupStats()
    wins = sum(1 for r in rows if r.won)
    return SetupStats(
        win_rate=wins / len(rows),
        average_rr=float(statistics.fmean(abs(r.rr) for r in rows)),
        signals=len(rows),
    )


def compute_summary(
    rows: list[StoredOutcome],
    *,
    now_ms: int | None = None,
    setup_filter: str | None = None,
) -> dict[str, Any]:
    now = now_ms if now_ms is not None else utc_now_ms()
    day0 = _day_start_utc_ms(now)
    week0 = now - MS_PER_WEEK

    by_setup = empty_by_setup()
    grouped: dict[str, list[StoredOutcome]] = {k: [] for k in SETUP_KEYS}
    for row in rows:
        if row.setup in grouped:
            grouped[row.setup].append(row)
    for key, items in grouped.items():
        stats = _setup_stats(items)
        by_setup[key] = {
            "win_rate": stats.win_rate,
            "average_rr": stats.average_rr,
            "signals": stats.signals,
        }

    universe = rows
    if setup_filter is not None:
        key = resolve_setup_key(setup_filter)
        universe = [r for r in rows if r.setup == key]

    signed = [_signed_rr(r.won, r.rr) for r in universe]
    wins = sum(1 for r in universe if r.won)
    overall = {
        "win_rate": (wins / len(universe)) if universe else 0.0,
        "average_rr": float(statistics.fmean(abs(r.rr) for r in universe)) if universe else 0.0,
        "sharpe_ratio": _sharpe(signed),
        "max_drawdown_pct": _max_drawdown_pct(signed),
        "signals_today": sum(1 for r in universe if r.ts_ms >= day0),
        "signals_week": sum(1 for r in universe if r.ts_ms >= week0),
    }
    return {
        "timestamp": now,
        "overall": overall,
        "by_setup": by_setup,
    }


def _parse_row(raw: Any) -> StoredOutcome | None:
    if not isinstance(raw, dict):
        return None
    try:
        setup = resolve_setup_key(raw.get("setup") or raw.get("setup_type"))
        return StoredOutcome(
            setup=setup,
            won=bool(raw["won"]),
            rr=float(raw["rr"]),
            ts_ms=int(raw.get("ts_ms") or utc_now_ms()),
            signal_id=raw.get("signal_id"),
            symbol=raw.get("symbol"),
        )
    except (UnknownSetupError, KeyError, TypeError, ValueError):
        return None


class PerformanceStore:
    def __init__(self, store: StateStore, *, max_outcomes: int = MAX_OUTCOMES) -> None:
        self.store = store
        self.max_outcomes = max_outcomes

    async def load(self) -> list[StoredOutcome]:
        raw = await self.store.get(REDIS_OUTCOMES_KEY)
        if not raw:
            return []
        if isinstance(raw, list):
            items = raw
        else:
            return []
        out: list[StoredOutcome] = []
        for item in items:
            parsed = _parse_row(item)
            if parsed is not None:
                out.append(parsed)
        return out

    async def record(self, outcome: SignalOutcome) -> StoredOutcome:
        stored = StoredOutcome(
            setup=outcome.canonical_setup(),
            won=outcome.won,
            rr=float(outcome.rr),
            ts_ms=outcome.event_ts_ms(),
            signal_id=outcome.signal_id,
            symbol=outcome.symbol,
        )
        rows = await self.load()
        payload = [stored.model_dump(mode="json"), *[r.model_dump(mode="json") for r in rows]]
        await self.store.set(REDIS_OUTCOMES_KEY, payload[: self.max_outcomes])
        return stored

    async def record_many(self, outcomes: list[SignalOutcome]) -> list[StoredOutcome]:
        stored = [
            StoredOutcome(
                setup=o.canonical_setup(),
                won=o.won,
                rr=float(o.rr),
                ts_ms=o.event_ts_ms(),
                signal_id=o.signal_id,
                symbol=o.symbol,
            )
            for o in outcomes
        ]
        rows = await self.load()
        payload = [
            *[s.model_dump(mode="json") for s in stored],
            *[r.model_dump(mode="json") for r in rows],
        ]
        await self.store.set(REDIS_OUTCOMES_KEY, payload[: self.max_outcomes])
        return stored

    async def summary(
        self,
        *,
        setup: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        rows = await self.load()
        return compute_summary(rows, now_ms=now_ms, setup_filter=setup)


def empty_summary(now_ms: int | None = None) -> dict[str, Any]:
    return compute_summary([], now_ms=now_ms)
