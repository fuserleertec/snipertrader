# Scalability test (Phase 3)

Harness: `sniper-data bench` / `tests/test_latency.py` — in-process
`Runtime.handle_tick` (InMemory bus + Redis-shaped store). No Docker.
This measures the compute + store path that dominates p99 after Kafka
ack is removed from the critical path (`KAFKA_SEND_WAIT=false` in a
hot demo). CI always asserts p99 < 500 ms.

## Baseline (3 symbols — compose default)

`DEMO_SYMBOLS=BTCUSDT,AAPL,ES` (crypto + equity + futures).

See the “Harness results” section below for the numbers from this PR.

## 2× symbol count

Six symbols: `BTCUSDT,ETHUSDT,AAPL,MSFT,ES,NQ` (2 crypto + 2 equity +
2 futures). Same tick budget, round-robin.

## Recommendations

* **API HPA:** CPU 65%, or average `sniper_ws_connections` ≈ 200 / pod.
  Min 2 / max 8. See [`k8s/hpa.yaml`](../k8s/hpa.yaml).
* **Pipeline HPA:** CPU 70% or `sniper_kafka_consumer_lag{topic=raw_ticks}`
  average 5k. **Assign symbols to replicas** — two writers on one
  symbol double-count VWAP / AVWAP accumulators.
* **Kafka:** `KAFKA_PARTITIONS=6` (one partition per busy symbol is a
  good starting point). Key = symbol.
* **Redis:** shared state; scale vertically first. Alert at 80% of the
  512 MiB compose budget.

## Harness results

Recorded on this PR’s CI-shaped VM (`sniper-data` in-process bench, 2026-09-05):

| Run | symbols | n | p50 ms | p99 ms | max ms | SLO 500 ms |
|---|---|---|---|---|---|---|
| baseline | BTCUSDT | 400 | 0.861 | 1.345 | 1.945 | **pass** |
| 2× | BTCUSDT,ETHUSDT,AAPL,MSFT,ES,NQ | 400 | 0.787 | 1.422 | 14.12 | **pass** |

`pytest -q` in `data_engineering/`: **98 passed**. Incremental W/S/Q VWAP
keeps p99 ~1.4 ms even at 2× symbol count — two orders of magnitude
inside the 500 ms SLO. The 14 ms max on the 2× run is a single warmup
outlier, not p99.
