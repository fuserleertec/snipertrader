"""OHLCV bar feed for backtest / lifecycle / paper marks.

Continuous tape is DE **1m / 5m** only:

* Kafka ``ohlcv_bars``
* ``WS /v1/ws/ohlcv?timeframe=1m|5m``
* ``GET /v1/ohlcv/{symbol}?timeframe=1m|5m``

Timescale ``ohlcv_bars`` is the persisted form of that Kafka topic — not
a dashboard snapshot. **Do not** treat ``GET /v1/universe/top`` (15m
ranking book) or ``GET /v1/dashboard/snapshot`` as an OHLC bar feed.

``live_trading`` stays false.
"""

from __future__ import annotations

from typing import Protocol

from sniper_quant.models import AssetClass, OHLCVBar, normalize_symbol

BAR_FEED_TIMEFRAMES = frozenset({"1m", "5m"})
OHLCV_HTTP_PATH = "/v1/ohlcv"
OHLCV_WS_PATH = "/v1/ws/ohlcv"


def assert_bar_feed_timeframe(timeframe: str) -> str:
    """Quant bar consumption is locked to continuous 1m / 5m."""
    tf = str(timeframe or "").strip().lower()
    if tf not in BAR_FEED_TIMEFRAMES:
        raise ValueError(
            "bar feed timeframe must be 1m or 5m (continuous DE ohlcv_bars / "
            f"/v1/ohlcv / /v1/ws/ohlcv); got {timeframe!r}. "
            "15m universe/top and dashboard_snapshots are ranking/dashboard only."
        )
    return tf


class OHLCVLoader(Protocol):
    async def fetch(
        self,
        symbol: str,
        timeframe: str = "5m",
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 10_000,
    ) -> list[OHLCVBar]: ...

    async def upsert(self, bar: OHLCVBar) -> None: ...

    async def close(self) -> None: ...


class InMemoryOHLCVLoader:
    """Demo / test path — same spirit as ``sniper_data.bus.timescaledb.InMemoryOHLCVStore``."""

    def __init__(self, bars: list[OHLCVBar] | None = None) -> None:
        self.bars: list[OHLCVBar] = list(bars or [])

    async def upsert(self, bar: OHLCVBar) -> None:
        for i, existing in enumerate(self.bars):
            if (
                existing.symbol == bar.symbol
                and existing.timeframe == bar.timeframe
                and existing.open_ts_ms == bar.open_ts_ms
            ):
                self.bars[i] = bar
                return
        self.bars.append(bar)

    async def fetch(
        self,
        symbol: str,
        timeframe: str = "5m",
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 10_000,
    ) -> list[OHLCVBar]:
        symbol = normalize_symbol(symbol)
        rows = [b for b in self.bars if b.symbol == symbol and b.timeframe == timeframe]
        if from_ms is not None:
            rows = [b for b in rows if b.open_ts_ms >= from_ms]
        if to_ms is not None:
            rows = [b for b in rows if b.open_ts_ms <= to_ms]
        rows.sort(key=lambda b: b.open_ts_ms)
        return rows[-limit:]

    async def close(self) -> None:
        return None


_FETCH_SQL = """
SELECT EXTRACT(EPOCH FROM ts) * 1000 AS open_ts_ms,
       EXTRACT(EPOCH FROM close_ts) * 1000 AS close_ts_ms,
       symbol, asset_class, timeframe,
       open, high, low, close, volume, n_ticks
FROM ohlcv_bars
WHERE symbol = $1 AND timeframe = $2
  AND ($3::BIGINT IS NULL OR EXTRACT(EPOCH FROM ts) * 1000 >= $3)
  AND ($4::BIGINT IS NULL OR EXTRACT(EPOCH FROM ts) * 1000 <= $4)
ORDER BY ts ASC
LIMIT $5
"""


class TimescaleOHLCVLoader:
    """Reads the DE ``ohlcv_bars`` hypertable with the same DSN / column layout."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool = None

    async def start(self) -> None:
        import asyncpg

        self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)

    async def upsert(self, bar: OHLCVBar) -> None:
        if self._pool is None:
            await self.start()
        assert self._pool is not None
        sql = """
        INSERT INTO ohlcv_bars (
          ts, symbol, asset_class, timeframe,
          open, high, low, close, volume, n_ticks, close_ts
        ) VALUES (
          to_timestamp($1 / 1000.0), $2, $3, $4,
          $5, $6, $7, $8, $9, $10, to_timestamp($11 / 1000.0)
        )
        ON CONFLICT (ts, symbol, timeframe) DO UPDATE SET
          high = GREATEST(ohlcv_bars.high, EXCLUDED.high),
          low = LEAST(ohlcv_bars.low, EXCLUDED.low),
          close = EXCLUDED.close,
          volume = EXCLUDED.volume,
          n_ticks = EXCLUDED.n_ticks,
          close_ts = EXCLUDED.close_ts;
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                bar.open_ts_ms,
                bar.symbol,
                bar.asset_class.value,
                bar.timeframe,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.n_ticks,
                bar.close_ts_ms,
            )

    async def fetch(
        self,
        symbol: str,
        timeframe: str = "5m",
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 10_000,
    ) -> list[OHLCVBar]:
        if self._pool is None:
            await self.start()
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_FETCH_SQL, symbol, timeframe, from_ms, to_ms, limit)
        return [
            OHLCVBar(
                symbol=r["symbol"],
                asset_class=AssetClass(r["asset_class"]),
                timeframe=r["timeframe"],
                open_ts_ms=int(r["open_ts_ms"]),
                close_ts_ms=int(r["close_ts_ms"]),
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                volume=r["volume"],
                n_ticks=r["n_ticks"],
            )
            for r in rows
        ]

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


class CompositeBarFeed:
    """Memory (Kafka/WS upserts) over DE GET, then persisted Kafka ``ohlcv_bars``.

    Never reads ``/v1/universe/top`` or dashboard snapshots.
    """

    def __init__(
        self,
        memory: InMemoryOHLCVLoader | None = None,
        *,
        http: OHLCVLoader | None = None,
        persist: OHLCVLoader | None = None,
    ) -> None:
        self.memory = memory or InMemoryOHLCVLoader()
        self.http = http
        self.persist = persist

    async def upsert(self, bar: OHLCVBar) -> None:
        assert_bar_feed_timeframe(bar.timeframe)
        await self.memory.upsert(bar)
        if self.persist is not None:
            try:
                await self.persist.upsert(bar)
            except Exception:  # noqa: BLE001
                pass

    async def fetch(
        self,
        symbol: str,
        timeframe: str = "5m",
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 10_000,
    ) -> list[OHLCVBar]:
        tf = assert_bar_feed_timeframe(timeframe)
        symbol = normalize_symbol(symbol)
        remote: list[OHLCVBar] = []
        if self.http is not None:
            try:
                remote = await self.http.fetch(
                    symbol, tf, from_ms=from_ms, to_ms=to_ms, limit=limit
                )
            except Exception:  # noqa: BLE001
                remote = []
        if not remote and self.persist is not None:
            try:
                remote = await self.persist.fetch(
                    symbol, tf, from_ms=from_ms, to_ms=to_ms, limit=limit
                )
            except Exception:  # noqa: BLE001
                remote = []
        mem = await self.memory.fetch(
            symbol, tf, from_ms=from_ms, to_ms=to_ms, limit=limit
        )
        by_ts = {b.open_ts_ms: b for b in remote}
        for bar in mem:
            by_ts[bar.open_ts_ms] = bar
        rows = sorted(by_ts.values(), key=lambda b: b.open_ts_ms)
        return rows[-limit:]

    async def close(self) -> None:
        await self.memory.close()
        if self.http is not None:
            await self.http.close()
        if self.persist is not None:
            await self.persist.close()
