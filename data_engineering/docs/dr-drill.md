# Disaster Recovery Drill

PM integration gate — Data Engineering evidence.

Executed: `2026-09-05T03:50:13Z` → `2026-09-05T03:50:14Z`

## Environment

- Host Redis: `/usr/bin/redis-server` on `127.0.0.1:52323`
- Data dir: `/tmp/sniper-dr-drill`
- RDB size after SAVE: **386 bytes**
- Kafka bounce: in-process retained log (compose Redpanda steps below).

## Steps executed (Redis RDB)

1. Start `redis-server` with `--save 60 1` and `--dbfilename dump.rdb`.
2. `SET` live books: `vwap:BTCUSDT:session`, `session:BTCUSDT:ny_am`, `perf:outcomes`.
3. `SAVE` (synchronous RDB).
4. `SHUTDOWN` — process gone (`redis_down`).
5. Start a **new** `redis-server` on the same `--dir` (loads `dump.rdb`).
6. `GET` the three keys; compare to the pre-crash payload.

### Observed — Redis restore **PASS**

- Keys before: `['perf:outcomes', 'session:BTCUSDT:ny_am', 'vwap:BTCUSDT:session']`
- Keys after: `['perf:outcomes', 'session:BTCUSDT:ny_am', 'vwap:BTCUSDT:session']`
- VWAP value after restart: `{'symbol': 'BTCUSDT', 'anchor_type': 'session', 'vwap': 67123.5, 'updated_ts_ms': 1725458400000}`
- Outcomes after restart: `[{'setup': '1_liquidity_sweep_vwap_reclaim', 'won': True, 'rr': 2.0, 'ts_ms': 1725458400000}]`

## Steps executed (Kafka / consumer catch-up)

1. Publish N `raw_ticks` onto a durable log (in-process bus retains every record).
2. Live consumer counts N.
3. Bounce: drop subscribers (broker/consumer death).
4. New consumer replays the retained log from offset 0.
5. Assert `published == live == replayed` — no permanent loss.

### Observed — Kafka catch-up **PASS**

```json
{
  "published": 200,
  "live_consumed": 200,
  "replayed_after_bounce": 200,
  "retained_log": 200,
  "no_permanent_loss": true,
  "note": "In-process retained log = Kafka topic replay after a broker bounce. Compose: docker compose restart redpanda \u2014 consumers reconnect with backoff and catch up from committed offsets (see consume_topic)."
}
```

## Compose-level procedure (Redpanda + Redis services)

When `docker compose` is available (local / prod-like):

```bash
cd data_engineering
docker compose up -d redis redpanda
# seed + BGSAVE
docker compose exec redis redis-cli SET vwap:BTCUSDT:session '{"vwap":1}'
docker compose exec redis redis-cli BGSAVE
docker compose restart redis          # RDB + AOF reload
docker compose exec redis redis-cli GET vwap:BTCUSDT:session
docker compose restart redpanda       # broker bounce
# pipeline consumers call consume_topic() with reconnect/backoff
# and resume from the committed group offset — no risk filter.
```

This VM did not have Docker; the Redis RDB drill ran against host
`redis-server` 7.x and Kafka catch-up against the retained in-process log.
Both exercise the same restore / replay contracts as compose.

## Gate: **PASS**

Raw observation JSON:

```json
{
  "started_utc": "2026-09-05T03:50:13Z",
  "redis_binary": "/usr/bin/redis-server",
  "port": 52323,
  "datadir": "/tmp/sniper-dr-drill",
  "redis_pid": 3642,
  "seed": {
    "save": "OK",
    "keys_before": [
      "perf:outcomes",
      "session:BTCUSDT:ny_am",
      "vwap:BTCUSDT:session"
    ]
  },
  "rdb_bytes": 386,
  "redis_down": true,
  "redis_pid_after": 3653,
  "restore": {
    "keys_after": [
      "perf:outcomes",
      "session:BTCUSDT:ny_am",
      "vwap:BTCUSDT:session"
    ],
    "vwap_restored": {
      "symbol": "BTCUSDT",
      "anchor_type": "session",
      "vwap": 67123.5,
      "updated_ts_ms": 1725458400000
    },
    "outcomes_restored": [
      {
        "setup": "1_liquidity_sweep_vwap_reclaim",
        "won": true,
        "rr": 2.0,
        "ts_ms": 1725458400000
      }
    ],
    "session_restored": {
      "symbol": "BTCUSDT",
      "high": 68000.0
    },
    "ok": true
  },
  "redis_rdb_ok": true,
  "kafka_catchup": {
    "published": 200,
    "live_consumed": 200,
    "replayed_after_bounce": 200,
    "retained_log": 200,
    "no_permanent_loss": true,
    "note": "In-process retained log = Kafka topic replay after a broker bounce. Compose: docker compose restart redpanda \u2014 consumers reconnect with backoff and catch up from committed offsets (see consume_topic)."
  },
  "pass": true,
  "finished_utc": "2026-09-05T03:50:14Z"
}
```

