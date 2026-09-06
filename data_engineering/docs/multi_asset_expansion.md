# Multi-asset expansion (paper only)

**Status:** paper / in-memory / preview. **`live_trading` remains `false`.**
This is not a live book and does not enable broker routing. Static site
untouched.

Stacks on Phase 3 setups 1–6 and Phase 4 prep docs. Setup 2 wire type is
always `fvg_entry` (never `ob_fvg` on `POST /risk/validate`).

## 15-minute paper scan

```bash
# Default provisional universe (includes ES, CL, GC, NQ)
sniper-data setups --inmemory --paper-scan --refresh-minutes 15 --cycles 1

# Explicit futures book
sniper-data setups --inmemory --paper-scan --universe ES,CL,GC,NQ --refresh-minutes 15 --cycles 1
```

`--inmemory --paper-scan` (or `--universe …`) rematerializes sweep / FVG /
pullback fixtures for each symbol, runs pattern detection + setups 1–6,
calls Quant `POST /risk/validate` (locked fields, **omit `id`**), then
publishes `setup_signals` only when `approved: true`. Cadence default is
**15 minutes** (universe / ensemble scan only). Setup 4 / Setup 5 do **not**
use that 15m clock as their bar timeframe. Use `--cycles 1` in CI; omit for
a long-running paper loop.

## Setup 4 / 5 continuous bars (DE PR #12)

`sd_extension_fade` and `vwap_pullback_cont` consume **continuous 1m and 5m**
bars only:

* Kafka `ohlcv_bars`
* `WS /v1/ws/ohlcv?timeframe=1m|5m`
* `GET /v1/ohlcv/{symbol}?timeframe=1m|5m`

They never read `dashboard_snapshots` or Redis `dashboard:snapshot:*`.
Those 15m envelopes are dashboard / ranking helpers, not detector OHLCV.

Existing `sniper-data setups --inmemory` is still the single-symbol BTCUSDT
fixture replay.

## Universe cutover (DE READY)

Detectors **swapped off** `SETUP_UNIVERSE`. Authoritative scan list:

`GET /v1/universe/top?limit=10|20` matching
[`universe_top.schema.json`](../../schemas/universe_top.schema.json):

```json
{
  "as_of_ts_ms": 0,
  "limit": 10,
  "symbols": [{ "symbol": "ES", "asset_class": "futures", "rank": 1, "score": 0.0 }]
}
```

| Priority | Surface | Role |
|---|---|---|
| 1 | `GET /v1/universe/top?limit=10\|20` | **Primary** ranked detector list |
| 2 | Redis `universe:top` | Cache of that envelope |
| 3 | Redis `universe:active` / `GET /v1/universe` | Full-list helpers `{symbol, asset_class}` |
| 4 | `SETUP_UNIVERSE` / `DASHBOARD_SYMBOLS` | Offline fallback **only** when DE HTTP/Redis are unreachable |

`resolve_scan_universe(provider, limit=20)` is the detector entry.
`UNIVERSE_HTTP_URL` points at the DE API. Default mix includes
**ES, NQ, CL, GC** plus crypto/equities (max 20). Per-symbol DE keys
are unchanged. `live_trading` stays `false`.

DE-owned HTTP (do not invent a second wire shape):

* `GET /v1/universe` — Redis `universe:active`
* `GET /v1/universe/top?limit=10|20` — Redis `universe:top`

## Ensemble ranking (P0) — dynamic, not hardcoded

Published `setup_signals` (after risk approval only):

| Field | Meaning |
|---|---|
| `ensemble_score` | 0–100 weighted score |
| `rank_components` | `{setup_quality, confluence, kill_zone, volume, freshness}` |
| `category` | `crypto` · `equity` · `futures` (P4 categorized picks) |
| `contributing_factors` | unchanged, publish-only |
| `factor_breakdown` | unchanged, publish-only |

Weights:

| Component | Weight | Input |
|---|---:|---|
| `setup_quality` | 0.40 | conviction (light R:R tilt) |
| `confluence` | 0.20 | factor count + session VWAP σ-extension |
| `kill_zone` | 0.15 | 100 if aligned, else 0 |
| `volume` | 0.15 | volume / delta confirm |
| `freshness` | 0.10 | recency inside the 15m window |

The top-10 is **recomputed** from those inputs for the active universe.
It is not a constant ticker table. Same inputs → same order (stable).
Change conviction / VWAP extension / kill-zone → order changes.

Kafka **`ensemble_features`**: 15-minute snapshot of the ranked book
(`weights`, `picks`, `universe`, `live_trading: false`).

In-memory / HTTP for FE:

* `GET /v1/picks/ensemble?limit=10` — Quant field map via `consume_picks_ensemble`
* helper `rank_top` / `EnsembleBook.top` (prefers Kafka `ensemble_features`)

### Map to Quant `GET /picks/ensemble`

| Quant / FE field | Source |
|---|---|
| `symbol` | `setup_signals.symbol` |
| `rank` | 1…N after sort |
| `score` | `ensemble_score` |
| `ensemble_score` | weighted 0–100 (raw components preserved) |
| `confidence` / `best_confidence` | published `confidence` (conviction/100) |
| `conviction` | same as `ensemble_score` (P0 display) |
| `signal` | `long`→`Buy`, `short`→`Sell` |
| `side` | `setup_signals.side` |
| `category` | `asset_class` / `category` |
| `setup_type` | wire slug (`fvg_entry`, never `ob_fvg`) |
| `entry` / `target` | published levels |
| `rank_components` | publish-only object (raw weights) |
| `contributing_factors` | publish-only labels |
| `active_levels` | `false` rows are skipped (`skip_reason`) |
| `id` / `ts_ms` | join keys |

Quant consumers prefer Kafka `ensemble_features` (15m / 900s snapshots with
`picks` + `signals` mirrors + `skipped`). Fallback: latest `setup_signals`
mirrors. `score` ← `ensemble_score`, `confidence` ← `best_confidence`;
`rank_components` and `contributing_factors` are passed through. Skip
`active_levels=false` / `skip_reason`.

Never send `ensemble_score`, `rank_components`, `category`,
`contributing_factors`, or `factor_breakdown` on `POST /risk/validate`.

## Inactive setups (do not emit)

Skip (log reason, no `setup_signals`) when the symbol has no usable DE
levels:

| Reason | When |
|---|---|
| `no_active_levels` | no session book and no FVG / OB / sweep keys |
| `no_active_zones` | session may exist; unmitigated FVG/OB/sweep missing |
| `mitigated_only` | zones exist but every FVG/OB/sweep is mitigated |

Scans `session:{symbol}:*`, `fvg:{symbol}:*`, `ob:{symbol}:*`,
`sweep:{symbol}:*` only.

## Signal History (P2)

`GET /v1/setup-signals/history` joins published rows to paper outcomes:

* `win` / `loss` / `unresolved` / `cancelled`
* Stub join: `PaperFillSource` / `StaticFillSource({id: outcome})`
* Quant paper fills plug in later by `id`, else
  `symbol + ts_ms + setup_type + side`
* Inactive / cancelled setups never appear (they were not published)

## Expected volume (KPI alignment)

Phase 4 prep KPI remains **2–5 quality published signals / day / symbol**
(or book-wide if PM keeps the 3-symbol grain — state the grain weekly).
The 20-symbol paper scan is allowed to emit **more raw candidates** so FE
history / picks have density; the **ensemble top-10 is book-wide**, not
10 per symbol.

Dedupe is unchanged: **same symbol + direction within 300s** → one winner
(highest conviction, else earliest `ts_ms`). Different symbols are **not**
collapsed.

## ES / CL / GC / NQ wiring

| Symbol | Paper generator (setups 1–6 rematerialized) |
|---|---|
| `ES` | sweep / Setup 1 `sweep_reclaim` + pattern sweep/FVG |
| `CL` | FVG / Setup 2 `fvg_entry` + pattern sweep/FVG |
| `GC` | pullback / Setup 5 `vwap_pullback_cont` |
| `NQ` | Judas / Setup 3 `po3_judas` |

Additional universe names cycle sweep → FVG → pullback → fade → Judas →
AVWAP+OB. Geometry is the locked fixture series, remapped to the symbol
and inferred `asset_class` (`futures` for these four).
