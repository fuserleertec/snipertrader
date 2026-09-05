# Detection performance template vs KPIs

**Phase 4 prep.** Weekly scorecard for setups 1–6 on the **paper /
continuous book** only. **`live_trading` remains `false`.** Fill this sheet
after the Quant paper-vs-walk-forward report. Do not treat E2E fixtures as
KPI evidence.

## KPIs (locked targets)

| KPI | Target | Notes |
|---|---|---|
| Signal accuracy | **&gt; 60%** | `paper_wins / (paper_wins + paper_losses)` among **published** paper fills. Unresolved excluded. |
| False positive rate | **&lt; 30%** | `paper_losses / published` (published-then-invalid). Unresolved excluded from the denominator only if PM agrees; default is **exclude unresolved**. |
| Quality signals / day | **2–5** | See assumption below. |

### Signals-per-day assumption (document this every week)

**Default assumption for this template:** **2–5 quality published signals per
day across the paper book** (`DEMO_SYMBOLS` = `BTCUSDT,AAPL,ES`), not per
symbol.

- Quality = published (`approved: true` → `setup_signals`) **and** conviction
  ≥ `min_conviction_for(setup_type)` (already true of published rows) **and**
  not `unresolved` within the week.
- If Quant / PM switch to **per symbol**, write that in the week's `notes`
  and keep the same 2–5 band **per symbol**. Do not mix grains in one sheet.
- Days = session days with at least one closed paper bar for that symbol
  (crypto: 7; equity/futures: RTH weekdays). Divide week totals by those days.

Per-setup signals/day is a **diagnostic**, not a second KPI, unless one
`setup_type` is 0 for the whole week (then escalate as a starve, not an FPR).

## Sheet columns

Copy one row per `(week, setup_type)`. Add a `ALL` roll-up row at the bottom.

| Column | Meaning |
|---|---|
| `week` | ISO week `YYYY-Www` (UTC Monday start) |
| `setup_type` | `sweep_reclaim` · `fvg_entry` · `po3_judas` · `sd_extension_fade` · `vwap_pullback_cont` · `avwap_ob_confluence` · `ALL` |
| `published` | Count of `setup_signals` with `id` that week |
| `approved` | Risk `approved: true` (equals `published` in this pipeline) |
| `paper_wins` | Published paper fills that hit target before stop |
| `paper_losses` | Published paper fills that hit stop first (or invalid outcome) |
| `accuracy` | `paper_wins / (paper_wins + paper_losses)` — blank if no resolved fills |
| `FPR` | `paper_losses / published_resolved` (see compute) |
| `signals/day` | Quality published / session-days (book or per-symbol — state which) |
| `conviction avg` | Mean log `conviction` (0–100) on **published** rows, not wire `confidence` |
| `notes` | Session / kill-zone / factor slice that drove the miss; OOS vs synthetic |
| `retune_action` | `none` · `propose` · `no-ship` · `escalate` — never `auto-apply` |

### Blank weekly table

```markdown
| week | setup_type | published | approved | paper_wins | paper_losses | accuracy | FPR | signals/day | conviction avg | notes | retune_action |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 2026-W36 | sweep_reclaim |  |  |  |  |  |  |  |  | book=3 symbols; live_trading=false | none |
| 2026-W36 | fvg_entry |  |  |  |  |  |  |  |  |  |  |
| 2026-W36 | po3_judas |  |  |  |  |  |  |  |  |  |  |
| 2026-W36 | sd_extension_fade |  |  |  |  |  |  |  |  |  |  |
| 2026-W36 | vwap_pullback_cont |  |  |  |  |  |  |  |  |  |  |
| 2026-W36 | avwap_ob_confluence |  |  |  |  |  |  |  |  |  |  |
| 2026-W36 | ALL |  |  |  |  |  |  |  |  | grain=book |  |
```

Optional diagnostic columns (keep off the KPI roll-up): `rejected`,
`skipped_conviction`, `deduped`, `reject_wrong`, `reject_correct`,
`unresolved`, `fn_missed_quality`.

## How to compute (paper + validate logs)

All joins follow [false_signal_analysis_plan.md](./false_signal_analysis_plan.md).
Paper fills only. **`live_trading` is false.**

### Inputs

1. **Published set** — Kafka `setup_signals` (or `Orchestrator.approved_log`)
   for the UTC week. Fields: `id`, `setup_type`, `symbol`, `side`, `ts_ms`,
   `confidence`, `trigger_event_ids`, `contributing_factors`,
   `factor_breakdown`.
2. **Validate logs** — each `POST /risk/validate` call + response
   (`approved`, `reason`). Body has no `id` and no factors; join on
   `symbol + ts_ms + setup_type + side + trigger_event_ids`.
3. **Pre/post logs** — `pre_filter_log` / `post_filter_log` / skip-conviction
   lines (`cand.log_fields()` includes `conviction`, `kill_zone`, factors).
4. **Paper fills** — Quant continuous paper book keyed by signal `id`.
   If a fill is missing, replay `entry`/`stop`/`target` on Timescale
   `ohlcv_bars` (preferred over synthetic).
5. **Quant metrics** — `GET /performance/summary` keys
   `1_sweep_reclaim` … `6_avwap_ob_confluence` as a cross-check, not a
   replacement for the join.

### Formulas

```
published          = count(setup_signals in week)
approved           = count(validate.approved == true)   # should == published
rejected           = count(validate.approved == false)
skipped_conviction = count(post-filter conviction < min_conviction_for(type))
deduped            = pre_filter - post_filter

resolved           = paper_wins + paper_losses
accuracy           = paper_wins / resolved              # require resolved ≥ 1
FPR                = paper_losses / resolved            # published-then-invalid
                     # equivalent to paper_losses / published when unresolved = 0

signals_per_day    = quality_published / session_days
                     quality_published = published - unresolved
                     session_days      = book days (default) or symbol days

conviction_avg     = mean(log.conviction) on published
                     # or 100 * mean(wire.confidence) if logs were dropped

reject_wrong       = rejected_or_skipped AND counterfactual paper win
reject_correct     = rejected_or_skipped AND counterfactual paper loss/invalid
FN                 = missed quality setup (see analysis plan)
```

`OrchestratorStats.false_positive_rate` (`rejected / (approved+rejected)`) is
the **risk-gate** reject share. It is **not** the KPI FPR. KPI FPR is
outcome-based on the paper book.

Minimum sample: if `resolved < 5` for a setup_type, mark `accuracy` / `FPR`
as `n/a` and put `small-n` in `notes`. Small-n weeks do **not** count toward
the two-week escalation streak unless PM overrides.

### Worked check

Week with 10 published, 7 wins, 2 losses, 1 unresolved:

- `accuracy = 7/9 = 77.8%` → pass (&gt; 60%)
- `FPR = 2/9 = 22.2%` → pass (&lt; 30%)
- `signals/day` (book, 5 equity days): if those 9 quality prints are the
  whole book, `9/5 = 1.8` → **miss** the 2–5 band (starve). Crypto-only weeks
  use 7 days.

## Escalation

A **KPI miss** is any of:

- `accuracy ≤ 60%` (or `n/a` with PM override)
- `FPR ≥ 30%`
- `signals/day` &lt; 2 or &gt; 5 on the agreed grain (`ALL` row)

### Two consecutive weeks

If the **same KPI** misses on the **same `setup_type`** (or on `ALL`) for
**two consecutive ISO weeks**:

1. Set `retune_action = escalate` on both rows.
2. ML files a change-log proposal
   ([weekly_tune_cadence.md](./weekly_tune_cadence.md)) — knob delta first,
   pattern variation only if the
   [pattern_variation_backlog.md](./pattern_variation_backlog.md) gate
   matches.
3. Quant attaches paper-vs-walk-forward drift and reject-reason mix.
4. PM decides `ship` / `no-ship` / `trial-paper-only`.
5. **Do not auto-apply** `SETUP_*` defaults. **Do not enable live trading.**

Non-consecutive misses reset the streak. Changing the signals/day grain
mid-streak resets that KPI's streak (note it).

### What escalation is not

- Not a live-book halt (there is no live book).
- Not permission to merge without PM.
- Not a green light to implement backlog variations that lack a paper gate.

## Header to paste above each week's sheet

```markdown
# Detection KPI — week YYYY-Www
Book: paper / continuous (Timescale OOS)
Symbols / grain: BTCUSDT,AAPL,ES — signals/day = **book** (2–5)
live_trading: false
Walk-forward report: <link>
False-signal tables: <link>
PM: <name>
```
