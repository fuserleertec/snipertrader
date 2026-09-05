# Phase 4 uptime / reliability runbook (paper)

**KPIs (paper window)**

| KPI | Target |
|---|---|
| Pipeline + API uptime | **> 99.5%** (monthly) |
| Tick → Redis VWAP / state p99 | **< 500 ms** |
| `live_trading` | **`false`** until PM / user sign-off (~**19 Sep 2026** paper gate) |

This runbook does **not** authorize live brokers, live order routing, or
changing the paper Alpaca path. Quant risk stays at `POST /risk/validate`.

## Health checks (every page)

```bash
curl -sf http://localhost:8000/health          # ok, phase=3, setups[6]
curl -sf http://localhost:8000/performance/summary
curl -sf http://localhost:8000/metrics         # API
curl -sf http://localhost:9101/metrics         # pipeline
curl -sf http://localhost:9102/metrics         # kill-zone
```

Expect `/performance/summary` **200** with all six `by_setup` keys
(zeros OK). `/health.ok` is Redis ping.

Compose: `docker compose ps` — `redis`, `redpanda`, `timescaledb`,
`pipeline`, `api`, `killzone` healthy.

## On-call triage

1. **Is it live trading?** No. `live_trading=false`. Do not “fix” an
   outage by enabling `BINANCE_ENABLE` or a live Alpaca URL.
2. **Latency?** Grafana tick→VWAP p99 / alert `VwapLatencySLO`.
   See [phase4-monitoring-plan.md](phase4-monitoring-plan.md) and
   [latency.md](latency.md).
3. **Lag?** `sniper_kafka_consumer_lag` / `KafkaConsumerLagHigh` (> 10k).
   Scale **by symbol**, not a second writer on the same symbol.
4. **Redis?** `RedisMemoryHigh`, `RedisErrors`, `redis-cli ping`.
5. **Data gaps?** `MissingTicks` / `sniper_missing_ticks_total`.
6. **WS clients disconnecting?** `sniper_ws_connections`,
   `sniper_ws_dropped_total`.

Severity (paper):

| Sev | Example | Action |
|---|---|---|
| 1 | ticks_in ≠ processed, empty Redis after restart, `/health.ok=false` | Failover steps below; do not publish signals |
| 2 | p99 > 500 ms, lag > 10k for 2m | Restart pipeline replica; check Kafka |
| 3 | WS drops, outlier spikes | Watch; no broker changes |

## Failover

Follow [ha-dr.md](ha-dr.md) (checklist) and [dr-drill.md](dr-drill.md)
(executed Redis RDB + Kafka catch-up). Short form:

| Component | First move |
|---|---|
| API | Restart replica. Stateless Redis reader. Confirm `/health` + `/performance/summary` |
| Pipeline | One writer per symbol. After crash, `avwap:acc:…` rehydrates W/S/Q |
| Redis | `BGSAVE` / volume `dump.rdb`; restore procedure in ha-dr.md. Clients backoff (`RedisStateStore`) |
| Kafka / Redpanda | `rpk cluster health`; `docker compose restart redpanda`; consumers reconnect (`consume_topic`) from group offset |
| Timescale | `pg_isready`; promote replica only if primary is down |

Drill evidence (2026-09-05): Redis RDB restored `vwap` / `session` /
`perf:outcomes`; 200/200 Kafka records replayed — no permanent loss.

## Paper vs live (do not blur)

| | Paper (now → ~19 Sep 2026) | Live |
|---|---|---|
| `live_trading` | **`false`** | Only after PM/user sign-off — **not this runbook** |
| Market data | Mock + optional paper Alpaca **data** stubs (still raise without keys) | Separate change |
| Orders | None from this pipeline | None from this pipeline |
| `ALPACA_BASE_URL` | Paper host if used | Do not switch here |
| `BINANCE_ENABLE` | off | off |

If someone asks to “just turn on live to test uptime,” the answer is no.
Uptime is measured on paper/mock compose and (later) paper-only feeds.

## Related

- Monitoring map: [phase4-monitoring-plan.md](phase4-monitoring-plan.md)
- Knobs: [phase4-infra-optimization.md](phase4-infra-optimization.md)
- Frontend/Quant API: [frontend-quant-api.md](frontend-quant-api.md)
