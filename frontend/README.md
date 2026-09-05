# SniperTrader Dashboard — Conviction Terminal (Rev. 1.1)

Next.js (App Router) port of the live **stock_picks.html** layout language
(sections 01–08) with Phase 2 Kronos overlays inside that chrome — not a
separate greenfield shell.

The UI runs **offline by default** on in-browser mock streams that emit the
exact JSON shapes in `/schemas`. Flip one env var to point at live
`ws://localhost:8000` **after** the Quant Risk Pre-Filter checklist gate.

## Setup (local paper preview)

The **repo-root Vercel project is the static marketing site**. It does **not**
serve this Next.js app. PR previews of the marketing project will 404 `/` as
the Conviction Terminal. Use one of the paths below.

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

### Dual deploy path (do not flip production marketing)

| Path | What it serves | How |
|---|---|---|
| **Marketing (existing)** | Static HTML at repo root (`stock_picks.html`, …) | Root `vercel.json` · Root Directory = `.` · **leave this on the live snipertrader.ai project** |
| **Dashboard (this app)** | Next.js Conviction Terminal | New Vercel project · Root Directory = `frontend` · uses `frontend/vercel.json` |

```bash
# Preview this app without touching the marketing project:
cd frontend
npx vercel            # preview URL for the Next dashboard
# or: Vercel Dashboard → Project Settings → Root Directory = frontend
```

`frontend/vercel.json` is scoped to that project only. Do **not** change the
marketing project's Root Directory to `frontend` — that would unpublish the
static site.

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
| `NEXT_PUBLIC_WS_BASE` | `ws://localhost:8000` | Data Eng WebSocket origin. Pattern overlays go live only when this is set **and** `USE_MOCKS=false`. |
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

- `GET /signals?symbol=&status=&setup_type=&from_ts=&to_ts=&limit=&cursor=` →
  `{ "items": [ Signal ], "next_cursor": string|null }`
  History is this same list (no separate history endpoint).
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

ML PR #7 overlay-focus views (card click → highlight `trigger_event_ids` only):

| setup_type | trigger_event_ids |
|---|---|
| `sweep_reclaim` | `[sweep.id, mss.id]` |
| `fvg_entry` | `[fvg.id, ...overlapping ob.ids]` — OB is never its own `setup_type` |
| `po3_judas` | `[sweep.id]` (no MSS) |

Parse-only (no overlay-focus view): `mss_break`, `order_block`, `sweep_mss`. Dropped: `*_pending_user_confirm`.

PR #9 / Quant explainability: `contributing_factors: string[]` (publish-only;
unknown ids are kept) + `factor_breakdown: {name, weight, score, note?}[]`
with `sum(score)` ≈ conviction.

Close fields are **live on Quant PR #2** (`GET /signals`, `GET /signals/{id}`,
WS `signal.upsert` / `signal.status`). Do **not** compute on FE — display the
payload:

- `realized_r`: `number | null` — null on ACTIVE/CANCELLED; signed R on TP_HIT/SL_HIT
- `exit_price`: `number | null` — same lifecycle
- `closed_ts_ms`: `number | null` — UTC ms, same lifecycle

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
| realized_r | Quant payload (`—` while null) |
| exit_price | Quant payload (`—` while null) |
| closed_ts_ms | Quant payload UTC ms (`—` while null) |

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
  "realized_r": null,
  "exit_price": null,
  "closed_ts_ms": null,
  "contributing_factors": ["liquidity_sweep", "mss", "vwap_reclaim"],
  "factor_breakdown": [
    { "name": "liquidity_sweep", "weight": 15, "score": 30, "note": "..." }
  ]
}
```

Mocks emit this exact REST list and WS envelope. Raw `fvg_zone` / `sweep_event`
Kafka stubs stay with Data Engineering — they are not table rows.

## Phase 2 — Setup visualization & real-time display

Layout lock stays on `stock_picks.html`. Phase 2 sits inside that chrome.

### Setup signal cards

Newest `ACTIVE` Quant rows render as a card strip (symbol, color-coded
`setup_type`, LONG/SHORT, entry / stop / target, planned R:R, conviction %,
UTC timestamp). Click → scroll the Kronos chart and apply that row’s
`trigger_event_ids` annotations plus entry/stop/target lines.

### Pattern overlays (`/schemas`, schema_version `"1.1"`)

Types copy `/schemas/sweep_event.schema.json`, `fvg_zone.schema.json`,
`mss_event.schema.json`, `order_block.schema.json`, `session_levels.schema.json`
— no extra Kafka fields. Chart draw mapping (ML Researchers Rev 1.1):

| Kind | Kafka | Redis | Draw |
|---|---|---|---|
| FVG / OB | `fvg_zones` / `order_block_zones` | `fvg\|ob:{symbol}:{id}` | primitive zone: `t0=created_ts_ms`, `t1=now` or freeze when `mitigated`; `high`/`low` from payload; color by `direction`; dim if mitigated; join on `id` |
| Sweep | `sweep_events` | `sweep:{symbol}:{id}` | `setMarkers`: `time=ts_ms`, `price=swept_level`; `sell`→high/arrowDown, `buy`→low/arrowUp; emphasize `confirmed`; optional `Δ` when `delta_divergence` |
| MSS | `mss_events` | `mss:{symbol}:{id}` | level at `broken_level`, marker at `ts_ms`; optional swing→break segment; join highlight via `trigger_sweep_id` |
| Setup | Quant `GET /signals` | — | Quant / ML PR #7 fields; join patterns via `trigger_event_ids[]` only (null on wire → `[]`); click card → highlight those overlay ids |

**FE-only Overlay DTO** (`src/lib/types.ts` `Overlay`, normalized in
`src/lib/draw.ts` `normalizeOverlays`) — not a Kafka shape:

```ts
type Overlay =
  | { kind:"zone"; source:"fvg"|"ob"; id; symbol; t0; t1; high; low; direction; mitigated?:boolean }
  | { kind:"marker"; source:"sweep"|"mss"; id; symbol; time; price; side?:string; direction?:string }
  | { kind:"session_box"; source:"asia"; symbol; t0; t1; high; low }
  | { kind:"setup"; id; symbol; setup_type; side; time; entry; stop; target; trigger_event_ids:string[]; confidence?:number }
```

Zones use `PatternZonesPrimitive`. Points use `setMarkers` (time-asc, one per
timestamp). Overlay sockets match VWAP / DE PR #5: on connect the server
SCANs Redis `{prefix}:{symbol}:*` then follows `{prefix}:{symbol}`. Frames
are **raw** `/schemas` 1.1 JSON — no `{type, payload}` envelope.

```js
const ws = new WebSocket("ws://localhost:8000/v1/ws/sweep?symbol=BTCUSDT");
ws.onmessage = (e) => JSON.parse(e.data);
```

`parseOverlayFrame(frame, hint)` + `PATTERN_WS` in `src/lib/overlays.ts`;
live client is `openPatternSockets` (`src/lib/patternWs.ts`). Sweep is
`side` + `swept_level` only.

### Setup-specific views

| View | setup_type | Chart |
|---|---|---|
| Setup 1 | `sweep_reclaim` | sweep + MSS + horizontal `ref_vwap` (Quant `ref_vwap` or session VWAP) + entry/stop/target. Highlight `sweep` + `mss` in `trigger_event_ids` |
| Setup 2 | `fvg_entry` (preset `fvg_ob`) | FVG rect + overlapping OB via `trigger_event_ids` / `order_block` factor + VWAP and/or HVN from `volume_profile` + confirm marker at entry |
| Setup 3 | `po3_judas` | Asia session box (`high`/`low`/`session_start_ms`→`session_end_ms` from `session:{symbol}:asia` / `GET /v1/session/{symbol}/asia`) + Asia-extreme sweep + displacement at entry + kill-zone shade when `active`. Highlight the sweep id only |

Setups 4–6 keep the Phase 1 overlays (σ fade, pullback, AVWAP+OB).

Active setup tab / card filter is an **allow-list**. `sweep_reclaim` never
draws FVG, OB, or DISP. `fvg_entry` never draws sweep / MSS / Asia / kill-zone.
`ob_fvg` is not a `setup_type`.

### Signal history

History is **`GET /signals`** with `from_ts`/`to_ts` + `status`/`setup_type`/`symbol`.
No `/signals/history`. Columns: outcome (`status`), `realized_r`, `exit_price`,
`closed_ts_ms` from the Quant payload (`—` while null). Same fields on
`GET /signals/{id}` and WS `signal.status` / `signal.upsert`. CSV uses those
field names.

### Real-time

- Quant `WS /ws/signals` → card strip + tables (`signal.upsert` / `signal.status`)
- Data Eng PR #5 `WS /v1/ws/sweep|fvg|mss|ob?symbol=` → pattern book
  (server seed SCAN, then pub/sub; raw schema 1.1 frames)
- Toast when `confidence > 0.8`
- Sound toggle **off** by default

Pattern sockets prefer **live** when `NEXT_PUBLIC_WS_BASE` is set **and**
`NEXT_PUBLIC_USE_MOCKS=false`. Otherwise the in-browser mock fallback emits
the same raw frames. See https://github.com/fuserleertec/snipertrader/pull/5

### Data Eng Phase 2 (optional, non-blocking)

Clients exist for PR #5: `GET/WS /v1/avwap`, `/v1/volume-profile`,
`/v1/kill-zone`, and pattern overlay sockets
`WS /v1/ws/sweep|fvg|mss|ob?symbol=`. AVWAP (`vwap_value`) maps onto the
existing VWAPValues chart shape. Volume-profile HVN lines draw on the
`fvg_entry` / all-overlays views. Kill-zone shade draws on `po3_judas` when
`active`. Asia box prefers `GET /v1/session/{symbol}/asia`
(`session:{symbol}:asia`).

## Theme

Dark / light toggle uses `body.light` + `body.light-mode` and the SniperTrader
green-cyan tokens (`--emerald`, `--cyan`, `--gold`, `--obs*`).
