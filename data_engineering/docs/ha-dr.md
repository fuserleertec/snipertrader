# High availability & disaster recovery

Local compose is a **single-node** demo. This document is the production
runbook. Multi-region is optional and budget-gated — stubs are here so
ops can turn them on without redesigning the pipeline.

Workers (API + pipeline) are **stateless**. Redis is the shared realtime
store; Kafka is the durable log; Timescale holds historical OHLCV (and
can hold outcomes later). Scale horizontally by adding replicas; do not
put two pipeline workers on the same symbol partition.

## TimescaleDB replication

**Recommended:** streaming physical replication (PostgreSQL WAL).

1. Primary writes OHLCV (`sql/init.sql` hypertable).
2. Replica uses `primary_conninfo` + `hot_standby = on`.
3. Application DSN: primary for writes, replica for `GET /v1/ohlcv`.

Logical replication (`CREATE PUBLICATION ohlcv FOR TABLE ohlcv_bars`) is
an alternative when the replica must be a different major version.

Compose stub (not started in CI):

```yaml
# timescaledb-replica:  (budget / multi-region)
#   image: timescale/timescaledb:2.17.2-pg16
#   environment:
#     POSTGRES_USER: sniper
#     POSTGRES_PASSWORD: sniper
#     POSTGRES_DB: market
#   command: ["postgres", "-c", "hot_standby=on"]
#   # Point recovery.conf / standby.signal at timescaledb:5432
```

Promote a replica with `pg_ctl promote` (or `SELECT pg_promote()`). Then
flip `DATABASE_URL` on API / pipeline and restart.

## Kafka / Redpanda mirroring

Optional. MirrorMaker 2 or Redpanda `rpk cluster remote` to a second
region. Topics to mirror: everything in `KAFKA_TOPICS`
(`raw_ticks` … `performance_outcomes`).

Skip until a second region is funded. Partition count (`KAFKA_PARTITIONS`,
default 6) must match on the remote cluster. Consumers are idempotent on
symbol-keyed messages; **no risk filter** on the consumer — Quant
validates at publish.

## Redis RDB snapshot — backup & restore

Compose now enables periodic RDB (`save 60 1`) plus AOF on the demo
Redis so a restart does not wipe AVWAP / performance state.

**Backup**

```bash
docker compose exec redis redis-cli BGSAVE
docker compose cp redis:/data/dump.rdb ./backups/dump-$(date -u +%Y%m%dT%H%M%SZ).rdb
# optional AOF:
docker compose cp redis:/data/appendonly.aof ./backups/
```

**Restore**

1. `docker compose stop redis api pipeline`
2. Copy `dump.rdb` to the Redis volume (`/data/dump.rdb`).
3. `docker compose start redis` then `api` / `pipeline`.
4. `GET /health` → `ok: true`. `GET /performance/summary` should return
   the restored `perf:outcomes` list.

## Failover checklist

### API (`:8000`)

- [ ] Confirm `GET /health` (`phase: 3`, Redis ping).
- [ ] Confirm `GET /performance/summary` returns all six `by_setup` keys.
- [ ] Confirm `GET /metrics` scrapes.
- [ ] Restart replica / bump HPA. API is a Redis reader (anchor POST is
      fence-posted via `avwap:index:{symbol}`).

### Pipeline

- [ ] One writer **per symbol partition**. Extra replicas must not share
      a symbol or AVWAP accumulators double-count.
- [ ] `METRICS_PORT=9101` — `sniper_ticks_processed_total` increasing.
- [ ] After a crash, Redis `avwap:acc:{symbol}:{anchor_id}` rehydrates
      incremental W/S/Q stats.

### Redis

- [ ] `redis-cli ping`
- [ ] `INFO memory` — alert at 80% (`sniper_redis_memory_bytes`).
- [ ] Restore RDB if the volume is lost (see above).
- [ ] Clients reconnect with exponential backoff (`RedisStateStore`).

### Kafka / Redpanda

- [ ] `rpk cluster health`
- [ ] Consumer lag `sniper_kafka_consumer_lag` < 10k / topic.
- [ ] Recreate missing topics: pipeline `KafkaBus.start()` uses
      `KAFKA_PARTITIONS` (default 6). Existing topics are **not**
      auto-repartitioned — use `rpk topic add-partitions` if needed.

### Timescale

- [ ] `pg_isready -U sniper -d market`
- [ ] Hypertable `ohlcv_bars` accepting upserts.
- [ ] Promote replica and flip `DATABASE_URL` if the primary is down.

## Risk boundary (do not move)

Risk enforcement stays at Quant `POST /risk/validate` **before** a
signal is published. Kafka consumers never drop messages for risk.
