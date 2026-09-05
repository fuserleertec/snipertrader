# Pattern variation backlog (do not implement / ship)

**Phase 4 prep.** Ranked ideas for setups 1–6. **Do not implement or ship**
unless a named **paper drift** metric requires it and PM signs.
**`live_trading` remains `false`.** Status values: `backlog` ·
`blocked on paper` · `ready`.

`ready` means "ready to *design* a paper-only trial after the gate trips" —
not ready to merge onto a live book. Nothing in this list is scheduled.

## Status legend

| Status | Meaning |
|---|---|
| `backlog` | Hypothesis only. No paper evidence yet. Do not start. |
| `blocked on paper` | Needs a paper cohort / feed / Quant metric that does not exist yet. |
| `ready` | Gate metric is specified and last week's paper pack would justify a trial **if** PM asks. Still no code until sign-off. |

## Priority list

Priority is ML-research order (1 = first to consider **after** a gate trip).
Effort: S = one detector file + tests; M = detector + context/Redis; L =
new feed or multi-TF contract.

### P1 — Multi-TF MSS confirm (S1)

| Field | Value |
|---|---|
| Hypothesis | Requiring MSS on both `5m` and `15m` (or 15m confirm after 5m sweep) cuts S1 false positives from one-bar noise sweeps. |
| setup_type | `sweep_reclaim` |
| Risk | Signals/day fall below 2 on thin symbols; more FNs on fast crypto. |
| Effort | M — orchestrator already runs S1 on `SETUP1_TIMEFRAMES`; need a cross-TF join, not a new `setup_type`. |
| Gate | Paper S1 accuracy &lt; 60% **or** FPR ≥ 30% for **2 consecutive weeks**, with FP slice dominated by single-TF MSS / unconfirmed reclaim. |
| Status | `blocked on paper` |

### P2 — HVN-only confluence (S2)

| Field | Value |
|---|---|
| Hypothesis | FVG overlap on **HVN/POC only** (drop session-VWAP-only prints) raises S2 quality when VWAP is magnet-choppy. |
| setup_type | `fvg_entry` |
| Risk | Misses clean VWAP-mitigation FVG with no profile node; volume-profile Redis must be warm. Wire stays `fvg_entry` (never `ob_fvg`). |
| Effort | S — `profile_overlaps_zone` already exists; add a `SetupParams` flag, default off. |
| Gate | Paper S2 FPR ≥ 30% for 2 weeks **and** FP cohort is VWAP-overlap without HVN (`order_block` / `fvg` factors present, no profile). |
| Status | `blocked on paper` |

### P3 — AVWAP ±1σ inside OB (S6)

| Field | Value |
|---|---|
| Hypothesis | Treating `bands.plus_1_sigma` / `minus_1_sigma` (Phase 2 nested bands) as confluence — not only `vwap_value` inside OB `[low, high]` — recovers reject-wrong S6 when price tags the band but the AVWAP line is just outside the block. |
| setup_type | `avwap_ob_confluence` |
| Risk | Looser geometry → more FPs; must not read Phase 1 flat `band_p1` on `avwap:*` keys. |
| Effort | S — `s6_approach_tol_atr` already pads the line; band-inside-OB is a geometry change. |
| Gate | Paper S6 signals/day &lt; 2 **or** reject-wrong rate high for 2 weeks, with misses showing ±1σ in OB and line outside. |
| Status | `blocked on paper` |

### P4 — News calendar hook replacing stub (S4)

| Field | Value |
|---|---|
| Hypothesis | Replacing `AllowAllNewsFilter` with a real calendar (`SkipWindowNewsFilter` + event timestamps) removes S4 fades printed into CPI/FOMC/NFP windows (`SETUP4_NEWS_WINDOW_SEC=900`). |
| setup_type | `sd_extension_fade` |
| Risk | Over-skip around low-tier headlines; depends on an external feed that **does not ship in this repo**. |
| Effort | L — feed + symbol mapping; detector interface already exists (`NewsFilter.should_skip`). |
| Gate | Paper S4 FPR ≥ 30% for 2 weeks **and** FP timestamps cluster inside a known macro window. Until a feed exists, status cannot become `ready`. |
| Status | `blocked on paper` |

### P5 — First-touch strictness / lookback (S5)

| Field | Value |
|---|---|
| Hypothesis | Tightening `SETUP5_FIRST_TOUCH_LOOKBACK_BARS` (lock 8) or requiring no prior VWAP tag in the trend window cuts S5 FPs on third-touch continuations. |
| setup_type | `vwap_pullback_cont` |
| Risk | Misses late-session first clean tag after a fake early wick. Prefer a **knob** trial (cadence doc) before a pattern rewrite. |
| Effort | S — knob first; variation only if lookback 6–10 cannot move FPR. |
| Gate | Paper S5 FPR ≥ 30% for 2 weeks with `first_touch` factor on losers **and** a knob-only trial already no-shipped or failed OOS. |
| Status | `backlog` |

### P6 — Require ±3σ in all ATR regimes (S4)

| Field | Value |
|---|---|
| Hypothesis | Always requiring a ±3σ tag (today only when `ATR/price ≥ SETUP_ATR_REGIME_HIGH_FRAC`) removes mid-regime 2σ fades that stop out on paper. |
| setup_type | `sd_extension_fade` |
| Risk | Signals/day collapse in quiet tape; 2σ fades are the walk-forward lock. |
| Effort | S — branch in Setup 4 trigger. |
| Gate | Paper S4 accuracy &lt; 60% for 2 weeks **and** FP slice is ±2σ in *low* ATR regime. |
| Status | `backlog` |

### P7 — London + NY AM Judas (S3)

| Field | Value |
|---|---|
| Hypothesis | Allowing `SETUP3_KILL_ZONE` ∈ `{ny_am, london}` for equities/futures (crypto already accepts London) captures Judas that displace at London open. |
| setup_type | `po3_judas` |
| Risk | Asia accum + London displace may not be the USME PO3 the walk-forward locked. |
| Effort | S — session/kill-zone predicate. |
| Gate | Paper S3 signals/day &lt; 2 for 2 weeks on `ES`/`AAPL` with FN cluster in London. |
| Status | `backlog` |

### P8 — Confirmed-sweep optional trial (S1)

| Field | Value |
|---|---|
| Hypothesis | Setting `SETUP1_REQUIRE_CONFIRMED_SWEEP=false` recovers FNs where MSS + VWAP reclaim printed before the sweep Redis row flipped `confirmed`/`reclaim`. |
| setup_type | `sweep_reclaim` |
| Risk | Large FP increase; this is a walk-forward lock. Treat as a **paper-only env trial**, not a default flip. |
| Effort | S — env already exists. Prefer cadence (knob) over a new pattern. |
| Gate | Paper S3/S1 FN (reject-wrong + skip) high for 2 weeks with unconfirmed sweeps that later paper-won. PM must ask. |
| Status | `backlog` |

### P9 — Multi-pattern publish instead of dedupe-drop (orchestrator)

| Field | Value |
|---|---|
| Hypothesis | When two setup_types fire same `symbol+side` inside 300s, publishing the runner-up as a linked note (or keeping both below a conviction gap) reduces FN from dedupe. |
| setup_type | orchestrator (all six) |
| Risk | Double paper size on the same idea; Quant validate/dedupe assumptions break. Needs Quant + PM. |
| Effort | M — orchestrator + paper book semantics. |
| Gate | FN count from `deduped` winners vs losers is the #1 failure mode for 2 weeks **and** paper signals/day &lt; 2 on the dropped type. |
| Status | `backlog` |

### P10 — HTF MSS in addition to 1h/4h rejection (S6)

| Field | Value |
|---|---|
| Hypothesis | Requiring a landed `mss_events` row on 1h or 4h (not only candle rejection) raises S6 precision. |
| setup_type | `avwap_ob_confluence` |
| Risk | Daily HTF is already a 4h swing proxy; true Daily MSS is not on the wire. |
| Effort | M — MSS book on HTF bars. |
| Gate | Paper S6 FPR ≥ 30% for 2 weeks with `htf_ob`+`avwap` but no `mss` on losers. |
| Status | `backlog` |

## Explicitly out of scope

- Live-book variants, live news trading, or enabling `live_trading`.
- New `setup_type` slugs (including `ob_fvg`) without a Quant schema change.
- Auto-promoting any row to `ready` from synthetic E2E fixtures.
- Implementing two variations in the same week.

## How a row leaves the backlog

1. Weekly paper pack shows the **gate** metric for two consecutive weeks
   (or PM asks).
2. ML writes a tune/variation proposal using the
   [weekly_tune_cadence.md](./weekly_tune_cadence.md) change-log template.
3. Prefer a **knob delta** on Timescale OOS before a pattern rewrite.
4. PM signs a **paper-only** trial. **`live_trading` stays `false`.**
5. Status moves `blocked on paper` → `ready` → (separate PR, not this folder)
   `in trial`. This file stays documentation; shipping code is a later PR.
