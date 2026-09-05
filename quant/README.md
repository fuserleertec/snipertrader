# SniperTrader quant — Phase 2 (Rev. 1.1)

Risk pre-filter, `setup_signals` second gate, Setups 1–3 walk-forward
backtests, live TP/SL lifecycle, and Grafana. This package sits next to
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

**E2E (ML simulation):** call `POST /risk/validate` first. Publish to
Kafka `setup_signals` **only** when `approved` is `true`. Then assign
`id`, persist `adjusted_position_size` (asset units), and include
`entry` / `stop` / `target` / `timeframe` / `trigger_event_ids`. The
quant consumer (`sniper-quant consume` or `POST /v1/signals/ingest`) is
the second gate — geometry + 1.5R — and will discard a bad publish.
Tests: `quant/tests/test_validate.py`, `test_validate_service.py`
(InMemoryBus, no Kafka required).

Joint E2E blockers: live Kafka + ML publisher not wired in this repo;
Timescale 5m history optional for walk-forward (in-memory tape used
here). Do **not** start Phase 3 until ML can hit `:8001` and publish
approved messages to `setup_signals`.

JSON Schema: [`schemas/risk_validate_request.schema.json`](../schemas/risk_validate_request.schema.json)
· OpenAPI: `http://localhost:8001/docs`

### Locked `setup_type` enum

| `setup_type` | Intent |
|---|---|
| `sweep_reclaim` | Setup 1 — Liquidity sweep + VWAP reclaim |
| `fvg_entry` | Setup 2 — Fair-value gap at VWAP / HVN |
| `po3_judas` | Setup 3 — Power of Three / Judas swing |
| `sd_extension_fade` | Setup 4 — SD extension fade (2σ/3σ → VWAP) |
| `vwap_pullback_cont` | Setup 5 — VWAP / 1σ pullback continuation |
| `avwap_ob_confluence` | Setup 6 — AVWAP + HTF order-block confluence |

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
`contributing_factors` / `factor_breakdown` are **publish-only** — do not
send them on `/risk/validate`.

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

The API also echoes `entry`, `stop`, `target`, `risk_per_unit`, `checks`,
and `size_unit: "asset"`. **`adjusted_position_size` is asset units**
(coins / shares / contracts), not USD notional.
ML's prices are **not rewritten**; only size may be adjusted.

| `reason` | Meaning |
|---|---|
| `ok` | Pass. Assign `id` and publish with `adjusted_position_size`. |
| `invalid_levels` | Stop/target on the wrong side of entry, or R:R below 1.5. |
| `position_size_exceeds_limit` | Proposed size > 2% equity risk. `adjusted_position_size` is the max. |
| `daily_loss_limit` | 3% daily loss hit, or this trade would breach the remainder. |
| `correlation_threshold` | 60-day \|ρ\| vs an open symbol > 0.70. |
| `same_symbol_conflict` | An ACTIVE position/signal exists on this symbol in the **opposite** direction. Same-direction pyramid is allowed. |
| `news_window` | Setup 4 only: `ts_ms` within ±15m of the stub calendar. |
| `low_conviction` | `confidence` sent and below the setup floor (S6=0.70, others=0.60). |

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

Same-symbol conflict is **opposite direction only**. An open long does not
block another long on that symbol; it does block a short.

## Signal validation service (Kafka second gate)

ML calls `/risk/validate` first. After approval, ML assigns `id` and
publishes to Kafka `setup_signals`. `sniper-quant consume` is the second
gate:

- Long: `stop < entry` and `target > entry`
- Short: `stop > entry` and `target < entry`
- Take-profit at least **1.5R**
- Pass → unique `id` (kept if present), Timescale `ACTIVE`, WS `signal.upsert`
- Fail → log and discard (never stored as ACTIVE)

In-memory / test path: `InMemoryBus` on topic `setup_signals`, or
`POST /v1/signals/ingest` (same handler, no Kafka).

```bash
sniper-quant consume            # Kafka at KAFKA_BOOTSTRAP
sniper-quant consume --inmemory # bus only (tests / local)
```

## Signal lifecycle

Timescale table `signals` (see `data_engineering/sql/02-signals.sql`):

`ACTIVE` → `TP_HIT` | `SL_HIT` | `CANCELLED`

`sniper-quant monitor` (or `POST /v1/lifecycle/bar`) watches OHLCV and
auto-closes ACTIVE rows when price tags TP or SL. Same-bar SL+TP → **SL
wins**. Closed rows persist `exit_price` / `realized_r` / `closed_ts_ms`
(storage columns `exit_px`, `r_multiple`, `closed_ts`) plus `outcome`
(`win` / `loss`). Those three Frontend fields are on `GET /signals`,
`GET /signals/{id}`, and `WS signal.status`. `realized_r` is **null**
for `ACTIVE` and `CANCELLED`.

## Frontend — dashboard signal table

JSON Schema: [`schemas/dashboard_signal.schema.json`](../schemas/dashboard_signal.schema.json)
· WS: [`schemas/signal_ws_event.schema.json`](../schemas/signal_ws_event.schema.json)
· OpenAPI: `http://localhost:8001/docs`

| Method | Path | Response |
|---|---|---|
| `GET` | `/signals?symbol=&status=&setup_type=&from_ts=&to_ts=&limit=&cursor=` | `{ "items": Signal[], "next_cursor": string \| null }` |
| `GET` | `/signals/history` | Same list as `GET /signals` |
| `GET` | `/performance/summary` | Live metrics; `by_setup` keyed by `setup_type` |
| `GET` | `/signals/{id}` | `Signal` |
| `WS` | `/ws/signals` | `{ "type": "signal.upsert" \| "signal.status", "signal": Signal }` |
| `POST` | `/signals` | `Signal` (after pre-filter; emits `signal.upsert`) |
| `PATCH` | `/signals/{id}` body `{"status":"TP_HIT"}` | `Signal` (emits `signal.status`) |

`GET /performance/summary` (OpenAPI `/docs`) returns:

```json
{
  "win_rate": 0.0,
  "average_rr": 0.0,
  "sharpe_ratio": 0.0,
  "max_drawdown_pct": 0.0,
  "signals_today": 0,
  "signals_week": 0,
  "by_setup": {
    "sweep_reclaim": {
      "setup_type": "sweep_reclaim",
      "product_key": "1_liquidity_sweep_vwap_reclaim",
      "win_rate": 0.0,
      "average_rr": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "signals_today": 0,
      "signals_week": 0
    }
  }
}
```

`by_setup` is keyed by **`setup_type`**, not `product_key`. Empty books are
zeros. Always present: `sweep_reclaim`, `fvg_entry`, `po3_judas`,
`mss_break`, `order_block`, `sweep_mss`. `ob_fvg` is omitted (not in the
validate enum). `product_key` map: `sweep_reclaim` →
`1_liquidity_sweep_vwap_reclaim`, `fvg_entry` → `2_fvg_mitigation_vwap`,
`po3_judas` → `3_po3_judas`, `mss_break` → `4_mss_break`, `order_block` →
`5_order_block`, `sweep_mss` → `6_sweep_mss`. Metrics come from signal
outcomes / `realized_r`.

History is `GET /signals` **or** `GET /signals/history` with `from_ts` /
`to_ts` (plus `symbol` / `status` / `setup_type` / `side`). Both share the
same list implementation.

`from_ts` / `to_ts` are inclusive UTC epoch milliseconds (same unit as `ts_ms`).
Default `limit` is 50 (max 500). Pass `cursor` = previous `next_cursor` for the
next page.

`Signal` fields (dashboard row — aligned with the ML validate candidate):

`id`, `ts_ms`, `symbol`, `asset_class`, `setup_type` (six locked values),
`side`, `entry`, `stop`, `target`, `status`
(`ACTIVE`\|`TP_HIT`\|`SL_HIT`\|`CANCELLED`), `confidence`, `timeframe`
(`1m`\|`5m`\|`15m`), `ref_session`, `trigger_event_ids`,
`realized_r` (signed R on TP/SL; null for ACTIVE/CANCELLED),
`exit_price` (optional), `closed_ts_ms` (optional).

```js
const ws = new WebSocket("ws://localhost:8001/ws/signals");
ws.onmessage = (ev) => {
  const { type, signal } = JSON.parse(ev.data);
  // type === "signal.upsert" | "signal.status"
};
```

## Backtester — Setups 1–3 + walk-forward

Event-driven replay of OHLCV + setup signals. Same-bar SL+TP → **SL wins**.
Transaction costs = commission + slippage.
Metrics: **win rate**, **avg R:R**, **Sharpe** (√252), **max drawdown**.

Loader: `TimescaleOHLCVLoader` (DE hypertable) or in-memory
`synthetic_setup_tape`.

| # | Product | `setup_type` |
|---|---|---|
| 1 | Liquidity Sweep + VWAP Reclaim | `sweep_reclaim` |
| 2 | FVG @ VWAP / HVN | `fvg_entry` |
| 3 | PO3 / Judas Swing | `po3_judas` |
| 4 | SD extension fade | `sd_extension_fade` |
| 5 | VWAP pullback continuation | `vwap_pullback_cont` |
| 6 | AVWAP + HTF order block | `avwap_ob_confluence` |

```bash
sniper-quant backtest --setups 1,2,3 --inmemory --timeframe 5m
# writes quant/reports/setups_1_3_walkforward.md  (share with ML)
sniper-quant backtest --setups 4,5,6 --inmemory --timeframe 5m --grid-mode core
# writes quant/reports/setups_4_6_walkforward.md
```

Walk-forward uses an expanding window (first 40% train, remaining 60% in
`--folds` OOS slices). Grids are the **locked ML ranges** (defaults in bold
in the report): Setup 1 stop buffer / VWAP band / min_rr / MSS lookback;
Setup 2 confluence / confirmation / entry / target; Setup 3 accum session /
displacement / band tag. Orchestrator: `dedupe_window_sec=300`,
`min_conviction=60`. Primary timeframe is **5m**.

`sniper-quant demo` runs the scripted 6-setup smoke book (no live trading).

Paper 2-week gate (in-memory, no broker):

```bash
USE_INMEMORY=1 PYTHONPATH=src python3 -m sniper_quant.cli api --inmemory --port 8001
# POST /paper/reset
# POST /risk/validate → POST /signals (or POST /paper/demo-fortnight)
# GET /paper/account
```

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
# Grafana    http://localhost:3002   admin / admin
```

`quant/docker-compose.yml` **includes** `data_engineering/docker-compose.yml`
so Redpanda, Redis, Timescale, and the DE pipeline come up together. Timescale
init runs `01-init.sql` (OHLCV) then `02-signals.sql` (signals +
`signal_performance` view). Extra services: `signal-validate` (Kafka
consumer), `signal-monitor` (TP/SL), `grafana` on **:3002**.

Grafana panels (per `setup_type` variable, including `po3_judas`):
signals/day, win rate, avg **realized_r** (storage `r_multiple`),
cumulative P&L. Alert rules fire when 7-day win rate < **0.35** or avg R
< **0.50** (`ALERT_WIN_RATE` / `ALERT_AVG_RR`). Provisioning lives in
`quant/grafana/provisioning/`.

Phase 2 surface (done): Kafka `setup_signals` consumer (`sniper-quant consume`),
lifecycle `realized_r` / `exit_price` / `closed_ts_ms`, Grafana on :3002,
`po3_judas` in the locked enum. Walk-forward defaults match ML PR #7.

Host-side API against compose infra:

```bash
export DATABASE_URL=postgresql://sniper:sniper@localhost:5432/market
sniper-quant api --port 8001
```

## Layout

```
quant/
  src/sniper_quant/     library + CLI
  tests/
  grafana/provisioning  Timescale datasource + setup-performance dashboard + alerts
  reports/              walk-forward markdown for ML
  Dockerfile
  docker-compose.yml    DE stack + risk-api :8001 + grafana :3002
data_engineering/sql/02-signals.sql
schemas/risk_validate_*.schema.json
```

## CLI

```
sniper-quant api      [--inmemory] [--host 0.0.0.0 --port 8001]
sniper-quant demo     [--inmemory]   # scripted 7-setup smoke book
sniper-quant backtest --setups 1,2,3 [--inmemory] [--report PATH] [--folds 3]
sniper-quant consume  [--inmemory]   # setup_signals second gate
sniper-quant monitor  [--inmemory] [--symbols BTCUSDT,...] [--timeframe 1m]
```
