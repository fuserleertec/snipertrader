# SniperTrader quant — Phase 1 (Rev. 1.1)

Risk pre-filter, USME stop/target engine, event-driven backtester, and
signal lifecycle. This package sits next to
[`data_engineering/`](../data_engineering/README.md) and shares its
TimescaleDB / Redis / Compose world. It does **not** replace the static
site or Vercel functions.

Python **3.11+**. FastAPI on **:8001** (DE market-data API stays on :8000).

## Why this lives beside `data_engineering/`

| Concern | Owner |
|---|---|
| Ticks → OHLCV / session / VWAP | `data_engineering/` (`sniper_data`) |
| Kafka contracts | `/schemas` (Rev. 1.1) |
| `ohlcv_bars` hypertable | DE `sql/init.sql` |
| `signals` + `account_daily` | DE `sql/02-signals.sql` (this PR) |
| Risk Pre-Filter, sizing, backtest | **this package** (`sniper_quant`) |

Historical bars are read from the same `ohlcv_bars` table DE writes
(same `DATABASE_URL`, same column layout as
`sniper_data.bus.timescaledb.TimescaleStore`). Tests and `sniper-quant demo`
use an in-memory loader — no live Timescale required.

## ML Researchers — `POST /risk/validate`

Phase 1: detectors only. **Do not publish to Kafka `setup_signals` until
this endpoint returns `approved: true`.** Assign `id` only after approval
(Phase 2).

JSON Schema: [`schemas/risk_validate_request.schema.json`](../schemas/risk_validate_request.schema.json)
· OpenAPI: `http://localhost:8001/docs`

### Locked `setup_type` enum

| `setup_type` | Intent |
|---|---|
| `sweep_reclaim` | Liquidity sweep + reclaim |
| `fvg_entry` | Fair-value gap entry |
| `mss_break` | Market-structure shift / break |
| `order_block` | Order-block reaction |
| `sweep_mss` | Sweep followed by MSS |
| `ob_fvg` | Order block + FVG confluence |

Unknown values → HTTP **422**.

### Request (omit `id`)

Stub fields (same as the DE `SetupSignal` core):

`schema_version` (`"1.1"`), `symbol`, `asset_class`, `setup_type`, `side`,
`confidence`, `ref_vwap`, `ref_session`, `ts_ms`.

**Required for risk:** `entry`, `stop`, `target` (numbers),
`timeframe` ∈ {`1m`,`5m`,`15m`}, `trigger_event_ids` (string[]).

**Optional:** `session_type` (DE enum:
`asia` · `london` · `ny_am` · `ny_pm` · `rth` · `eth` · `globex`),
`proposed_position_size` (engine may overwrite via `adjusted_position_size`).

```json
{
  "schema_version": "1.1",
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "setup_type": "sweep_reclaim",
  "side": "long",
  "confidence": 0.87,
  "ref_vwap": 65010.5,
  "ref_session": "ny_am",
  "ts_ms": 1700000000000,
  "entry": 65000,
  "stop": 64600,
  "target": 65800,
  "timeframe": "5m",
  "trigger_event_ids": ["sweep:BTCUSDT:abc", "fvg:BTCUSDT:def"],
  "session_type": "ny_am",
  "proposed_position_size": 1.25
}
```

Hyphenated symbols are normalized (`btc-usdt` → `BTCUSDT`).

### Response (required keys)

JSON Schema: [`schemas/risk_validate_response.schema.json`](../schemas/risk_validate_response.schema.json)

```json
{
  "approved": true,
  "reason": "ok",
  "adjusted_position_size": 4.54545455
}
```

The API also echoes `entry`, `stop`, `target`, `risk_per_unit`, and `checks`.
ML's prices are **not rewritten**; only size may be adjusted.

| `reason` | Meaning |
|---|---|
| `ok` | Pass. Assign `id` and publish with `adjusted_position_size`. |
| `invalid_levels` | Stop/target on the wrong side of entry, or R:R below 1.5. |
| `position_size_exceeds_limit` | Proposed size > 2% equity risk. `adjusted_position_size` is the max. |
| `daily_loss_limit` | 3% daily loss hit, or this trade would breach the remainder. |
| `correlation_threshold` | 60-day \|ρ\| vs an open symbol > 0.70. |
| `same_symbol_conflict` | An ACTIVE position/signal already exists on this symbol. |

After approval, Phase 2 publish to `setup_signals` **requires** `id` plus
additive fields `entry`, `stop`, `target`, `timeframe`, `trigger_event_ids`,
`position_size`, `status: "ACTIVE"`
([`setup_signal.schema.json`](../schemas/setup_signal.schema.json)).

`GET /risk/params` and `GET /v1/setups` expose the locked enum and limits.

## USME stop / take-profit

The ICT calculator (`USME_ICT_Calculator.html`) scores confluence; it does
**not** encode SL/TP math. Defaults below are taken from product copy and
are documented so ML can override per-signal:

| Rule | Source | Implementation |
|---|---|---|
| Stop = **2× ATR(14)** | USME v3.1 (`usme-v3-1.html`) — moved from 1× ATR to cut noise stop-outs | `sl_atr_multiple=2.0` |
| Stop **beyond invalidation / structure** | ICT / USME language (discount-premium, swing invalidation) | If `invalidation` is sent, stop is placed beyond that level **and** no tighter than 2× ATR |
| TP at **2R** (min 1:2; never below 1:1.5) | Prop Firm MasterPlan, 30-Day Funded Challenge | `tp_r_multiple=2.0`, `min_rr=1.5` |
| Fallback ATR | none in-repo | `1%` of \|entry\| when `atr` is omitted |

On `POST /risk/validate`, ML **must** send `entry` / `stop` / `target`. The
pre-filter checks geometry and the 1.5 R floor; it does not rewrite prices.
`compute_usme_levels` remains for the backtester when a demo constructs
levels from ATR.

## Risk parameters

| Parameter | Default | Env |
|---|---|---|
| Fixed-fractional risk | **2%** of equity | `RISK_FRACTION` |
| Max daily loss | **3%** of equity | `MAX_DAILY_LOSS_FRAC` |
| Correlation lookback | 60 daily returns | `CORR_LOOKBACK_DAYS` |
| Correlation reject | \|ρ\| > **0.70** | `CORR_THRESHOLD` |
| Commission | 1 bp | `COMMISSION_BPS` |
| Slippage | 2 bp (each side) | `SLIPPAGE_BPS` |
| Default equity | 100_000 | `DEFAULT_EQUITY` |

Same-symbol: any open / ACTIVE position on that symbol is a hard reject
(including opposite side).

## Signal lifecycle

Timescale table `signals` (see `data_engineering/sql/02-signals.sql`):

`ACTIVE` → `TP_HIT` | `SL_HIT` | `CANCELLED`

## Frontend — dashboard signal table

JSON Schema: [`schemas/dashboard_signal.schema.json`](../schemas/dashboard_signal.schema.json)
· WS: [`schemas/signal_ws_event.schema.json`](../schemas/signal_ws_event.schema.json)
· OpenAPI: `http://localhost:8001/docs`

| Method | Path | Response |
|---|---|---|
| `GET` | `/signals?symbol=&status=&setup_type=&from_ts=&to_ts=&limit=&cursor=` | `{ "items": Signal[], "next_cursor": string \| null }` |
| `GET` | `/signals/{id}` | `Signal` |
| `WS` | `/ws/signals` | `{ "type": "signal.upsert" \| "signal.status", "signal": Signal }` |
| `POST` | `/signals` | `Signal` (after pre-filter; emits `signal.upsert`) |
| `PATCH` | `/signals/{id}` body `{"status":"TP_HIT"}` | `Signal` (emits `signal.status`) |

`from_ts` / `to_ts` are inclusive UTC epoch milliseconds (same unit as `ts_ms`).
Default `limit` is 50 (max 500). Pass `cursor` = previous `next_cursor` for the
next page.

`Signal` fields (dashboard row — aligned with the ML validate candidate):

`id`, `ts_ms`, `symbol`, `asset_class`, `setup_type` (six locked values),
`side`, `entry`, `stop`, `target`, `status`
(`ACTIVE`\|`TP_HIT`\|`SL_HIT`\|`CANCELLED`), `confidence`, `timeframe`
(`1m`\|`5m`\|`15m`), `ref_session`, `trigger_event_ids`.

```js
const ws = new WebSocket("ws://localhost:8001/ws/signals");
ws.onmessage = (ev) => {
  const { type, signal } = JSON.parse(ev.data);
  // type === "signal.upsert" | "signal.status"
};
```

## Backtester

Event-driven replay of OHLCV + setup signals (all six types). Same-bar
SL+TP → **SL wins**. Transaction costs = commission + slippage.
Metrics: **win rate**, **avg R:R**, **Sharpe** (√252), **max drawdown**.

Loader: `TimescaleOHLCVLoader` (DE hypertable) or `InMemoryOHLCVLoader`.

## How to run

### Unit tests (no Docker)

```bash
cd quant
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

In-memory backtest demo (no brokers):

```bash
sniper-quant demo --inmemory
```

### API locally

```bash
sniper-quant api --inmemory --port 8001
# OpenAPI: http://localhost:8001/docs
curl -s http://localhost:8001/health
curl -s http://localhost:8001/risk/params
curl -s -X POST http://localhost:8001/risk/validate \
  -H 'content-type: application/json' \
  -d '{"schema_version":"1.1","symbol":"BTCUSDT","asset_class":"crypto","setup_type":"sweep_reclaim","side":"long","ts_ms":1700000000000,"entry":100,"stop":96,"target":108,"timeframe":"15m","trigger_event_ids":["evt-1"]}'
```

### Full stack (shared with DE)

```bash
cd quant
docker compose up --build
# DE API     http://localhost:8000/docs
# Risk API   http://localhost:8001/docs
```

`quant/docker-compose.yml` **includes** `data_engineering/docker-compose.yml`
so Redpanda, Redis, Timescale, and the DE pipeline come up together. Timescale
init runs `01-init.sql` (OHLCV) then `02-signals.sql` (signals).

Host-side API against compose infra:

```bash
export DATABASE_URL=postgresql://sniper:sniper@localhost:5432/market
sniper-quant api --port 8001
```

## Layout

```
quant/
  src/sniper_quant/     library + CLI
  tests/                sizing, daily loss, correlation, conflict, validate shape
  Dockerfile
  docker-compose.yml    include DE stack + risk-api :8001
data_engineering/sql/02-signals.sql
schemas/risk_validate_*.schema.json
```

## CLI

```
sniper-quant api      [--inmemory] [--host 0.0.0.0 --port 8001]
sniper-quant demo     [--inmemory]   # synthetic backtest → metrics JSON
sniper-quant backtest [--inmemory]   # alias of demo
```
