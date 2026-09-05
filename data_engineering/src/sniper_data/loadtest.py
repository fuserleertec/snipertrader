"""High-volume tick harness — Performance Under Load (PM gate).

Elevated rate (no inter-tick sleep) across many symbols. Measures
tick → Redis VWAP publish and asserts **no data loss**:

    ticks_in == ticks_processed == raw_ticks published
    every tick has a session VWAP key after handle_tick

SLO: p99 < 500 ms.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.bus.timescaledb import InMemoryOHLCVStore
from sniper_data.latency import P99_SLO_S, percentile
from sniper_data.pipeline import Runtime
from sniper_data.symbols import normalize_tick

DEFAULT_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "AAPL",
    "MSFT",
    "NVDA",
    "ES",
    "NQ",
    "CL",
)


async def bench_under_load(
    *,
    n: int = 3_000,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    symbols = [s.upper() for s in (symbols or list(DEFAULT_SYMBOLS))]
    bus = InMemoryBus(maxlen=max(n * 4, 20_000))
    store = InMemoryStateStore()
    bars = InMemoryOHLCVStore()
    rt = Runtime(inmemory=True, bus=bus, store=store, bars=bars)
    await rt.start()
    base = int(datetime(2024, 6, 4, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
    samples: list[float] = []
    ticks_in = 0
    vwap_hits = 0
    wall0 = time.perf_counter()
    try:
        for i in range(n):
            symbol = symbols[i % len(symbols)]
            tick = normalize_tick(
                symbol=symbol,
                price=100.0 + (i % 31) * 0.05,
                volume=10.0 + (i % 7),
                ts=base + i * 50,
            )
            ticks_in += 1
            t0 = time.perf_counter()
            await rt.handle_tick(tick)
            snap = await store.get(f"vwap:{tick.symbol}:session")
            samples.append(time.perf_counter() - t0)
            if snap is not None:
                vwap_hits += 1
    finally:
        wall_s = time.perf_counter() - wall0
        processed = rt.ticks_processed
        await rt.stop()

    raw_published = len(bus.topics.get("raw_ticks", []))
    vwap_published = len(bus.topics.get("vwap_values", []))
    p99 = percentile(samples, 99)
    loss = {
        "ticks_in": ticks_in,
        "ticks_processed": processed,
        "raw_ticks_published": raw_published,
        "vwap_session_hits": vwap_hits,
        "vwap_values_published": vwap_published,
    }
    no_loss = (
        ticks_in == processed == raw_published
        and vwap_hits == ticks_in
        and vwap_published >= ticks_in
    )
    report = {
        "harness": "tick_to_redis_vwap",
        "n": ticks_in,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "wall_s": round(wall_s, 4),
        "ticks_per_sec": round(ticks_in / wall_s, 1) if wall_s else 0.0,
        "p50_ms": round(percentile(samples, 50) * 1000, 3),
        "p95_ms": round(percentile(samples, 95) * 1000, 3),
        "p99_ms": round(p99 * 1000, 3),
        "max_ms": round(max(samples) * 1000, 3) if samples else 0.0,
        "slo_p99_ms": int(P99_SLO_S * 1000),
        "slo_pass": bool(samples) and p99 < P99_SLO_S,
        "no_data_loss": no_loss,
        "counts": loss,
        "pass": bool(samples) and p99 < P99_SLO_S and no_loss,
    }
    return report


def write_load_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Performance Under Load",
        "",
        "PM integration gate — Data Engineering evidence.",
        "",
        f"Recorded: `{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        "",
        "## Harness",
        "",
        "- Path: `RawTick` → incremental VWAP (W/S/Q) → store `SET vwap:{symbol}:session` + Kafka `vwap_values`.",
        f"- Symbols ({report['symbol_count']}): `{', '.join(report['symbols'])}`.",
        f"- Ticks: **{report['n']}** at full rate (no inter-tick sleep — elevated vs compose `TICK_INTERVAL_MS=80`).",
        "- Script: `sniper-data load` / `sniper_data.loadtest.bench_under_load`.",
        "",
        "## Latency (tick → Redis VWAP)",
        "",
        "| metric | value |",
        "|---|---|",
        f"| p50 | {report['p50_ms']} ms |",
        f"| p95 | {report['p95_ms']} ms |",
        f"| **p99** | **{report['p99_ms']} ms** |",
        f"| max | {report['max_ms']} ms |",
        f"| wall | {report['wall_s']} s ({report['ticks_per_sec']} ticks/s) |",
        f"| SLO | p99 < {report['slo_p99_ms']} ms → **{'PASS' if report['slo_pass'] else 'FAIL'}** |",
        "",
        "## Data loss",
        "",
        "Invariant: `ticks_in == ticks_processed == raw_ticks_published` and every tick produced a session VWAP hit.",
        "",
        "```json",
        json.dumps(report["counts"], indent=2),
        "```",
        "",
        f"**no_data_loss = {report['no_data_loss']}**",
        "",
        f"## Gate: **{'PASS' if report['pass'] else 'FAIL'}**",
        "",
        "Full JSON:",
        "",
        "```json",
        json.dumps(report, indent=2),
        "```",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")
