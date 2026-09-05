# Phase 4 infra optimization notes (prep only)

**Status:** recommendations from Phase 3 evidence. Paper window only.
`live_trading=false`. Do not retune production brokers or flip live
feeds from this document.

Evidence:

- [performance_under_load.md](performance_under_load.md) — 8 symbols, 3000 ticks, p99 **2.19 ms**, no loss
- [scalability-test.md](scalability-test.md) — 2× symbol count, p99 ~1.4 ms
- [dr-drill.md](dr-drill.md) — Redis RDB restore + Kafka catch-up, no permanent loss
- [ha-dr.md](ha-dr.md) — failover checklist
- [latency.md](latency.md) — incremental W/S/Q path

## What we measured

| Fact | Number |
|---|---|
| Tick → Redis session VWAP p99 (elevated rate) | **2.19 ms** vs SLO 500 ms |
| Throughput in harness | ~751 ticks/s (no sleep) |
| Data loss | `ticks_in == processed == raw_ticks published == 3000` |
| Compose default interval | `TICK_INTERVAL_MS=80` (~12.5 ticks/s/symbol) — far below harness |
| Redis RDB restore | 3 live keys (`vwap`, `session`, `perf:outcomes`) survived process bounce |
| Kafka bounce analogue | 200/200 messages replayed from retained log |

Bottlenecks that *would* matter at prod volume (not seen in harness):
Kafka `send_and_wait` (`KAFKA_SEND_WAIT=true`), Timescale upsert on bar
close, unthrottled AVWAP Redis sync (already capped at
`ANCHOR_SYNC_INTERVAL_S=1`).

## Recommended prod knobs (paper)

Apply only after scrape dashboards are live. Defaults already in
`.env.example` / compose.

| Knob | Paper recommendation | Why |
|---|---|---|
| `KAFKA_PARTITIONS` | **6** (already) | One partition per busy symbol; key = symbol. Do not auto-repartition existing topics — `rpk topic add-partitions` if needed |
| Pipeline replicas | 1 until symbol-assignment exists; then N writers **partitioned by symbol** | Two writers on one symbol double-count VWAP / AVWAP |
| Consumer concurrency | 1 consumer group member per assigned partition | `consume_topic` reconnects with backoff; no risk filter |
| `REDIS_MAX_CONNECTIONS` | **32** | API + pipeline + WS pub/sub; raise only if `RedisErrors` climb |
| `REDIS_RETRIES` / `KAFKA_RETRIES` | 4 / 5 | Proven in unit reconnect tests |
| Incremental VWAP / AVWAP | **keep** | O(1) W/S/Q; do not revert to full-window recalc |
| `KAFKA_SEND_WAIT` | **true** in paper | Durability > extra ms; harness p99 already ≪ SLO |
| `WS_HEARTBEAT_S` / `WS_BACKLOG` | 15 s / 64 | Protocol ping + drop-oldest |
| HPA | [k8s/hpa.yaml](../k8s/hpa.yaml) — API CPU 65% or ~200 WS/pod; pipeline lag 5k | Example only; not deployed |

## What **not** to change during the paper window

- **`live_trading` remains `false`.** No live Binance WS (`BINANCE_ENABLE`),
  no live Alpaca tape, no live order entry. Paper Alpaca URL stays
  `https://paper-api.alpaca.markets` if/when Quant papers.
- Do not lower `KAFKA_SEND_WAIT` to chase latency — we are not SLO-bound.
- Do not raise `TICK_INTERVAL_MS` “to be safe” on the mock feed in a way
  that hides gap detectors (`MISSING_TICK_GAP_MS`).
- Do not share a symbol across two pipeline replicas.
- Do not add Kafka-side risk filters.
- Do not rewrite Phase 1/2 JSON contracts or `SETUP_KEYS`.
- Do not enable Timescale multi-region or Kafka mirroring until budget
  sign-off ([ha-dr.md](ha-dr.md)).
- Do not implement the monitoring TODOs in
  [phase4-monitoring-plan.md](phase4-monitoring-plan.md) as a live-traffic
  cutover — scrape paper first.

## Paper vs later

After ~19 Sep 2026 paper gate, any live-broker decision is a **separate
PM/user change**. This file is not that change.
