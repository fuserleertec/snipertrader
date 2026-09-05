# Weekly tune cadence (paper / after-paper)

**Phase 4 prep.** Cadence for proposing detector and risk knobs while the
book is paper / continuous only. **`live_trading` remains `false`.** No knob
ships unless paper drift is outside tolerance **or** PM explicitly asks.

## When

Run **once per ISO week**, after Quant publishes the **paper-vs-walk-forward**
report (`GET /performance/summary` plus the weekly paper pack).

Suggested sequence (same week, paper book only):

1. Quant closes the weekly paper cohort (fills, R, walk-forward vs paper).
2. ML joins pre/post validate logs + `setup_signals` + paper fills
   ([false_signal_analysis_plan.md](./false_signal_analysis_plan.md)).
3. ML + Quant each file knob proposals (tables below).
4. PM signs **before** any default change is merged.
5. If no sign-off: leave `SETUP_*` / `SetupParams` at the locked walk-forward
   defaults. Log "no-ship" in the change log.

Do not retune off a single session or a synthetic `sniper-data setups`
fixture run.

## What knobs

All tunables live on `SetupParams`
(`data_engineering/src/sniper_data/setup_detection/params.py`) and
`SETUP_*` env (`data_engineering/src/sniper_data/config.py`,
`.env.example`). Detectors must not grow new magic numbers — change the
named field.

### Shared / orchestrator

| Knob | Env | `SetupParams` | Default | Owner |
|---|---|---|---|---|
| ATR period | `SETUP_ATR_PERIOD` | `atr_period` | 14 | ML |
| Stop buffer × ATR | `SETUP_STOP_BUFFER_ATR` | `stop_buffer_atr` | 0.05 | ML + Quant |
| Dedupe window | `SETUP_DEDUPE_WINDOW_SEC` | `dedupe_window_sec` | 300 | ML |
| Min conviction to validate (S1–S3 floor) | `SETUP_MIN_CONVICTION_TO_VALIDATE` | `min_conviction_to_validate` | 60 | ML + Quant |
| High-ATR regime (S4 → require ±3σ) | `SETUP_ATR_REGIME_HIGH_FRAC` | `atr_regime_high_frac` | 0.02 | ML |
| Kill-zone conviction bonus | `SETUP_CONV_KILL_ZONE_BONUS` | `conv_kill_zone_bonus` | 10 | ML |
| Volume conviction bonus | `SETUP_CONV_VOLUME_BONUS` | `conv_volume_bonus` | 10 | ML |
| Multi-pattern conviction bonus | `SETUP_CONV_MULTI_PATTERN_BONUS` | `conv_multi_pattern_bonus` | 10 | ML |

### S1 — `sweep_reclaim`

| Knob | Env | `SetupParams` | Default |
|---|---|---|---|
| Min R:R | `SETUP1_MIN_RR` | `s1_min_rr` | 2.0 |
| MSS swing lookback | `SETUP1_MSS_SWING_LOOKBACK` | `s1_mss_swing_lookback` | 5 |
| Max bars sweep → MSS | `SETUP1_MAX_BARS_SWEEP_TO_MSS` | `s1_max_bars_sweep_to_mss` | 15 |
| Require confirmed/reclaim sweep | `SETUP1_REQUIRE_CONFIRMED_SWEEP` | `s1_require_confirmed_sweep` | true |
| Timeframes | `SETUP1_TIMEFRAMES` | `s1_timeframes` | `5m,15m` |

### S2 — `fvg_entry`

| Knob | Env | `SetupParams` | Default |
|---|---|---|---|
| VWAP / HVN overlap pad | `SETUP2_OVERLAP_TOL_ATR` | `s2_overlap_tol_atr` | 0.05 |
| Pin wick/body | `SETUP2_PIN_WICK_RATIO` | `s2_pin_wick_ratio` | 2.5 |
| Max FVG age (hours) | `SETUP2_MAX_FVG_AGE_HOURS` | `s2_max_fvg_age_hours` | 24 |
| Target R:R fallback | `SETUP2_TARGET_RR_FALLBACK` | `s2_target_rr_fallback` | 2.0 |

Wire `setup_type` stays `fvg_entry`. Do not introduce `ob_fvg` via a tune.

### S3 — `po3_judas`

| Knob | Env | `SetupParams` | Default |
|---|---|---|---|
| Accumulation session | `SETUP3_ACCUM_SESSION` | `s3_accum_session` | `asia` |
| Kill zone | `SETUP3_KILL_ZONE` | `s3_kill_zone` | `ny_am` |
| Displacement body × ATR | `SETUP3_DISPLACEMENT_MIN_BODY_ATR` | `s3_displacement_min_body_atr` | 1.2 |
| Require ±1σ/±2σ tag | `SETUP3_REQUIRE_BAND_TAG` | `s3_require_band_tag` | true |
| Max bars sweep → displace | `SETUP3_MAX_BARS_SWEEP_TO_DISPLACE` | `s3_max_bars_sweep_to_displace` | 6 |

### S4 — `sd_extension_fade`

| Knob | Env | `SetupParams` | Default |
|---|---|---|---|
| Volume average period | `SETUP4_VOL_AVG_PERIOD` | `s4_vol_avg_period` | 20 |
| Low-volume fraction | `SETUP4_VOL_FRAC` | `s4_vol_frac` | 0.8 |
| Min R:R | `SETUP4_MIN_RR` | `s4_min_rr` | 1.5 |
| Min R:R at ±3σ | `SETUP4_MIN_RR_AT_3S` | `s4_min_rr_at_3s` | 2.0 |
| News skip window (sec) | `SETUP4_NEWS_WINDOW_SEC` | `s4_news_window_sec` | 900 |
| Min conviction | `SETUP4_MIN_CONVICTION` | `s4_min_conviction` | 60 |
| Timeframes | `SETUP4_TIMEFRAMES` | `s4_timeframes` | `1m,5m` |
| Pin wick/body | `SETUP4_PIN_WICK_RATIO` | `s4_pin_wick_ratio` | 2.5 |
| Band-tag fraction | `SETUP4_BAND_TAG_FRAC` | `s4_band_tag_frac` | 0.25 |

News filter is still `AllowAllNewsFilter` (stub). Tuning `SETUP4_NEWS_WINDOW_SEC`
does nothing until a real calendar is wired — see backlog.

### S5 — `vwap_pullback_cont`

| Knob | Env | `SetupParams` | Default |
|---|---|---|---|
| Trend bars | `SETUP5_TREND_BARS` | `s5_trend_bars` | 20 |
| Timeframes | `SETUP5_TIMEFRAMES` | `s5_timeframes` | `5m` |
| First-touch lookback | `SETUP5_FIRST_TOUCH_LOOKBACK_BARS` | `s5_first_touch_lookback_bars` | 8 |
| Min R:R | `SETUP5_MIN_RR` | `s5_min_rr` | 2.0 |
| Min conviction | `SETUP5_MIN_CONVICTION` | `s5_min_conviction` | 60 |
| Pullback / approach tol × ATR | `SETUP5_PULLBACK_TOL_ATR` | `s5_pullback_tol_atr` | 0.15 |
| Strong-body fraction | `SETUP5_STRONG_BODY_FRAC` | `s5_strong_body_frac` | 0.5 |
| Pin wick/body | `SETUP5_PIN_WICK_RATIO` | `s5_pin_wick_ratio` | 2.5 |
| Liquidity lookback | `SETUP5_LIQUIDITY_LOOKBACK_BARS` | `s5_liquidity_lookback_bars` | 24 |

`first_touch` in the user brief maps to `s5_first_touch_lookback_bars`.

### S6 — `avwap_ob_confluence`

| Knob | Env | `SetupParams` | Default |
|---|---|---|---|
| Min R:R | `SETUP6_MIN_RR` | `s6_min_rr` | 2.0 |
| Min conviction | `SETUP6_MIN_CONVICTION` | `s6_min_conviction` | 70 |
| HTF books | `SETUP6_HTF_TIMEFRAMES` | `s6_htf_timeframes` | `1h,4h` |
| Wire timeframe | `SETUP6_WIRE_TIMEFRAME` | `s6_wire_timeframe` | `15m` |
| HTF swing lookback | `SETUP6_SWING_LOOKBACK` | `s6_swing_lookback` | 2 |
| Daily (4h proxy) swing lookback | `SETUP6_DAILY_SWING_LOOKBACK` | `s6_daily_swing_lookback` | 6 |
| Approach tol × ATR | `SETUP6_APPROACH_TOL_ATR` | `s6_approach_tol_atr` | 0.15 |
| Pin wick/body | `SETUP6_PIN_WICK_RATIO` | `s6_pin_wick_ratio` | 2.5 |

`approach_tol_atr` in the user brief is `s6_approach_tol_atr` (S6). S5's
nearest analogue is `s5_pullback_tol_atr`.

Quant-owned paper metrics (not `SETUP_*`, but part of the same meeting):
position size, daily loss / lock, paper R distribution, walk-forward vs paper
drift. Quant proposes those; ML does not edit the risk service from this repo.

## Who proposes / who signs

| Role | Proposes | Does not |
|---|---|---|
| **ML Researchers** | Detector knobs: lookbacks, first-touch, approach/overlap tols, vol_frac, confirmation wick/body, timeframes, dedupe window, conviction bonuses, news window (once a feed exists) | Risk lock-list, live flags, auto-merge |
| **Quant** | Risk / paper metrics: min_rr implications, stop buffer vs paper MAE, performance/summary drift, reject-reason mix, paper size | Detector geometry without ML review |
| **PM** | Asks for a tune outside drift; **signs every default change** before merge | Implementing knobs |

A proposal is a filled change-log row (below) plus the week's false-signal
tables. Two signatures: **ML + Quant** on the numbers, **PM** on the merge.

## Ship rule

Ship a default / env change **only if**:

1. Paper drift is **outside tolerance** on a named KPI for the setup
   (see [detection_performance_template.md](./detection_performance_template.md)
   — accuracy &lt; 60%, FPR ≥ 30%, or signals/day outside 2–5 for two
   consecutive weeks), **or**
2. PM explicitly asks for a trial on the paper book.

Otherwise: **no-ship**. Leave walk-forward locks in place.

Additional gates:

- **Timescale OOS preferred over synthetic.** Estimate the delta by replaying
  closed bars from Timescale (`ohlcv_bars`) on the paper / continuous book.
  In-memory fixtures and `--e2e-report` are handshake-only.
- One setup_type per change set unless PM groups a coupled pair (e.g. S5
  first-touch + pullback tol).
- Paper book only. **`live_trading` remains `false`.** Do not point the
  retune at a live validate/publish sink.
- Validate allow-list unchanged: still omit `id`, `contributing_factors`,
  `factor_breakdown`.

## Change log template

Copy one row per proposed (or rejected) tune. Keep the log in the weekly
paper pack, not in `SetupParams`.

```markdown
## Tune proposal — week YYYY-Www

| Field | Value |
|---|---|
| Week | YYYY-Www (UTC) |
| setup_type | sweep_reclaim \| fvg_entry \| po3_judas \| sd_extension_fade \| vwap_pullback_cont \| avwap_ob_confluence \| orchestrator |
| Knob | e.g. `SETUP5_FIRST_TOUCH_LOOKBACK_BARS` / `s5_first_touch_lookback_bars` |
| Current default | 8 |
| Proposed | 6 (example) |
| Direction | tighten / loosen / no-op |
| Owner | ML / Quant / joint |
| Evidence | link to paper-vs-walk-forward + false-signal tables |
| Paper drift | metric, old, new, tolerance, consecutive weeks |
| OOS source | Timescale `ohlcv_bars` range (preferred) / synthetic (say why) |
| Expected effect | accuracy / FPR / signals-per-day |
| Risk | what could get worse on paper |
| Auto-applied? | **no** |
| live_trading | **false** (must stay false) |
| PM decision | ship / no-ship / trial-paper-only |
| PM sign-off | name + date |
| Merge ref | PR link or "not merged" |
```

No-ship example (still log it):

```markdown
| Week | 2026-W36 |
| setup_type | sd_extension_fade |
| Knob | SETUP4_VOL_FRAC |
| Current default | 0.8 |
| Proposed | 0.7 |
| Direction | loosen |
| Owner | ML |
| Evidence | W36 FP cluster on low_volume; paper accuracy 62% (inside tol) |
| Paper drift | accuracy 62% ≥ 60%; FPR 28% < 30%; 1 week only |
| OOS source | Timescale 2026-08-25 → 2026-08-31 |
| PM decision | no-ship |
| live_trading | false |
```
