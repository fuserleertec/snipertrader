# Performance Under Load

PM integration gate — Data Engineering evidence.

Recorded: `2026-09-05T03:50:13Z`

## Harness

- Path: `RawTick` → incremental VWAP (W/S/Q) → store `SET vwap:{symbol}:session` + Kafka `vwap_values`.
- Symbols (8): `BTCUSDT, ETHUSDT, AAPL, MSFT, NVDA, ES, NQ, CL`.
- Ticks: **3000** at full rate (no inter-tick sleep — elevated vs compose `TICK_INTERVAL_MS=80`).
- Script: `sniper-data load` / `sniper_data.loadtest.bench_under_load`.

## Latency (tick → Redis VWAP)

| metric | value |
|---|---|
| p50 | 1.347 ms |
| p95 | 1.569 ms |
| **p99** | **2.187 ms** |
| max | 47.27 ms |
| wall | 3.9956 s (750.8 ticks/s) |
| SLO | p99 < 500 ms → **PASS** |

## Data loss

Invariant: `ticks_in == ticks_processed == raw_ticks_published` and every tick produced a session VWAP hit.

```json
{
  "ticks_in": 3000,
  "ticks_processed": 3000,
  "raw_ticks_published": 3000,
  "vwap_session_hits": 3000,
  "vwap_values_published": 9000
}
```

**no_data_loss = True**

`vwap_values_published` is 9000 because each tick emits session + weekly + rolling VWAP (3 publishes × 3000 ticks). The loss invariant uses `raw_ticks` 1:1 and a session-VWAP hit per tick.

## Gate: **PASS**

Full JSON:

```json
{
  "harness": "tick_to_redis_vwap",
  "n": 3000,
  "symbols": [
    "BTCUSDT",
    "ETHUSDT",
    "AAPL",
    "MSFT",
    "NVDA",
    "ES",
    "NQ",
    "CL"
  ],
  "symbol_count": 8,
  "wall_s": 3.9956,
  "ticks_per_sec": 750.8,
  "p50_ms": 1.347,
  "p95_ms": 1.569,
  "p99_ms": 2.187,
  "max_ms": 47.27,
  "slo_p99_ms": 500,
  "slo_pass": true,
  "no_data_loss": true,
  "counts": {
    "ticks_in": 3000,
    "ticks_processed": 3000,
    "raw_ticks_published": 3000,
    "vwap_session_hits": 3000,
    "vwap_values_published": 9000
  },
  "pass": true
}
```

