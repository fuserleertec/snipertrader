# False-signal analysis plan (paper / continuous book only)

**Phase 4 prep.** Analyze published and rejected setup candidates against
**paper fills** and the continuous paper book. Do **not** run this study on a
live book. **`live_trading` remains `false`.** Recommended knob deltas are
logged only — never auto-applied.

## Scope

| In | Out |
|---|---|
| Paper / continuous book fills and Quant paper metrics | Live broker fills |
| `setup_signals` published after `approved: true` | Changing `live_trading` |
| Orchestrator pre / post risk-validate logs | Auto-merging `SETUP_*` defaults |
| Publish-only `contributing_factors` / `factor_breakdown` | Shipping new detectors |

Universe: setups 1–6 on the demo / paper symbols (`DEMO_SYMBOLS`, default
`BTCUSDT,AAPL,ES`). Cohort grain is **calendar week × `setup_type`**.

## Data sources

Join everything on `trigger_event_ids` (chart / zone ids) plus, after publish,
signal `id`. Factors are **labels**, not chart ids — do not treat a factor
name as a Redis key.

| Source | What it holds | Join keys |
|---|---|---|
| **Paper fills** (Quant paper / continuous book) | Entry, stop, target, exit, R, win/loss, MAE/MFE | signal `id`; fallback `symbol + ts_ms + setup_type + side` |
| **`setup_signals` Kafka** (approved only) | Published wire: `id`, `setup_type`, `side`, `confidence`, `entry`/`stop`/`target`, `trigger_event_ids`, `contributing_factors`, `factor_breakdown` | `id`; `trigger_event_ids` → Redis `sweep:` / `fvg:` / `mss:` / `ob:` / `avwap:` |
| **Pre-filter logs** (`Orchestrator.pre_filter_log` / `raw_log`) | Every candidate after `asyncio.gather`, before dedupe | `setup_type`, `symbol`, `side`, `ts_ms`, `trigger_event_ids`, `conviction` |
| **Post-filter logs** (`Orchestrator.post_filter_log`) | Survivors of the 300s dedupe window | same + conviction after kill-zone / volume / multi-pattern bonuses |
| **Risk validate logs** | `POST /risk/validate` body + `approved` / `reason` / `adjusted_position_size`. Body is the locked allow-list (no `id`, no factors, no `conviction`) | `symbol`, `ts_ms`, `setup_type`, `side`, `trigger_event_ids` |
| **Skip-conviction logs** | `conviction < min_conviction_for(setup_type)` — never sent to risk | same as pre-filter |
| **Quant paper metrics** | `GET /performance/summary` keys: `1_sweep_reclaim`, `2_fvg_entry`, `3_po3_judas`, `4_sd_extension_fade`, `5_vwap_pullback_cont`, `6_avwap_ob_confluence` (plus the weekly paper-vs-walk-forward report) | `setup_type` slug |
| **Explainability** | `contributing_factors` (stable ids) and `factor_breakdown` `{name, weight, score, note?}` with `sum(score) ≈ conviction` (0–100); wire `confidence = conviction / 100` | signal `id` (publish only) |
| **Session / kill zone** | `session_type` on the candidate; Redis `kill_zone:{symbol}`; log field `kill_zone` | `symbol`, `ts_ms` |

Prometheus proxies (not a substitute for paper outcomes):
`sniper_setup_candidates_total`, `sniper_setup_approved_total`,
`sniper_setup_rejected_total`. Rejects are the **risk-gate** false-positive
proxy; paper fills decide **outcome** false positives.

## Definitions

Outcomes are **paper-book only**. A candidate that never published has no
fill; reconstruct a *counterfactual* paper path from entry/stop/target on the
continuous book (Timescale OHLCV preferred).

| Term | Definition |
|---|---|
| **Published** | Risk returned `approved: true`; signal written to `setup_signals` with `id` and `status=ACTIVE`. |
| **Approved** | Same as published in this pipeline (approve ⇒ publish). Count from `approved_log` / Quant paper intake. |
| **Rejected** | Sent to `POST /risk/validate` and `approved: false` (or transport `risk_error:*`). Dropped; no `id`. |
| **Skipped** | Post-dedupe conviction below `SetupParams.min_conviction_for(setup_type)` (60 for S1–S5, 70 for S6). Never validated. |
| **Deduped** | Same `symbol + side` inside `SETUP_DEDUPE_WINDOW_SEC` (300s); loser is not validated. |
| **Valid paper outcome** | Continuous-book path from `entry` hits `target` before `stop` (paper win), or hits `stop` first (paper loss). Flat / time-stop / no-fill is **neither** — bucket as `unresolved`. |
| **False positive (FP)** | **Published**, then **invalid outcome**: paper loss, or structure invalidates before target (stop hit, reclaim fails, zone mitigated against the side). |
| **False negative (FN)** | **Missed quality setup**: not published (skipped, deduped, or reject-wrong) **and** the counterfactual paper path is a win at the locked R:R. Quality bar: would have met that week's min conviction **or** a human/PM tagged replay as a valid USME print. |
| **Reject-correct** | Risk rejected (or conviction-skipped) **and** the counterfactual paper path is a loss or unresolved-invalid. Gate did the right thing. |
| **Reject-wrong** | Risk rejected (or conviction-skipped) **and** the counterfactual paper path is a win. These feed FN and the knob-delta list (usually loosen a gate or raise a miss). |
| **True positive (TP)** | Published **and** paper win. |
| **True negative (TN)** | Not published **and** reject-correct. |

Do **not** count synthetic fixture wins from `sniper-data setups --e2e-report`
as paper outcomes. E2E is a handshake pack, not OOS.

## Method

### 1. Weekly cohort

Group by ISO week (UTC Monday 00:00 → Sunday 24:00) and `setup_type`:

| Setup | `setup_type` | Performance key |
|---|---|---|
| 1 | `sweep_reclaim` | `1_sweep_reclaim` |
| 2 | `fvg_entry` | `2_fvg_entry` |
| 3 | `po3_judas` | `3_po3_judas` |
| 4 | `sd_extension_fade` | `4_sd_extension_fade` |
| 5 | `vwap_pullback_cont` | `5_vwap_pullback_cont` |
| 6 | `avwap_ob_confluence` | `6_avwap_ob_confluence` |

Setup 2 is **`fvg_entry` only**. Overlapping OB is in `trigger_event_ids` +
factor `order_block`. Never join on `ob_fvg` (not on the wire).

### 2. Join

1. Start from post-filter candidates (and skipped-conviction rows).
2. Attach risk decision by `symbol + ts_ms + setup_type + side + trigger_event_ids`.
3. Attach published `id` from `approved_log` / `setup_signals`.
4. Attach paper fill by `id`; if missing, replay entry/stop/target on Timescale
   OHLCV (`ohlcv_bars` hypertables) — **not** on synthetic bars.
5. Expand `trigger_event_ids` to zone snapshots (Redis TTL ≤ 48h; after expiry
   use Kafka archive / Timescale if Quant persisted them).
6. Attach `contributing_factors` / `factor_breakdown` from the **published**
   signal only. Rejects have no breakdown on the validate body — use the
   pre/post log copies (those fields stay in `cand.log_fields()`).

### 3. Slices (required)

Every weekly table is sliced, not just rolled up:

| Slice | Buckets | Source |
|---|---|---|
| **Session** | `asia` · `london` · `ny_am` · `ny_pm` · `rth` · `eth` · `globex` | `session_type` / `ref_session` |
| **Kill zone** | active vs inactive; zone name when active | `kill_zone` log field; Redis `kill_zone:{symbol}` |
| **Conviction** | `below_gate` (< min for that setup); `60s` (60–69); `70s` (70–79); `80s` (80–89); `90s` (90–100) | log `conviction` (not wire `confidence`) |
| **Symbol / asset class** | `BTCUSDT` crypto · `AAPL` equity · `ES` futures (plus any paper extras) | candidate `symbol` |
| **Factor presence** | each stable id in `contributing_factors` | publish or log breakdown |

Stable factor ids: `liquidity_sweep`, `mss`, `fvg`, `order_block`,
`vwap_reclaim`, `vwap_band_extension`, `vwap_pullback`, `first_touch`,
`low_volume`, `volume_confirm`, `rejection_candle`, `engulfing`, `avwap`,
`htf_ob`, `kill_zone`, `multi_pattern`, `trend_align`.

### 4. Failure-mode ranking

For each `(week, setup_type, slice)` compute:

- `n_published`, `n_approved`, `paper_wins`, `paper_losses`, `unresolved`
- `accuracy = paper_wins / (paper_wins + paper_losses)` (ignore unresolved)
- `FPR = paper_losses / n_published` (published-then-invalid; see
  [detection_performance_template.md](./detection_performance_template.md))
- `reject_wrong_rate`, `reject_correct_rate`
- Top factor names among FPs vs TPs (mean `score` in `factor_breakdown`)
- Dominant reject `reason` among reject-wrong vs reject-correct

Rank failure modes by **paper R lost** (sum of losers' intended R), then by
count. Typical modes to score (do not treat as exhaustive):

- Sweep not confirmed / reclaim failed after publish (S1)
- Stale FVG (`SETUP2_MAX_FVG_AGE_HOURS`) or VWAP/HVN overlap too loose (S2)
- Judas displacement without a real ±1σ/±2σ tag (S3)
- Low-volume fade into news or high-ATR without ±3σ (S4; news feed is still a stub)
- Repeat VWAP touch counted as first-touch (S5)
- AVWAP line inside OB but HTF rejection was noise (S6)
- Dedupe dropped a higher-quality later print (check `deduped` vs FN)
- Conviction skip that later printed a paper win (FN / reject-wrong)

### 5. Knob deltas (recommend only)

Map each ranked mode to a **signed delta** on a named `SETUP_*` /
`SetupParams` field (see [weekly_tune_cadence.md](./weekly_tune_cadence.md)).
Write the recommendation in the weekly change log.

**Do not auto-apply.** Defaults stay at the Quant walk-forward lock until PM
signs a merge. Prefer Timescale OOS replay over synthetic fixtures when
estimating the delta.

## Outputs (weekly)

1. Cohort tables (week × setup_type × session × kill_zone × conviction bucket).
2. Ranked failure-mode list with counts, paper R, and example `id`s /
   `trigger_event_ids`.
3. Recommended knob deltas (field, old, proposed, evidence week, OOS note).
4. KPI row for [detection_performance_template.md](./detection_performance_template.md).
5. Escalation flag if accuracy or FPR miss two consecutive weeks.

## Explicit non-goals

- No live book. No live validate/publish sink.
- **`live_trading` remains `false`.**
- No code change to detectors, orchestrator, or risk allow-list as part of this
  analysis.
- No auto-write to `.env` / `SetupParams` defaults.
