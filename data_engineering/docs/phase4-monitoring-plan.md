# Phase 4 monitoring plan (prep only)

**Status:** ready for paper-window operations. Does **not** flip live
traffic, enable brokers, or change paper paths.

`live_trading=false` until PM / user sign-off (paper gate ~19 Sep 2026).
This document maps **prod data-quality** signals onto metrics already in
the repo and lists gaps as TODO — do not implement live collection here.

## Scrape endpoints (already wired)

| Process | URL | Source |
|---|---|---|
| API | `GET http://localhost:8000/metrics` | `sniper_data.api` |
| Pipeline | `http://localhost:9101/metrics` | compose `METRICS_PORT=9101` |
| Kill-zone | `http://localhost:9102/metrics` | compose `METRICS_PORT=9102` |

Prometheus scrape + rules:
[`observability/prometheus/prometheus.yml`](../observability/prometheus/prometheus.yml),
[`observability/prometheus/alerts.yml`](../observability/prometheus/alerts.yml).

Grafana:
[`observability/grafana/dashboards/sniper-data.json`](../observability/grafana/dashboards/sniper-data.json)
(panels: ticks, tick→VWAP p99, VWAP compute, Kafka lag, Redis memory, WS
connections + publish latency, Redis/Kafka errors, missing/outlier ticks).

## Kafka

| Concern | Existing | Alert today | TODO (not in this PR) |
|---|---|---|---|
| Consumer lag per topic | `sniper_kafka_consumer_lag{topic,group}` | `KafkaConsumerLagHigh` (> 10k, 2m) | Add lag panels per `KAFKA_TOPICS` (incl. `options_chain`, `order_flow`, `performance_outcomes`) |
| Produce/consume errors | `sniper_kafka_errors_total{op}` | `KafkaErrors` (increase > 20 / 5m) | Split `op=publish` vs `op=consume` recording rules |
| Under-replicated partitions | — | — | **TODO:** scrape broker JMX / Redpanda admin (`redpanda_kafka_under_replicated_replicas` or `rpk cluster health`). Not implemented — paper window does not need multi-broker ISR yet |
| Produce latency | `sniper_bus_publish_seconds{topic}` | — | **TODO:** alert p99 > 50 ms on `raw_ticks` |

Risk stays at Quant `POST /risk/validate`. Consumers must **not** grow a
risk-drop counter.

## Redis

| Concern | Existing | Alert today | TODO |
|---|---|---|---|
| Memory | `sniper_redis_memory_bytes` | `RedisMemoryHigh` (> 80% of 512 MiB compose budget, 5m) | Recalibrate threshold to the prod Redis `maxmemory` (not 512 MiB) |
| Connection / op errors | `sniper_redis_errors_total{op}` | `RedisErrors` (increase > 20 / 5m) | — |
| Hit rate | — | — | **TODO:** `INFO stats` `keyspace_hits` / `keyspace_misses` → `sniper_redis_keyspace_hits_total` |
| Key eviction | — | — | **TODO:** `evicted_keys` gauge; zone TTL already clamps ≤ 48h (`sniper-data evict`) |
| Pool | `REDIS_MAX_CONNECTIONS` (default 32) | — | Alert if `connected_clients` approaches the pool cap |

## WebSocket

| Concern | Existing | TODO |
|---|---|---|
| Active connections | `sniper_ws_connections{route}` | Grafana already plots this |
| Publish fanout latency | `sniper_ws_publish_seconds{route}` | **TODO:** alert p99 > 100 ms |
| Dropped frames (backpressure) | `sniper_ws_dropped_total{route}` | **TODO:** alert increase > 0 for 5m |
| Disconnect / reconnect rates | — | **TODO:** counters `sniper_ws_disconnects_total`, `sniper_ws_reconnects_total` (API today only inc/dec the gauge) |

Routes: `vwap`, `session`, `ohlcv`, `avwap`, `volume-profile`, `kill-zone`,
`sweep`, `fvg`, `mss`, `ob`. JSON frame contracts stay Phase 1/2.

## Latency (tick → state)

SLO: **p99 tick → Redis VWAP / state publish < 500 ms**.

Phase 3 load evidence ([performance_under_load.md](performance_under_load.md)):
p99 **2.19 ms** at 3000 ticks / 8 symbols (751 ticks/s). Headroom is large.

| Signal | Metric | Threshold (paper) | Rationale |
|---|---|---|---|
| Tick → VWAP p99 | `sniper_tick_to_vwap_seconds` | **> 500 ms for 5m → critical** (`VwapLatencySLO`) | Contract SLO |
| Early warning | same | **> 50 ms for 15m → warning** | ~20× Phase 3 harness p99; **TODO** add this rule |
| VWAP compute | `sniper_vwap_compute_seconds` | observe only | Incremental W/S/Q; should stay µs–ms |
| AVWAP compute | `sniper_avwap_compute_seconds` | observe only | Same math |

## Data-loss / quality

| Concern | Existing | Alert | TODO |
|---|---|---|---|
| Timestamp gaps | `sniper_missing_ticks_total{symbol}` | `MissingTicks` (increase > 50 / 5m) | Per-symbol page |
| Price outliers | `sniper_outlier_ticks_total{symbol}` | — | **TODO:** warning if increase > 20 / 5m |
| ticks_in vs processed | load harness asserts equality | — | **TODO:** expose `sniper_ticks_received_total` vs `sniper_ticks_processed_total` and alert on mismatch (`abs(received - processed) > 0` for 2m). Harness-only today (`loadtest.bench_under_load`) |
| Kafka undelivered | — | — | **TODO:** producer `RecordAccumulator` / `record-error-rate` |

Paper window: treat a ticks_in/processed mismatch as **sev-1 data quality**,
not a reason to enable a live broker.

## Health (human)

`GET /health` → `{ ok, phase: 3, setups: SETUP_KEYS, topics, inmemory }`.
`GET /performance/summary` must still return all six `by_setup` keys.

## What this plan does **not** do

- Does not set `live_trading=true`.
- Does not open Binance / Alpaca live streams (`BINANCE_ENABLE` stays off;
  equity/options connectors still raise without keys).
- Does not change paper Alpaca base URL (`ALPACA_BASE_URL` paper host).
