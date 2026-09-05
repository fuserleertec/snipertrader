# Frontend & Quant — Phase 3 API note

This note freezes the Performance Snapshot envelope and the US-equities
options / order-flow contracts. Phase 1/2 routes are unchanged.

Base URL (compose): `http://localhost:8000`

## Performance Snapshot

```
GET /performance/summary
GET /performance/summary?setup=1_liquidity_sweep_vwap_reclaim   # optional
```

Always **200** with this exact JSON (zeros OK when the store is empty):

```json
{
  "timestamp": 1725458400000,
  "overall": {
    "win_rate": 0.0,
    "average_rr": 0.0,
    "sharpe_ratio": 0.0,
    "max_drawdown_pct": 0.0,
    "signals_today": 0,
    "signals_week": 0
  },
  "by_setup": {
    "1_liquidity_sweep_vwap_reclaim": { "win_rate": 0.0, "average_rr": 0.0, "signals": 0 },
    "2_fvg_mitigation_vwap": { "win_rate": 0.0, "average_rr": 0.0, "signals": 0 },
    "3_po3_asia_range_sweep": { "win_rate": 0.0, "average_rr": 0.0, "signals": 0 },
    "4_sd_extension_fade": { "win_rate": 0.0, "average_rr": 0.0, "signals": 0 },
    "5_vwap_pullback_cont": { "win_rate": 0.0, "average_rr": 0.0, "signals": 0 },
    "6_avwap_ob_confluence": { "win_rate": 0.0, "average_rr": 0.0, "signals": 0 }
  }
}
```

`timestamp` is UTC epoch milliseconds. Schema:
[`schemas/performance_summary.schema.json`](../../schemas/performance_summary.schema.json).

`?setup=` filters **`overall` only**. `by_setup` still returns all six keys.
Unknown setup → **400**.

### Ingestion (Quant / ML)

```
POST /performance/outcomes
Content-Type: application/json
```

```json
{
  "setup": "1_liquidity_sweep_vwap_reclaim",
  "won": true,
  "rr": 2.1,
  "ts_ms": 1725458400000,
  "signal_id": "optional",
  "symbol": "BTCUSDT"
}
```

`setup` may be a canonical key **or** a `setup_type` alias. Equivalent:

```json
{ "setup_type": "po3_judas", "won": false, "rr": 1.0 }
```

| `setup_type` alias | `by_setup` key |
|---|---|
| `po3_judas` | `3_po3_asia_range_sweep` |
| `sd_extension_fade` | `4_sd_extension_fade` |
| `vwap_pullback_cont` | `5_vwap_pullback_cont` |
| `avwap_ob_confluence` | `6_avwap_ob_confluence` |

Canonical keys live in **one** constant: `sniper_data.setups.SETUP_KEYS`.

Kafka topic `performance_outcomes` accepts the same JSON (key = symbol or
setup). The pipeline consumer writes Redis `perf:outcomes`. **Do not put
risk filters on this topic.** Quant `POST /risk/validate` stays at the
publisher boundary.

## Options chain + order flow (ML / Quant)

Topics: `options_chain` · `order_flow`. Field names are frozen — no
`iv` / `oi` / `right` / `side` / `taker_side` aliases.

See [`schemas/options_chain.schema.json`](../../schemas/options_chain.schema.json)
and [`schemas/order_flow.schema.json`](../../schemas/order_flow.schema.json).

`symbol` = underlying, uppercase, no hyphens (`AAPL`). `ts_ms` / `expiry_ms`
are UTC ms. `aggressor` is `buy` \| `sell` (same as `raw_tick`).

Live connectors (`OptionsChainConnector`, `OrderFlowConnector`) raise until
Alpaca keys are set. Compose demo uses `MockOptionsFlow`.

## Frontend streams (unchanged Phase 1/2)

`WS /v1/ws/sweep|fvg|mss|ob?symbol=` and Phase 2 AVWAP / volume-profile /
kill-zone sockets now send protocol-level pings (`WS_HEARTBEAT_S`, default
15s) and drop frames when a client backlog exceeds `WS_BACKLOG` (64).
JSON frame shapes are unchanged.

## Metrics (Frontend ops)

| Process | Scrape |
|---|---|
| API | `GET http://localhost:8000/metrics` |
| Pipeline | `http://localhost:9101/metrics` |
| Kill-zone | `http://localhost:9102/metrics` |

New series: `sniper_ws_connections`, `sniper_ws_publish_seconds`,
`sniper_redis_errors_total`, `sniper_kafka_errors_total`,
`sniper_kafka_consumer_lag`, `sniper_vwap_compute_seconds`,
`sniper_tick_to_vwap_seconds`, `sniper_missing_ticks_total`,
`sniper_outlier_ticks_total`, `sniper_redis_memory_bytes`.
