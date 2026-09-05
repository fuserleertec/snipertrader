# Tick → signal-ready path (latency)

```
exchange / MockConnector
        │
        ▼
   RawTick (normalize)
        │
        ├─► Kafka raw_ticks          (durable log; keyed by symbol)
        ├─► OHLCV aggregator         (in-process)
        ├─► Session tracker          → Redis session:{symbol}:{type}
        ├─► VWAP incremental W/S/Q   → Redis vwap:{symbol}:{anchor}
        ├─► AVWAP incremental W/S/Q  → Redis avwap:{symbol}:{anchor_id}
        ├─► Volume profile bins      → Redis volume_profile:{symbol}:{session}
        └─► pattern store_*          → Redis + WS overlay (Phase 1/2)
```

**SLO:** p99 tick → Redis VWAP write **< 500 ms**.

## Bottlenecks (measured / designed)

| Stage | Cost | Notes |
|---|---|---|
| VWAP / AVWAP math | O(1) / tick | Incremental `W/S/Q` — no full-window recalc. Rolling VWAP is O(1) add+remove. |
| Redis SET | ~0.2–1 ms local | Three VWAP anchors (session/weekly/rolling) per tick. |
| Kafka `send_and_wait` | 1–20 ms | Default `KAFKA_SEND_WAIT=true` for durability. Set `false` to fire-and-forget. |
| Anchor Redis sync | was every tick | Throttled to `ANCHOR_SYNC_INTERVAL_S` (default 1s). |
| Timescale upsert | per closed bar | Not on the VWAP SLO path. |

## Harness

```bash
cd data_engineering
sniper-data bench --n 400 --symbols BTCUSDT
# or: pytest tests/test_latency.py -q
```

The bench runs `Runtime.handle_tick` in-process (InMemory bus/store) and
records time until `vwap:{symbol}:session` is readable. CI asserts
p99 < 500 ms. Prometheus: `sniper_tick_to_vwap_seconds`,
`sniper_vwap_compute_seconds`.
