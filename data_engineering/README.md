# SniperTrader data-engineering — Phase 1 (Rev. 1.1) + Phase 2 + Phase 3

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

Pattern topics (contracts only in Phase 1; Redis+Kafka, no Timescale hypertables):
  sweep_events      → Redis sweep:{symbol}:{id}   TTL ≤ 48h
  fvg_zones         → Redis fvg:{symbol}:{id}     TTL ≤ 48h
  mss_events        → Redis mss:{symbol}:{id}     TTL ≤ 48h
  order_block_zones → Redis ob:{symbol}:{id}      TTL ≤ 48h
  setup_signals

Phase 2 (same raw_ticks stream; asset_class differentiates crypto / equity / futures):
  raw_ticks ─┬─► Anchored VWAP ─► Redis avwap:{symbol}:{anchor_id}
             ├─► Volume profile ─► Redis volume_profile:{symbol}:{session_type}
             └─► (ticks only; kill zones are time-driven)

  anchor_events (ML / HTTP) ─► AVWAP engine
  kill_zone_events (scheduler) ─► Redis kill_zone:{symbol}
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

Ticks may carry optional `aggressor` (`buy`/`sell`) and `is_buyer_maker`.
Bars may carry optional `buy_volume` / `sell_volume`; consumers compute
`delta = buy_volume - sell_volume` (no `delta` field on the wire).

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
| `pipeline` | **9101** | Mock producer + consumers (end-to-end). Prometheus `:9101/metrics` |
| `api` | **8000** | Quant HTTP + WebSocket. Prometheus `GET /metrics` |
| `killzone` | **9102** | Kill-zone scheduler. Prometheus `:9102/metrics` |
| `redpanda` | 19092 | Kafka-compatible broker |
| `redis` | 6379 | Real-time state |
| `timescaledb` | 5432 | Historical OHLCV |
| `evict` | — | Zone TTL repair every 60s |

OpenAPI: [http://localhost:8000/docs](http://localhost:8000/docs)

```bash
curl -s http://localhost:8000/health
curl -s "http://localhost:8000/v1/vwap/BTCUSDT?anchor=session"
curl -s http://localhost:8000/v1/session/BTCUSDT
curl -s "http://localhost:8000/v1/ohlcv/BTCUSDT?timeframe=1m&limit=200"
# ws://localhost:8000/v1/ws/vwap?symbol=BTCUSDT
# ws://localhost:8000/v1/ws/session?symbol=BTCUSDT
# ws://localhost:8000/v1/ws/ohlcv?symbol=BTCUSDT&timeframe=1m
curl -s http://localhost:8000/v1/kill-zone/BTCUSDT
curl -s http://localhost:8000/v1/volume-profile/BTCUSDT
curl -s -X POST http://localhost:8000/v1/anchors -H 'content-type: application/json' \
  -d '{"symbol":"BTCUSDT","anchor_time":1725458400000,"anchor_price":64000,"source":"manual"}'
curl -s http://localhost:8000/v1/avwap/BTCUSDT
curl -s http://localhost:8000/metrics
# ws://localhost:8000/v1/ws/avwap?symbol=BTCUSDT
# ws://localhost:8000/v1/ws/volume-profile?symbol=BTCUSDT
# ws://localhost:8000/v1/ws/kill-zone?symbol=BTCUSDT
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
| `KILLZONE_INPROCESS` | `true` | Run the timer inside `pipeline` (compose sets `0`) |
| `KILLZONE_POLL_S` | `1` | Scheduler poll interval |
| `METRICS_PORT` | `0` | Pipeline/killzone Prometheus port (`0` = off) |
| `MAX_ANCHORS_PER_SYMBOL` | `32` | Cap on live AVWAP anchors |
| `SWING_DETECT` | `true` | In-process fractal swing → anchors |
| `SWING_LOOKBACK` | `5` | MSS / ICT swing confirmation bars each side |
| `RISK_VALIDATE_URL` | `http://localhost:8001/risk/validate` | Quant Risk Pre-Filter |
| `SETUP_ATR_PERIOD` | `14` | ATR lookback for stop / overlap / displacement |
| `SETUP_STOP_BUFFER_ATR` | `0.05` | Stop buffer as a multiple of ATR |
| `SETUP1_MIN_RR` | `2.0` | Setup 1 minimum R:R (nearer of ±1σ/±2σ) |
| `SETUP1_MSS_SWING_LOOKBACK` | `5` | Setup 1 MSS swing lookback |
| `SETUP1_MAX_BARS_SWEEP_TO_MSS` | `15` | Expire armed sweep if no MSS |
| `SETUP1_REQUIRE_CONFIRMED_SWEEP` | `true` | Require `confirmed` / `reclaim` |
| `SETUP1_TIMEFRAMES` | `5m,15m` | Setup 1 only |
| `SETUP2_OVERLAP_TOL_ATR` | `0.05` | VWAP / HVN overlap pad |
| `SETUP2_PIN_WICK_RATIO` | `2.5` | Pin confirmation wick/body |
| `SETUP2_MAX_FVG_AGE_HOURS` | `24` | Ignore older FVGs |
| `SETUP2_TARGET_RR_FALLBACK` | `2.0` | If no prior swing |
| `SETUP3_ACCUM_SESSION` | `asia` | Globex optional for futures |
| `SETUP3_KILL_ZONE` | `ny_am` | Crypto also accepts London |
| `SETUP3_DISPLACEMENT_MIN_BODY_ATR` | `1.2` | Displacement body ≥ this × ATR |
| `SETUP3_REQUIRE_BAND_TAG` | `true` | Sweep must tag ±1σ or ±2σ |
| `SETUP3_MAX_BARS_SWEEP_TO_DISPLACE` | `6` | Expire Judas if no displacement |
| `SETUP_DEDUPE_WINDOW_SEC` | `300` | Orchestrator dedupe window |
| `SETUP_MIN_CONVICTION_TO_VALIDATE` | `60` | Skip risk if conviction below this (S6 uses 70) |
| `SETUP_ATR_REGIME_HIGH_FRAC` | `0.02` | ATR/price ≥ this → high-vol regime (S4 requires ±3σ) |
| `SETUP4_VOL_FRAC` / `SETUP4_VOL_AVG_PERIOD` | `0.8` / `20` | Low-volume confirm |
| `SETUP4_MIN_RR` / `SETUP4_MIN_RR_AT_3S` | `1.5` / `2.0` | Fade R:R (prefer 2.0 at 3σ) |
| `SETUP4_NEWS_WINDOW_SEC` | `900` | News skip window (stub allows if no feed) |
| `SETUP5_TREND_BARS` | `20` | 5m bars above/below rising/falling VWAP |
| `SETUP5_MIN_RR` | `2.0` | Pullback continuation R:R |
| `SETUP6_MIN_RR` / `SETUP6_MIN_CONVICTION` | `2.0` / `70` | AVWAP+OB confluence |
| `SETUP6_HTF_TIMEFRAMES` | `1h,4h` | HTF rejection / OB book |
| `BINANCE_*` / `ALPACA_*` | empty | Live stubs only |

## Exchange adapters

Pluggable `ExchangeConnector` implementations in `src/sniper_data/connectors/`:

| Adapter | Status |
|---|---|
| `MockConnector` | Working demo feed (book depth, bid/ask, UTC ms). No keys. |
| `BinanceConnector` | Binance-shaped REST/WS stub. `parse_trade` is real. Live WS requires `BINANCE_ENABLE=1`. |
| `USEquitiesConnector` | Alpaca-shaped REST/WS placeholder. Raises until keys are wired. |
| `FuturesConnector` | CME / Globex placeholder. Demo futures ticks come from `MockConnector`. |

Symbols are normalized to **uppercase, no hyphens**, with an `asset_class`
field (`crypto` · `equity` · `futures`). All event times are **UTC milliseconds**.

**Futures convention:** root / continuous `ES` (demo default) or dated CME
`ESZ2024` = root + month code (FGHJKMNQUVXZ) + 4-digit year. `ESZ24` is
accepted as-is (not rewritten). Always `^[A-Z0-9]+$`.

## Redis key map (for ML Researchers)

| Key | TTL | Payload |
|---|---|---|
| `session:{symbol}:{session_type}` | none (live book) | OHLC + window bounds |
| `vwap:{symbol}:{anchor_type}` | none (live book) | VWAP + ±1/2/3σ |
| `fvg:{symbol}:{id}` | **required, ≤ 48h** | FVG zone (`schemas/fvg_zone.schema.json`) |
| `sweep:{symbol}:{id}` | **required, ≤ 48h** | Sweep event (`side` + `swept_level`) |
| `mss:{symbol}:{id}` | **required, ≤ 48h** | MSS event (`schemas/mss_event.schema.json`) |
| `ob:{symbol}:{id}` | **required, ≤ 48h** | Order block (`schemas/order_block.schema.json`) |

`session_type` ∈ `asia` · `london` · `ny_am` · `ny_pm` · `rth` · `eth` · `globex`.

Phase 2 keys (no TTL; live books):

| Key | Payload |
|---|---|
| `avwap:{symbol}:{anchor_id}` | Anchored VWAP + ±1/2/3σ bands (exact Phase 2 JSON) |
| `avwap:latest:{symbol}` | Convenience pointer; same JSON as the last AVWAP write |
| `avwap:meta:{symbol}:{anchor_id}` | Anchor metadata (`source`, times) — not a wire schema |
| `avwap:index:{symbol}` | JSON list of `anchor_id`s |
| `avwap:acc:{symbol}:{anchor_id}` | Incremental W/S/Q stats for worker restart |
| `volume_profile:{symbol}:{session_type}` | HVN / LVN / POC |
| `kill_zone:{symbol}` | Current (or last) kill-zone event — exact Kafka JSON |
| `kill_zone:active:{asset_class}` | Class-level view: `kill_zone`, `start_time`, `end_time`, `active`, `asset_class` |

Zone writes go through `store_fvg` / `store_sweep` / `store_mss` / `store_ob`,
which always `SET … EX`. A missing TTL raises. TTL > 48h is clamped. The
`sniper-data evict` job (and the `evict` compose service) SCANs `fvg:*` /
`sweep:*` / `mss:*` / `ob:*`, deletes rows older than 48h, and re-`EXPIRE`s
keys with TTL `-1` or > 48h.

## HTTP API (Quant Developers / frontend)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Redis ping + topic list |
| `GET` | `/v1/vwap/{symbol}?anchor=session\|weekly\|rolling` | Latest VWAP + bands |
| `GET` | `/v1/session/{symbol}/{session_type}` | One session book |
| `GET` | `/v1/session/{symbol}` | All cached books for the symbol |
| `GET` | `/v1/ohlcv/{symbol}?timeframe=1m&limit=200` | Closed bars for chart bootstrap |
| `WS` | `/v1/ws/vwap?symbol=BTCUSDT` | Seed + Redis `vwap:{symbol}` |
| `WS` | `/v1/ws/session?symbol=BTCUSDT` | Seed `session:{symbol}:*` + Redis `session:{symbol}` |
| `WS` | `/v1/ws/ohlcv?symbol=BTCUSDT&timeframe=1m` | Seed last N bars + Redis `ohlcv:{symbol}:{timeframe}` |

`timeframe` is required on OHLCV routes: `1m` · `5m` · `15m` · `1h` · `4h`.

Interactive docs at `/docs`. Hyphenated symbols are accepted and normalized
(`btc-usdt` → `BTCUSDT`).

Example session WS frame (`SessionLevels`):

```json
{"schema_version":"1.1","symbol":"BTCUSDT","asset_class":"crypto","session_type":"london",
 "session_start_ms":1717500000000,"session_end_ms":1717523400000,
 "open":100.0,"high":102.0,"low":98.0,"close":99.67,"volume":60.0,"updated_ts_ms":1717500003000}
```

Example OHLCV WS / HTTP bar (`ohlcv_bar` schema; optional `buy_volume` / `sell_volume`):

```json
{"schema_version":"1.1","symbol":"BTCUSDT","asset_class":"crypto","timeframe":"1m",
 "open_ts_ms":1717502400000,"close_ts_ms":1717502460000,
 "open":100.0,"high":101.0,"low":99.5,"close":100.5,"volume":14.0,"n_ticks":2,
 "buy_volume":10.0,"sell_volume":4.0}
```

```bash
curl -s "http://localhost:8000/v1/ohlcv/BTCUSDT?timeframe=1m&limit=200"
# ws://localhost:8000/v1/ws/session?symbol=BTCUSDT
# ws://localhost:8000/v1/ws/ohlcv?symbol=BTCUSDT&timeframe=1m
# ws://localhost:8000/v1/ws/vwap?symbol=BTCUSDT
```

## Kafka topics

Created on pipeline startup (Redpanda also auto-creates):

`raw_ticks` · `ohlcv_bars` · `session_levels` · `vwap_values` ·
`sweep_events` · `fvg_zones` · `mss_events` · `order_block_zones` ·
`setup_signals` · `kill_zone_events` · `anchor_events`

## Layout

```
data_engineering/
  src/sniper_data/          library + CLI
  src/sniper_data/pattern_detection/  sweep / FVG / MSS / order-block + Phase 2 anchors
  tests/                    VWAP fixtures, DST sessions, TTL, pattern detectors
  sql/init.sql              Timescale hypertable + indexes
  docker-compose.yml
  Dockerfile
schemas/                    JSON Schema (repo root, as specified)
```

## CLI

```
sniper-data pipeline [--inmemory] [--duration N]
sniper-data demo     [--inmemory] [--duration N]   # alias of pipeline
sniper-data patterns [--inmemory] [--duration N]
sniper-data patterns --inmemory --replay           # ICT fixtures + swing→anchor wiring
sniper-data setups   --inmemory                    # USME setups 1–6 fixtures + mock risk
sniper-data setups   --inmemory --replay           # same
sniper-data api      [--host 0.0.0.0 --port 8000]
sniper-data evict    [--inmemory]
sniper-data killzones [--inmemory] [--duration N]
```

## Phase 2 — Multi-asset, Anchored VWAP, volume profile, kill zones

Phase 1 contracts are unchanged. The mock/demo feed already streams **three**
asset classes on the existing `raw_ticks` topic (`DEMO_SYMBOLS=BTCUSDT,AAPL,ES`).
Session windows stay asset-class specific (see table above).

### ML contract — register / request anchors

Three equivalent ways to create an anchor. The engine then computes VWAP from
`anchor_time` → now on subsequent ticks (`ts_ms >= anchor_time`).

**HTTP (preferred for tools / notebooks)**

```http
POST /v1/anchors
Content-Type: application/json

{
  "symbol": "BTCUSDT",
  "anchor_time": 1725458400000,
  "anchor_price": 64000.00,
  "source": "swing_high",
  "asset_class": "crypto",
  "anchor_id": "optional-uuid"
}
```

`source` ∈ `manual` · `swing_high` · `swing_low` · `earnings` · `news`.
`asset_class` and `anchor_id` are optional (`asset_class` is inferred;
`anchor_id` is a UUID if omitted). Response is `201` with the assigned
`anchor_id` plus Redis keys.

`GET /v1/anchors?symbol=BTCUSDT` lists `avwap:meta:{symbol}:{id}` rows.

**Kafka (same JSON as the POST body)**

Publish to `anchor_events` (key = symbol). The pipeline consumer registers
the anchor and begins accumulating. Idempotent on `anchor_id`.

**In-process hooks**

* Fractal swing detector (`SWING_DETECT=1`) emits `swing_high` / `swing_low`.
* `sniper_data.swings.earnings_anchor` / `news_anchor` are placeholders —
  call them when an earnings or news timestamp is known; they produce the
  same `AnchorRegistration` object.
* ML ICT swings (below) publish the same JSON to `anchor_events`.

## Pattern detectors (ML Researchers)

`sniper_data.pattern_detection` consumes DE-normalized `raw_ticks`,
`ohlcv_bars`, `session_levels`, and `vwap_values`. It publishes the
landed pattern topics and writes zones through `store_fvg` / `store_sweep`
/ `store_mss` / `store_ob` (TTL ≤ 48h). Zones are **Redis + Kafka only**.

| Detector | Rule | Notes |
|---|---|---|
| Sweep (corrected) | Break of established session high/low **plus** in-process delta divergence | `side=sell` = high swept; `side=buy` = low swept. `volume_profile` is scored, **never a gate**. Reclaim/`confirmed` after high-volume opposite close back inside the range. |
| FVG | 3-candle imbalance on `1m` / `5m` / `15m` | `mitigated` = filled on retrace into `[low, high]`. |
| MSS | Swing lookback default **5** (`SWING_LOOKBACK`) | Bullish = break of last lower-high after a **real** sell-side sweep. Bearish = break of last higher-low after a buy-side sweep. |
| Order block | Last opposite candle before displacement | Zone = origin candle high/low. |

Delta is computed **in the detector** as `buy_volume − sell_volume`. There
is **no `delta` field** on ticks or bars and **no Redis key** for delta.

## ML Researchers Phase 2 — Anchor / AVWAP wiring

When the ICT swing / MSS detector confirms a swing high or swing low it
**registers an AVWAP anchor** using the locked DE contract. Prefer Kafka
in-pipeline; use the HTTP helper from notebooks / tools.

**Kafka (realtime, key = symbol, idempotent on `anchor_id`)**

```json
{
  "symbol": "BTCUSDT",
  "anchor_time": 1725458400000,
  "anchor_price": 64000.0,
  "source": "swing_high"
}
```

`source` is `swing_high` or `swing_low` (also accepted: `manual` · `earnings`
· `news`). Optional: `anchor_id`, `asset_class` (inferred from the symbol if
omitted). **No other field names.** Topic: `anchor_events`.

Helpers:

```python
from sniper_data.pattern_detection.anchors import publish_anchor, post_anchor, swing_to_registration
from sniper_data.pattern_detection.context import get_avwap, get_volume_profile, get_kill_zone

await publish_anchor(bus, swing_to_registration(symbol, swing, asset_class))
# or: await post_anchor(req, base_url="http://localhost:8000")
```

**Consume (do not redefine shapes)**

| Store | Key / topic | Model |
|---|---|---|
| Redis | `avwap:{symbol}:{anchor_id}` | `AnchoredVWAP` — `{anchor_id, symbol, anchor_time, anchor_price, vwap_value, bands:{plus_1_sigma…minus_3_sigma}, asset_class}` (no `schema_version`) |
| Redis | `volume_profile:{symbol}:{session_type}` | `VolumeProfile` — HVN / LVN / POC |
| Redis | `kill_zone:{symbol}` | `KillZoneEvent` |
| Kafka | `kill_zone_events` | same JSON as the Redis key |

```python
snap = await get_avwap(store, "BTCUSDT", anchor_id)
profile = await get_volume_profile(store, "BTCUSDT", "ny_am")
zone = await get_kill_zone(store, "BTCUSDT")
```

## Phase 2 — USME setup detection (setups 1–3)

`sniper_data.setup_detection` consumes **only** landed DE topics / Redis keys
(`sweep_events`, `mss_events`, `fvg_zones`, `ohlcv_bars`, `session_levels`,
`vwap_values`, `kill_zone_events`, `anchor_events`; Redis `session:`, `vwap:`,
`fvg:`, `sweep:`, `mss:`, `ob:`, `avwap:`, `volume_profile:`, `kill_zone:`).

DE sweep mapping (do not invert):

* `side=buy` = session **low** swept (ICT sell-side liquidity) → Setup 1 **long**
  after a bullish MSS (break last LH) whose candle **closes above**
  `vwap:{symbol}:session`.
* `side=sell` = session **high** swept (ICT buy-side liquidity) → Setup 1 **short**
  after a bearish MSS (break last HL) whose candle **closes below** session VWAP.

This reclaim pairing is **USME Setup 1**, not the Phase 1 MSS continuation
pairing. Incoming `mss_events` are used when `direction` matches reclaim;
otherwise the detector measures the LH/HL break from `ohlcv_bars`.

| Setup | `setup_type` | Rule |
|---|---|---|
| 1 | `sweep_reclaim` | Confirmed sweep + MSS + session-VWAP close on **5m/15m**. Stop = extreme ± `0.05×ATR(14)`. TP = nearer of ±1σ/±2σ with `min_rr=2.0`. Max 15 bars sweep→MSS. |
| 2 | `fvg_entry` | FVG age ≤ 24h overlapping session VWAP **or** HVN/POC (`overlap_tol=0.05×ATR`). Confirm engulfing **or** pin (`wick_ratio=2.5`). Entry = confirmation close. Stop beyond FVG + ATR buffer. Target = prior swing, else 2R. Overlapping OB stays on `trigger_event_ids` + `order_block` factor — Quant does **not** accept `ob_fvg`. |
| 3 | `po3_judas` | Accum `session:{symbol}:asia` (Globex optional for futures). Kill zone `ny_am` (crypto: NY AM or London). Displacement body ≥ `1.2×ATR` within 6 bars. **Require** ±1σ/±2σ tag. Stop = wick ± ATR buffer. TP = opposite accum extreme. |

Orchestrator: setups 1–3 run in parallel. Dedupe (`SETUP_DEDUPE_WINDOW_SEC=300`)
keeps the highest conviction when symbol + side + overlapping TFs fire.
Candidates with conviction &lt; `SETUP_MIN_CONVICTION_TO_VALIDATE` (60) are
logged and **not** sent to risk. Conviction stays in logs only;
validate / Kafka get `confidence = conviction/100`.

**Risk gate (locked):** before `setup_signals`, `POST {RISK_VALIDATE_URL}` with
**only** `schema_version`, `symbol`, `asset_class`, `setup_type`, `side`,
`confidence`, `ref_vwap`, `ref_session`, `ts_ms`, `entry`, `stop`, `target`,
`timeframe`, `trigger_event_ids`, optional `session_type`, optional
`proposed_position_size`. **Omit `id`.** Do not send `risk_reward`,
`setup_id`, `kill_zone*`, or `conviction`. Publish iff `approved: true`, then
assign `id` and set `status=ACTIVE` / `position_size=adjusted_position_size`.
Rejects are logged and dropped (Prometheus `sniper_setup_rejected_total` is
the false-positive proxy).

```bash
sniper-data setups --inmemory
sniper-data setups --e2e-report --e2e-out /tmp/phase2_e2e_report.json
```

`--e2e-report` is the Phase 3 PM integration pack (setups 1–6 through
mocked `POST /risk/validate`, plus conviction / reject / dedupe gates).
It writes `quant_replay/` next to `--e2e-out` so Quant can replay locked
validate JSON against `sniper-quant api --inmemory --port 8001`.

## Phase 3 — Setups 4–6 + full orchestrator

Detectors 4–6 run **in parallel** with 1–3. Same risk gate: `POST /risk/validate`
with the locked field allow-list (**omit `id`**, omit `contributing_factors` /
`factor_breakdown`). Publish to `setup_signals` only when `approved: true`.

| Setup | `setup_type` | Quant `GET /performance/summary` key | Rule |
|---|---|---|---|
| 4 | `sd_extension_fade` | `4_sd_extension_fade` | Session VWAP `vwap:{symbol}:session` flat `band_m2`/`band_p2`/`band_m3`/`band_p3`. Trigger ±2σ or ±3σ. Volume &lt; 80% of 20-bar avg. Rejection: engulfing / pin (hammer / shooting star) / 1m–5m MSS. Long lower band, short upper. SL beyond ±3σ, TP = session VWAP. min_rr 1.5 (prefer 2.0 at 3σ). Conviction ≥ 60. |
| 5 | `vwap_pullback_cont` | `5_vwap_pullback_cont` | Rising session VWAP + price above for N=20 5m bars (falling / below → short). Pullback to VWAP or ±1σ with OB or FVG. First clean VWAP touch (tunable lookback). Confirm engulfing or strong trend candle. SL behind swing, TP structure liquidity. min_rr 2.0, conviction ≥ 60. |
| 6 | `avwap_ob_confluence` | `6_avwap_ob_confluence` | Phase 2 AVWAP **nested bands only** on `avwap:{symbol}:{anchor_id}` (`vwap_value` + `bands.plus_1_sigma`…`minus_3_sigma`, no `schema_version`, **not** Phase 1 `band_p1`). HTF OB 1h/4h. Confluence: AVWAP line inside OB `[low, high]`. Rejection or MSS on 1h/4h. SL past opposite OB side, TP HTF swing liquidity. min_rr 2.0, conviction ≥ 70. Wire `timeframe` is `15m` (Quant validate enum). Daily HTF = wide 4h swing proxy. |

**AVWAP vs session VWAP (do not mix):**

* Setups 4–5 read Phase 1 `vwap:{symbol}:session` (`VWAPValues` with flat `band_m1`…`band_p3`).
* Setup 6 reads Phase 2 `avwap:{symbol}:{anchor_id}` (`AnchoredVWAP` nested `bands`).

**News filter (Setup 4):** no calendar feed ships in-repo. `AllowAllNewsFilter` is the
default stub (always allow). Plug in `SkipWindowNewsFilter({symbol: [ts_ms, …]})` or
any `NewsFilter.should_skip(symbol, ts_ms, *, window_ms)` implementation. Window =
`SETUP4_NEWS_WINDOW_SEC` (900s / 15m).

**Orchestrator:** all six detectors via `asyncio.gather`. Pre-filter and post-filter
candidates are logged. Dedupe same symbol + direction within `SETUP_DEDUPE_WINDOW_SEC`
(300s) keeps highest conviction, else earliest `ts_ms`. Conviction is refined with
kill-zone, volume-confirm, and multi-pattern bonuses (env-tunable). High ATR regime
(`SETUP_ATR_REGIME_HIGH_FRAC`) forces Setup 4 to require a ±3σ tag.

Publish-only fields on `setup_signals` (never on validate):

* `contributing_factors` — stable factor ids that fired (labels, not chart ids).
* `factor_breakdown` — `{name, weight, score, note?}[]`. `sum(score)` ≈ conviction
  (0–100); `confidence = conviction / 100`.

Join the chart via signal `id` + `trigger_event_ids`. Factor names are not
substitute event ids. Stable names: `liquidity_sweep`, `mss`, `fvg`,
`order_block`, `vwap_reclaim`, `vwap_band_extension`, `vwap_pullback`,
`first_touch`, `low_volume`, `volume_confirm`, `rejection_candle`, `engulfing`,
`avwap`, `htf_ob`, `kill_zone`, `multi_pattern`, `trend_align`.

```bash
sniper-data setups --inmemory
sniper-data setups --e2e-report --e2e-out /tmp/phase3_e2e_report.json
```

Pattern-detector in-memory demo (sweeps / FVG / MSS / anchors, not setups):

```bash
sniper-data patterns --inmemory --replay
```

That path confirms a swing → `anchor_events` → mock DE AVWAP write →
`get_avwap` read-back.

### Frontend contract — AVWAP + volume profile

| Method | Path | Redis / channel |
|---|---|---|
| `GET` | `/v1/avwap/{symbol}` | `avwap:latest:{symbol}` |
| `GET` | `/v1/avwap/{symbol}/{anchor_id}` | `avwap:{symbol}:{anchor_id}` |
| `WS` | `/v1/ws/avwap?symbol=BTCUSDT` | seed + channel `avwap:{symbol}` |
| `WS` | `/v1/ws/avwap?symbol=BTCUSDT&anchor_id=` | filtered to one anchor |
| `GET` | `/v1/volume-profile/{symbol}` | all `volume_profile:{symbol}:*` |
| `GET` | `/v1/volume-profile/{symbol}/{session_type}` | one session book |
| `WS` | `/v1/ws/volume-profile?symbol=BTCUSDT` | channel `volume_profile:{symbol}` |
| `GET` | `/v1/kill-zone/{symbol}` | `kill_zone:{symbol}` |
| `GET` | `/v1/kill-zone/active/{asset_class}` | `kill_zone:active:{asset_class}` |
| `WS` | `/v1/ws/kill-zone?symbol=BTCUSDT` | channel `kill_zone:{symbol}` |
| `GET` | `/metrics` | Prometheus (API process) |

AVWAP wire JSON (no `schema_version`):

```json
{
  "anchor_id": "uuid",
  "symbol": "BTCUSDT",
  "anchor_time": 1725458400000,
  "anchor_price": 64000.00,
  "vwap_value": 64500.00,
  "bands": {
    "plus_1_sigma": 64700.00,
    "plus_2_sigma": 64950.00,
    "plus_3_sigma": 65200.00,
    "minus_1_sigma": 64300.00,
    "minus_2_sigma": 64050.00,
    "minus_3_sigma": 63800.00
  },
  "asset_class": "crypto"
}
```

σ is the Phase 1 volume-weighted variance:
`sqrt( Σ v_i (p_i − VWAP)² / Σ v_i )`.

Volume-profile wire JSON:

```json
{
  "symbol": "BTCUSDT",
  "session_type": "ny_am",
  "high_volume_nodes": [{"price": 65000.00, "volume": 1500.5}],
  "low_volume_nodes": [{"price": 64900.00, "volume": 200.0}],
  "poc": 65000.00,
  "timestamp": 1725459000000
}
```

POC = max-volume price bin. HVN = local maxima ≥ mean bin volume (POC always
included). LVN = local minima ≤ mean (never the POC). Tick sizes: BTC `$5`,
ETH `$1`, AAPL `$0.05`, ES `$0.25` (overridable).

Kill-zone events (Kafka `kill_zone_events` + Redis `kill_zone:{symbol}`):

```json
{
  "symbol": "BTCUSDT",
  "kill_zone": "ny_am",
  "start_time": 1725458400000,
  "end_time": 1725462000000,
  "active": true,
  "asset_class": "crypto"
}
```

Crypto windows are the Phase 1 UTC sessions (Asia 00:00–07:00, London
07:00–13:30, NY AM 13:30–15:00, NY PM 18:00–20:00). Equities use RTH/ETH;
futures use RTH/Globex. Redis `kill_zone:{symbol}` stores the **primary**
window (RTH over ETH). `kill_zone:active:{asset_class}` is the class-level
lookup (no `symbol` field).

### Prometheus

| Process | Scrape |
|---|---|
| API | `http://localhost:8000/metrics` |
| Pipeline | `http://localhost:9101/metrics` (compose) |
| Kill-zone timer | `http://localhost:9102/metrics` (compose) |

Series: `sniper_ticks_processed_total`, `sniper_avwap_updates_total`,
`sniper_avwap_compute_seconds`, `sniper_volume_profile_updates_total`,
`sniper_volume_profile_compute_seconds`,
`sniper_kill_zone_transitions_total`, `sniper_http_request_duration_seconds`,
`sniper_setup_detection_latency_seconds`, `sniper_setup_candidates_total`,
`sniper_setup_approved_total`, `sniper_setup_rejected_total`.

### Horizontal scaling

Workers are stateless: Kafka `raw_ticks` is keyed by symbol; Redis holds
anchor metadata, AVWAP sufficient statistics (`avwap:acc:…`), volume-profile
books, and the current kill zone. Run N pipeline replicas **partitioned by
symbol** so two workers never increment the same accumulator. The kill-zone
service is a single writer (compose `killzone`); it is idempotent on
`(symbol, kill_zone, start_time, active)` and reconciles Redis after each
tick. The API is a pure Redis reader/writer (anchor POST is fence-posted via
`avwap:index:{symbol}`).

In-memory demo (`sniper-data demo --inmemory --duration 5`) still runs the
kill-zone loop inside the pipeline (`KILLZONE_INPROCESS=true`). Compose sets
that to `0` and runs `sniper-data killzones` as its own service.
