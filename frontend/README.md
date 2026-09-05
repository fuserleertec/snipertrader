# SniperTrader Dashboard — Conviction Terminal (Rev. 1.1)

Next.js (App Router) port of the live **stock_picks.html** layout language
(sections 01–08) with Phase 2 Kronos overlays inside that chrome — not a
separate greenfield shell.

The UI runs **offline by default** on in-browser mock streams that emit the
exact JSON shapes in `/schemas`. Flip one env var to point at live
`ws://localhost:8000` **after** the Quant Risk Pre-Filter checklist gate.

## Setup

```bash
cd frontend
cp .env.example .env.local   # optional; mocks are the default
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

From the repo root:

```bash
npm run dev:dashboard
```

`NEXT_PUBLIC_USE_MOCKS=false npm run dev` talks to Data Eng (`:8000`) and
Quant (`:8001`). Quant local:

```bash
cd quant && sniper-quant api --inmemory --port 8001
# docs: http://localhost:8001/docs
```

## Layout (locked to `/stock_picks.html`)

- **01 Header** — “Quantitative Market Intelligence Conviction Terminal” + LIVE
  strip (Next Refresh ET, Data Age, Heartbeat, Health, REFRESH / SHARE / DOWNLOAD)
- **02 Quantum Ensemble Picks** — provenance table (#, Asset, Signal, Last/Chg,
  Target, Conviction, Engines K/S/M/F/Q, Why). Setup Signals tab is Quant
  `setup_signals` (filters + CSV; sound off by default)
- **03 Live Market Simulation View** — Conviction & Velocity Leaderboard,
  MiroFish swarm heatmap, Kronos Structural K-Line (FVG / OB / sweep / MSS),
  Scenario Probability Matrix
- **04 Categorized Stock Picks** — All / Ultra-High / High / Watchlist cards
- **05 Narrative & Volatility Injectors**
- **06 Execution & Position Management**
- **07 Recon Audit**
- **08 Understanding the Engine**

Card/table click joins chart overlays via `trigger_event_ids`.

## Chart (performance)

- `lightweight-charts` **v4.x**: `createChart` + candlestick series
- VWAP **mean** is a single `createPriceLine`
- ±1/2/3σ **bands** are one custom canvas primitive (`VwapBandsPrimitive`) —
  not six extra series
- Session OHLC (open / high / low / close) are price lines for the sessions
  checked in the sidebar
- History is `setData` once; live ticks use `series.update`

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_USE_MOCKS` | `true` | In-browser streams. Set `false` for live Data Eng + Quant. |
| `NEXT_PUBLIC_WS_BASE` | `ws://localhost:8000` | Data Eng WebSocket origin (`/v1/ws/*`) |
| `NEXT_PUBLIC_HTTP_BASE` | `http://localhost:8000` | Data Eng HTTP. Same-origin `/v1/*` is rewritten here. |
| `NEXT_PUBLIC_QUANT_API_BASE` | `http://localhost:8001` | Quant REST (`/signals`, `/performance/summary`). Same-origin paths rewrite here. |
| `NEXT_PUBLIC_QUANT_WS_BASE` | `ws://localhost:8001` | Quant WS (`/ws/signals`) |

`NEXT_PUBLIC_QUANT_HTTP_BASE` is accepted as an alias of `QUANT_API_BASE`.

Mock → live is **env-only**. Market-data clients talk to Data Eng; signal
clients talk to Quant. Bases are independently configurable.

## Data contracts — `schema_version` `"1.1"`

All times are **UTC milliseconds**. Symbols are **uppercase, no hyphens**.
One WebSocket connection = one symbol; reconnect (new URL) to change symbol.
Subscribe is **query-param only** — no multiplexed subscribe JSON yet.

Canonical JSON Schema: [`/schemas`](../schemas/README.md).

### VWAP — LIVE

`WS /v1/ws/vwap?symbol=BTCUSDT`

HTTP: `GET /v1/vwap/{symbol}?anchor=session|weekly|rolling`

Frame (`vwap_values`):

```json
{
  "schema_version": "1.1",
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "anchor_type": "session",
  "session_type": "london",
  "anchor_start_ms": 0,
  "lookback_periods": null,
  "vwap": 99.666,
  "sigma": 1.795,
  "band_m3": 94.28,
  "band_m2": 96.07,
  "band_m1": 97.87,
  "band_p1": 101.46,
  "band_p2": 103.25,
  "band_p3": 105.05,
  "cum_volume": 1000,
  "n_obs": 20,
  "updated_ts_ms": 1710000000000
}
```

Mean = `vwap`. Bands: `band_p1`/`band_m1` (±1σ), `p2`/`m2` (±2σ), `p3`/`m3` (±3σ).
σ is volume-weighted: `sqrt(Σ vᵢ (pᵢ − VWAP)² / Σ vᵢ)`.

### Session levels — LIVE (PR #1)

HTTP: `GET /v1/session/{symbol}/{session_type}`, `GET /v1/session/{symbol}`

`WS /v1/ws/session?symbol=BTCUSDT` — seeds `session:{symbol}:*` snapshots, then
pub/sub on `session:{symbol}`. Query-param subscribe only.

Frame (`session_levels`): `schema_version`, `symbol`, `asset_class`,
`session_type` ∈ `asia|london|ny_am|ny_pm|rth|eth|globex`,
`session_start_ms`, `session_end_ms`, `open`, `high`, `low`, `close`,
`volume`, `updated_ts_ms`.

### OHLCV — LIVE (PR #1)

`WS /v1/ws/ohlcv?symbol=BTCUSDT&timeframe=1m` — **`timeframe` is required**
(`1m|5m|15m|1h|4h`). Seeds last N closed bars, then pub/sub
`ohlcv:{symbol}:{timeframe}`. Frames may include `buy_volume` / `sell_volume`.

`GET /v1/ohlcv/{symbol}?timeframe=1m&limit=200` — history bootstrap
`{ symbol, timeframe, bars }`.

Frame (`ohlcv_bar`): `schema_version`, `symbol`, `asset_class`, `timeframe`,
`open_ts_ms`, `close_ts_ms`, `open`, `high`, `low`, `close`, `volume`, `n_ticks`,
optional `buy_volume` / `sell_volume`.

Every frame is treated as a **closed** bar unless `closed: false` is present.

These endpoints are **production-ready** on Data Eng `:8000`. Keep mocks for
offline. Set `NEXT_PUBLIC_USE_MOCKS=false` and
`NEXT_PUBLIC_WS_BASE=ws://localhost:8000` only after the Quant Risk Pre-Filter
checklist gate.

### Signals — Quant OpenAPI (PR #2, live)

Quant owns **setup/trade signals** (post risk-approval), **not** raw sweep/FVG
pattern streams. REST base `http://localhost:8001`. Docs: `/docs`.

REST:

- `GET /signals?symbol=&status=&setup_type=&side=&from_ts=&to_ts=&limit=&cursor=` →
  `{ "items": [ Signal ], "next_cursor": string|null }`
- `GET /signals/history` — same list + filters (history alias)
- `GET /signals/{id}` → `Signal`
- `GET /performance/summary` → Quant PR #2 at `:8001` (flat envelope +
  `by_setup` product keys). Same-origin rewrite, then mock fallback.

`cursor` is the opaque token from the previous page's `next_cursor`.
`limit` default 50 (1–500). Auth `X-API-Key` is optional (off by default).

Locked `setup_type` ↔ `by_setup` product key:

| setup_type | by_setup |
|---|---|
| `sweep_reclaim` | `1_liquidity_sweep_vwap_reclaim` |
| `fvg_entry` | `2_fvg_mitigation_vwap` |
| `po3_judas` | `3_po3_asia_range_sweep` |
| `sd_extension_fade` | `4_sd_extension_fade` |
| `vwap_pullback_cont` | `5_vwap_pullback_cont` |
| `avwap_ob_confluence` | `6_avwap_ob_confluence` |

Dropped from UI: `mss_break`, `order_block`, `sweep_mss`, `ob_fvg`, `*_pending_user_confirm`.

PR #9 / Quant explainability: `contributing_factors: string[]` (publish-only;
unknown ids are kept) + `factor_breakdown: {name, weight, score, note?}[]`
with `sum(score)` ≈ conviction. Closed rows may include `realized_r`,
`exit_price`, `closed_ts_ms`.

Overlays 4–6: ±2σ/±3σ + rejection + session VWAP target; pullback shade + OB/FVG; AVWAP + OB confluence.

Phase 3 pages: `/analytics`, `/alerts`, `/account`. Auth + alerts are **localStorage mocks** (Quant has no alerts/SSO API yet). Cumulative P&L on analytics is a **stub polyline**, not an API field. Web Push is stubbed (no VAPID).

Live WS: `ws://localhost:8001/ws/signals` →
`{ "type": "signal.upsert"|"signal.status", "signal": Signal }`
(`signal.upsert` on POST /signals; `signal.status` on PATCH / lifecycle close).

Table columns map 1:1 to Signal fields:

| Column | Field |
|---|---|
| Timestamp | `ts_ms` (UTC ms) |
| Symbol | `symbol` |
| Pattern Type | `setup_type` ∈ `sweep_reclaim` \| `fvg_entry` \| `po3_judas` \| `sd_extension_fade` \| `vwap_pullback_cont` \| `avwap_ob_confluence` |
| Direction | `side` ∈ `long` \| `short` |
| Zone | `{ entry, stop, target }` (UI also derives `zone_low`/`zone_high` from stop/entry) |
| Status | `ACTIVE` \| `TP_HIT` \| `SL_HIT` \| `CANCELLED` |

```json
{
  "id": "string",
  "ts_ms": 0,
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "setup_type": "sweep_reclaim",
  "side": "long",
  "entry": 0,
  "stop": 0,
  "target": 0,
  "status": "ACTIVE",
  "confidence": 0.8,
  "timeframe": "5m",
  "ref_session": "ny_am",
  "trigger_event_ids": ["..."],
  "contributing_factors": ["liquidity_sweep", "mss", "vwap_reclaim"],
  "factor_breakdown": [
    { "name": "liquidity_sweep", "weight": 15, "score": 30, "note": "..." }
  ]
}
```

Mocks emit this exact REST list and WS envelope. Raw `fvg_zone` / `sweep_event`
Kafka stubs stay with Data Engineering — they are not table rows.

## Theme

Dark / light toggle uses `body.light` + `body.light-mode` and the SniperTrader
green-cyan tokens (`--emerald`, `--cyan`, `--gold`, `--obs*`).
