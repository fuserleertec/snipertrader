"""Tick → Redis VWAP latency harness.

Path under test (in-process, no Kafka broker):

    RawTick → VWAP incremental W/S/Q → Redis SET vwap:{symbol}:{anchor}

Target: p99 < 500 ms (Phase 3 SLO). Incremental VWAP is O(1) per tick
(session / weekly / rolling) so the harness is expected to land in
single-digit milliseconds on CI.
"""

from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.pipeline import Runtime
from sniper_data.symbols import normalize_tick

P99_SLO_S = 0.5


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = min(len(ordered) - 1, max(0, int(round((q / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


async def bench_tick_to_vwap(
    *,
    n: int = 400,
    symbols: list[str] | None = None,
) -> dict:
    """Measure ``handle_tick`` until session VWAP is in the store."""
    symbols = symbols or ["BTCUSDT"]
    bus = InMemoryBus()
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=bars)
    await rt.start()
    base = int(datetime(2024, 6, 4, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
    samples: list[float] = []
    try:
        for i in range(n):
            symbol = symbols[i % len(symbols)]
            tick = normalize_tick(
                symbol=symbol,
                price=100.0 + (i % 17) * 0.05,
                volume=10.0 + (i % 5),
                ts=base + i * 200,
            )
            t0 = time.perf_counter()
            await rt.handle_tick(tick)
            await store.get(f"vwap:{tick.symbol}:session")
            samples.append(time.perf_counter() - t0)
    finally:
        await rt.stop()
    report = {
        "n": len(samples),
        "symbols": symbols,
        "p50_ms": round(percentile(samples, 50) * 1000, 3),
        "p95_ms": round(percentile(samples, 95) * 1000, 3),
        "p99_ms": round(percentile(samples, 99) * 1000, 3),
        "max_ms": round(max(samples) * 1000, 3) if samples else 0.0,
        "mean_ms": round(statistics.fmean(samples) * 1000, 3) if samples else 0.0,
        "slo_p99_ms": int(P99_SLO_S * 1000),
        "pass": bool(samples) and percentile(samples, 99) < P99_SLO_S,
    }
    return report
