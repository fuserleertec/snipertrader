# SniperTrader Dashboard — Frontend Phase 1 (Rev. 1.1)

Next.js (App Router) + TypeScript + Tailwind dashboard for the Data Engineering
Phase 1 contracts. Lives in `frontend/` beside the static site and
`data_engineering/` Python pipeline.

The UI runs **offline by default** on in-browser mock streams that emit the
exact JSON shapes in `/schemas`. Flip one env var to point at live
`ws://localhost:8000`.

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

`NEXT_PUBLIC_USE_MOCKS=false npm run dev` talks to the Data Eng API
(`docker compose up` in `data_engineering/`).

## Layout

- **Header** — symbol selector (uppercase, no hyphens, e.g. `BTCUSDT`), timeframe
  pills (`1m` `5m` `15m` `1h` `4h`), last price, mock/live status, theme toggle
- **Sidebar** — VWAP anchor (`session` | `weekly` | `rolling`), session-level
  filters, Quant `setup_type` / `status` filters
- **Main chart** — TradingView Lightweight Charts v4 candlesticks
- **Setup cards** — ACTIVE Quant signals at the top; click joins overlays via `trigger_event_ids`
- **Pattern overlays** — FVG / order-block zones, sweep arrows, MSS broken levels (Rev. 1.1)
- **Bottom table** — history filters + CSV; toast when `confidence > 0.8`

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
| `NEXT_PUBLIC_USE_MOCKS` | `true` | In-browser streams. Set `false` for live API. |
| `NEXT_PUBLIC_WS_BASE` | `ws://localhost:8000` | Data Eng WebSocket origin (`/v1/ws/*`) |
| `NEXT_PUBLIC_HTTP_BASE` | `http://localhost:8000` | Data Eng HTTP. Same-origin `/v1/*` is rewritten here. |
| `NEXT_PUBLIC_QUANT_HTTP_BASE` | `http://localhost:8000` | Quant REST (`/signals`). Same-origin `/signals` is rewritten here. |
| `NEXT_PUBLIC_QUANT_WS_BASE` | `ws://localhost:8000` | Quant planned WS (`/ws/signals`) |

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

### Session levels — HTTP live; WS draft

HTTP: `GET /v1/session/{symbol}/{session_type}`, `GET /v1/session/{symbol}`

Draft WS: `WS /v1/ws/session?symbol=BTCUSDT`

Frame (`session_levels`): `schema_version`, `symbol`, `asset_class`,
`session_type` ∈ `asia|london|ny_am|ny_pm|rth|eth|globex`,
`session_start_ms`, `session_end_ms`, `open`, `high`, `low`, `close`,
`volume`, `updated_ts_ms`.

Plotted as price lines (O/H/L/C) for checked sessions.

### OHLC — WS draft

Draft WS: `WS /v1/ws/ohlcv?symbol=BTCUSDT&timeframe=1m`

`timeframe` ∈ `1m|5m|15m|1h|4h`

Frame (`ohlcv_bar`): `schema_version`, `symbol`, `asset_class`, `timeframe`,
`open_ts_ms`, `close_ts_ms`, `open`, `high`, `low`, `close`, `volume`, `n_ticks`.

Every frame is treated as a **closed** bar unless `closed: false` is present
(optional, not in the current schema). Planned history:
`GET /v1/ohlcv/{symbol}?timeframe=1m&limit=200` — mocks use this shape.

### Signals — Quant Developers (provisional)

Quant owns **setup/trade signals** (post risk-approval), **not** raw sweep/FVG
pattern streams.

REST:

- `GET /signals?symbol=&status=&setup_type=&from_ts=&to_ts=&limit=` →
  `{ "items": [ Signal ], "next_cursor": string|null }`
- `GET /signals/{id}` → `Signal`

Planned WS: `WS /ws/signals` →
`{ "type": "signal.upsert"|"signal.status", "signal": Signal }`

Table columns map 1:1 to Signal fields:

| Column | Field |
|---|---|
| Timestamp | `ts_ms` (UTC ms) |
| Symbol | `symbol` |
| Pattern Type | `setup_type` ∈ `sweep_reclaim` \| `fvg_entry` \| `mss_break` \| `order_block` \| `sweep_mss` \| `ob_fvg` |
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
  "trigger_event_ids": ["..."]
}
```

Mocks emit this exact REST list and WS envelope. Raw `fvg_zone` / `sweep_event`
Kafka stubs stay with Data Engineering — they are not table rows.

## Theme

Dark / light toggle uses `body.light` + `body.light-mode` and the SniperTrader
green-cyan tokens (`--emerald`, `--cyan`, `--gold`, `--obs*`).
