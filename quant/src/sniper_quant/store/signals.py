"""Signal lifecycle store — Timescale ``signals`` or in-memory."""

from __future__ import annotations

import json
import time
from typing import Protocol

from sniper_quant.models import AssetClass, Side, SignalStatus, StoredSignal


def _now_ms() -> int:
    return int(time.time() * 1000)


class SignalStore(Protocol):
    async def insert(self, signal: StoredSignal) -> StoredSignal: ...

    async def get(self, signal_id: str) -> StoredSignal | None: ...

    async def list(
        self,
        *,
        symbol: str | None = None,
        status: SignalStatus | str | None = None,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 200,
    ) -> list[StoredSignal]: ...

    async def update_status(
        self,
        signal_id: str,
        status: SignalStatus,
        *,
        closed_ts_ms: int | None = None,
    ) -> StoredSignal | None: ...

    async def active(self) -> list[StoredSignal]: ...

    async def close(self) -> None: ...


class InMemorySignalStore:
    def __init__(self) -> None:
        self.rows: dict[str, StoredSignal] = {}

    async def insert(self, signal: StoredSignal) -> StoredSignal:
        self.rows[signal.id] = signal
        return signal

    async def get(self, signal_id: str) -> StoredSignal | None:
        return self.rows.get(signal_id)

    async def list(
        self,
        *,
        symbol: str | None = None,
        status: SignalStatus | str | None = None,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 200,
    ) -> list[StoredSignal]:
        rows = list(self.rows.values())
        if symbol:
            rows = [r for r in rows if r.symbol == symbol.upper().replace("-", "")]
        if status:
            st = SignalStatus(status)
            rows = [r for r in rows if r.status is st]
        if from_ms is not None:
            rows = [r for r in rows if r.ts_ms >= from_ms]
        if to_ms is not None:
            rows = [r for r in rows if r.ts_ms <= to_ms]
        rows.sort(key=lambda r: r.ts_ms, reverse=True)
        return rows[:limit]

    async def update_status(
        self,
        signal_id: str,
        status: SignalStatus,
        *,
        closed_ts_ms: int | None = None,
    ) -> StoredSignal | None:
        row = self.rows.get(signal_id)
        if row is None:
            return None
        terminal = status in {SignalStatus.TP_HIT, SignalStatus.SL_HIT, SignalStatus.CANCELLED}
        updated = row.model_copy(
            update={
                "status": status,
                "closed_ts_ms": closed_ts_ms or (_now_ms() if terminal else row.closed_ts_ms),
            }
        )
        self.rows[signal_id] = updated
        return updated

    async def active(self) -> list[StoredSignal]:
        return [r for r in self.rows.values() if r.status is SignalStatus.ACTIVE]

    async def close(self) -> None:
        return None


_INSERT_SQL = """
INSERT INTO signals (
  ts, id, schema_version, symbol, asset_class, setup_type, side,
  confidence, ref_vwap, ref_session, entry, stop_px, target,
  timeframe, trigger_event_ids, session_type,
  position_size, status, closed_ts
) VALUES (
  to_timestamp($1 / 1000.0), $2, $3, $4, $5, $6, $7,
  $8, $9, $10, $11, $12, $13,
  $14, $15, $16,
  $17, $18,
  CASE WHEN $19::BIGINT IS NULL THEN NULL ELSE to_timestamp($19 / 1000.0) END
)
ON CONFLICT (id, ts) DO UPDATE SET
  status = EXCLUDED.status,
  entry = EXCLUDED.entry,
  stop_px = EXCLUDED.stop_px,
  target = EXCLUDED.target,
  timeframe = EXCLUDED.timeframe,
  trigger_event_ids = EXCLUDED.trigger_event_ids,
  session_type = EXCLUDED.session_type,
  position_size = EXCLUDED.position_size,
  updated_at = NOW(),
  closed_ts = EXCLUDED.closed_ts
"""


def _row_to_signal(r) -> StoredSignal:
    closed = r["closed_ts"]
    return StoredSignal(
        schema_version=r["schema_version"],
        id=r["id"],
        symbol=r["symbol"],
        asset_class=AssetClass(r["asset_class"]),
        setup_type=r["setup_type"],
        side=Side(r["side"]),
        confidence=r["confidence"],
        ref_vwap=r["ref_vwap"],
        ref_session=r["ref_session"],
        ts_ms=int(r["ts_ms"]),
        entry=r["entry"],
        stop=r["stop_px"],
        target=r["target"],
        timeframe=r["timeframe"],
        trigger_event_ids=_decode_ids(r["trigger_event_ids"]),
        session_type=r["session_type"],
        position_size=r["position_size"],
        status=SignalStatus(r["status"]),
        closed_ts_ms=int(closed.timestamp() * 1000) if closed is not None else None,
    )


def _decode_ids(raw) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [str(raw)]
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return [str(parsed)]


class TimescaleSignalStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool = None

    async def start(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)

    async def _conn(self):
        if self._pool is None:
            await self.start()
        assert self._pool is not None
        return self._pool

    async def insert(self, signal: StoredSignal) -> StoredSignal:
        pool = await self._conn()
        async with pool.acquire() as conn:
            await conn.execute(
                _INSERT_SQL,
                signal.ts_ms,
                signal.id,
                signal.schema_version,
                signal.symbol,
                signal.asset_class.value,
                signal.setup_type,
                signal.side.value,
                signal.confidence,
                signal.ref_vwap,
                signal.ref_session,
                signal.entry,
                signal.stop,
                signal.target,
                str(signal.timeframe) if signal.timeframe is not None else None,
                json.dumps(list(signal.trigger_event_ids or [])),
                str(signal.session_type) if signal.session_type is not None else None,
                signal.position_size,
                signal.status.value,
                signal.closed_ts_ms,
            )
        return signal

    async def get(self, signal_id: str) -> StoredSignal | None:
        pool = await self._conn()
        sql = """
        SELECT EXTRACT(EPOCH FROM ts) * 1000 AS ts_ms, id, schema_version,
               symbol, asset_class, setup_type, side, confidence, ref_vwap,
               ref_session, entry, stop_px, target, timeframe, trigger_event_ids,
               session_type, position_size, status, closed_ts
        FROM signals WHERE id = $1
        ORDER BY ts DESC LIMIT 1
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, signal_id)
        return _row_to_signal(row) if row else None

    async def list(
        self,
        *,
        symbol: str | None = None,
        status: SignalStatus | str | None = None,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 200,
    ) -> list[StoredSignal]:
        pool = await self._conn()
        st = SignalStatus(status).value if status else None
        sql = """
        SELECT EXTRACT(EPOCH FROM ts) * 1000 AS ts_ms, id, schema_version,
               symbol, asset_class, setup_type, side, confidence, ref_vwap,
               ref_session, entry, stop_px, target, timeframe, trigger_event_ids,
               session_type, position_size, status, closed_ts
        FROM signals
        WHERE ($1::TEXT IS NULL OR symbol = $1)
          AND ($2::TEXT IS NULL OR status = $2)
          AND ($3::BIGINT IS NULL OR EXTRACT(EPOCH FROM ts) * 1000 >= $3)
          AND ($4::BIGINT IS NULL OR EXTRACT(EPOCH FROM ts) * 1000 <= $4)
        ORDER BY ts DESC
        LIMIT $5
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, symbol, st, from_ms, to_ms, limit)
        return [_row_to_signal(r) for r in rows]

    async def update_status(
        self,
        signal_id: str,
        status: SignalStatus,
        *,
        closed_ts_ms: int | None = None,
    ) -> StoredSignal | None:
        current = await self.get(signal_id)
        if current is None:
            return None
        terminal = status in {SignalStatus.TP_HIT, SignalStatus.SL_HIT, SignalStatus.CANCELLED}
        closed = closed_ts_ms or (_now_ms() if terminal else current.closed_ts_ms)
        pool = await self._conn()
        sql = """
        UPDATE signals
        SET status = $2,
            closed_ts = CASE WHEN $3::BIGINT IS NULL THEN closed_ts
                             ELSE to_timestamp($3 / 1000.0) END,
            updated_at = NOW()
        WHERE id = $1
        """
        async with pool.acquire() as conn:
            await conn.execute(sql, signal_id, status.value, closed)
        return await self.get(signal_id)

    async def active(self) -> list[StoredSignal]:
        return await self.list(status=SignalStatus.ACTIVE, limit=5000)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
