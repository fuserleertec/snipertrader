# SniperTrader data-engineering — Phase 1 (Rev. 1.1)

Streaming market-data pipeline and **correct VWAP** (volume-weighted variance)
for SniperTrader.ai. This package lives beside the static site; it does not
replace Vercel serverless functions or the HTML pages.

Python **3.11+**. Asyncio throughout (connectors, Kafka, Redis, API).

## Architecture

```
Exchange adapters          Kafka topics              State / history
─────────────────          ────────────              ──────────────
MockConnector ──┐
Binance stub  ──┼─► raw_ticks ──► OHLCV aggregator ─► ohlcv_bars
US equity stub──┘                 │                   TimescaleDB hypertable
                                  ├─► session_levels ─► Redis session:{symbol}:{type}
                                  └─► vwap_values    ─► Redis vwap:{symbol}:{anchor}
                                                         └─► FastAPI + WebSocket

Pattern topics (contracts only in Phase 1):
  sweep_events → Redis sweep:{symbol}:{id}   TTL ≤ 48h
  fvg_zones    → Redis fvg:{symbol}:{id}     TTL ≤ 48h
  setup_signals
```

Session windows are **asset-class specific**. They are never hardcoded to
`00:00 UTC` for every market.

| Asset class | Sessions |
|---|---|
| Crypto | Asia 00:00–07:00 UTC · London 07:00–13:30 UTC · NY AM 13:30–15:00 UTC · NY PM 18:00–20:00 UTC |
| US equities | RTH 09:30–16:00 `America/New_York` (DST via `zoneinfo`) · ETH 04:00–20:00 NY |
| CME futures | RTH 09:30–16:00 NY · Globex overnight 18:00–09:30 NY (wraps midnight) |

Weekly VWAP resets Monday **00:00 UTC** for crypto and Monday **RTH open
(09:30 NY)** for equities/futures.

JSON contracts: [`/schemas`](../schemas/README.md).

## VWAP math (corrected)

```
VWAP   = Σ(pᵢ · vᵢ) / Σ(vᵢ)
σ_VWAP = sqrt( Σ(vᵢ · (pᵢ − VWAP)²) / Σ(vᵢ) )
```

Bands are `VWAP ± {1,2,3}σ` using **that** σ — not a simple rolling stdev of
price or of `price − VWAP`.

TradingView's built-in VWAP+SD study typically applies an unweighted `stdev`
to `src − vwap`. Those bands match this engine only when every observation
has equal volume. Unequal volume is supposed to diverge; see
`tests/test_vwap.py`.

Redis key: `vwap:{symbol}:{anchor_type}` where `anchor_type` ∈
`session` · `weekly` · `rolling` (default lookback 20).

## How to run

### 1. Unit tests (no Docker)

```bash
cd data_engineering
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

In-process demo (mock ticks → OHLCV / session / VWAP, no brokers):

```bash
sniper-data demo --inmemory --duration 5
```

### 2. Full stack (`docker compose up`)

```bash
cd data_engineering
cp .env.example .env          # optional; compose injects its own env
docker compose up --build
```

| Service | Port | Role |
|---|---|---|
| `pipeline` | — | Mock producer + consumers (end-to-end) |
| `api` | **8000** | Quant HTTP + WebSocket |
| `redpanda` | 19092 | Kafka-compatible broker |
| `redis` | 6379 | Real-time state |
| `timescaledb` | 5432 | Historical OHLCV |
| `evict` | — | Zone TTL repair every 60s |

OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/v1/vwap/BTCUSDT?anchor=session
curl -s http://localhost:8000/v1/session/BTCUSDT
# WebSocket: ws://localhost:8000/v1/ws/vwap?symbol=BTCUSDT
```

Host-side pipeline against compose infra:

```bash
export KAFKA_BOOTSTRAP=localhost:19092
export REDIS_URL=redis://localhost:6379/0
export DATABASE_URL=postgresql://sniper:sniper@localhost:5432/market
sniper-data pipeline
```

## Config

All secrets are environment variables. See [`.env.example`](.env.example).
**Never commit keys.**

| Variable | Default | Purpose |
|---|---|---|
| `KAFKA_BOOTSTRAP` | `localhost:19092` | Redpanda / Kafka |
| `REDIS_URL` | `redis://localhost:6379/0` | State store |
| `DATABASE_URL` | `postgresql://sniper:sniper@localhost:5432/market` | Timescale |
| `DEMO_SYMBOLS` | `BTCUSDT,AAPL,ES` | Mock feed universe |
| `ROLLING_VWAP_PERIODS` | `20` | Rolling VWAP window |
| `FVG_TTL_SECONDS` | `172800` | Clamped to ≤ 48h |
| `TICK_INTERVAL_MS` | `80` | Mock print interval |
| `USE_INMEMORY` | `false` | Skip brokers |
| `BINANCE_*` / `ALPACA_*` | empty | Live stubs only |

## Exchange adapters

Pluggable `ExchangeConnector` implementations in `src/sniper_data/connectors/`:

| Adapter | Status |
|---|---|
| `MockConnector` | Working demo feed (book depth, bid/ask, UTC ms). No keys. |
| `BinanceConnector` | Binance-shaped REST/WS stub. `parse_trade` is real. Live WS requires `BINANCE_ENABLE=1`. |
| `USEquitiesConnector` | Alpaca-shaped REST/WS placeholder. Raises until keys are wired. |

Symbols are normalized to **uppercase, no hyphens**, with an `asset_class`
field (`crypto` · `equity` · `futures`). All event times are **UTC milliseconds**.

## Redis key map (for ML Researchers)

| Key | TTL | Payload |
|---|---|---|
| `session:{symbol}:{session_type}` | none (live book) | OHLC + window bounds |
| `vwap:{symbol}:{anchor_type}` | none (live book) | VWAP + ±1/2/3σ |
| `fvg:{symbol}:{id}` | **required, ≤ 48h** | FVG zone (`schemas/fvg_zone.schema.json`) |
| `sweep:{symbol}:{id}` | **required, ≤ 48h** | Sweep event |

`session_type` ∈ `asia` · `london` · `ny_am` · `ny_pm` · `rth` · `eth` · `globex`.

Zone writes go through `sniper_data.zones.store_fvg` / `store_sweep`, which
always `SET … EX`. A missing TTL raises. TTL > 48h is clamped. The
`sniper-data evict` job (and the `evict` compose service) SCANs `fvg:*` /
`sweep:*`, deletes rows older than 48h, and re-`EXPIRE`s keys with TTL `-1`
or > 48h.

## HTTP API (Quant Developers)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Redis ping + topic list |
| `GET` | `/v1/vwap/{symbol}?anchor=session\|weekly\|rolling` | Latest VWAP + bands |
| `GET` | `/v1/session/{symbol}/{session_type}` | One session book |
| `GET` | `/v1/session/{symbol}` | All cached books for the symbol |
| `WS` | `/v1/ws/vwap?symbol=BTCUSDT` | Pushes Redis pub/sub `vwap:{symbol}` |

Interactive docs at `/docs`. Hyphenated symbols are accepted and normalized
(`btc-usdt` → `BTCUSDT`).

## Kafka topics

Created on pipeline startup (Redpanda also auto-creates):

`raw_ticks` · `ohlcv_bars` · `session_levels` · `vwap_values` ·
`sweep_events` · `fvg_zones` · `setup_signals`

## Layout

```
data_engineering/
  src/sniper_data/          library + CLI
  tests/                    VWAP fixtures, DST sessions, TTL, pipeline
  sql/init.sql              Timescale hypertable + indexes
  docker-compose.yml
  Dockerfile
schemas/                    JSON Schema (repo root, as specified)
```

## CLI

```
sniper-data pipeline [--inmemory] [--duration N]
sniper-data demo     [--inmemory] [--duration N]   # alias of pipeline
sniper-data api      [--host 0.0.0.0 --port 8000]
sniper-data evict    [--inmemory]
```
