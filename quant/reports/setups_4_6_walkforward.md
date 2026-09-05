# Setups walk-forward (Quant Phase 3)

Locked tunable ranges from **ML / PM STOP**. Bold values are in-repo **defaults**.
Walk-forward sweeps the listed grids; this file is the retune brief.

Enum is six values only. Dormant `mss_break` / `order_block` / `sweep_mss` /
`ob_fvg` are **not** validated and are **not** walked-forward.

Tape: **in-memory synthetic tape** · `BTCUSDT` · `5m` · 2134 bars · 3 expanding folds · grid mode `core`.

## Mapping

| # | Product name | `setup_type` |
|---|---|---|
| 1 | Liquidity Sweep + VWAP Reclaim | `sweep_reclaim` |
| 2 | FVG @ VWAP / HVN | `fvg_entry` |
| 3 | PO3 / Judas Swing | `po3_judas` |
| 4 | SD extension fade | `sd_extension_fade` |
| 5 | VWAP pullback continuation | `vwap_pullback_cont` |
| 6 | AVWAP + HTF order block | `avwap_ob_confluence` |

HTF for Setup 6 is **synthesized from 5m** (12 bars ≈ 1h, 48 ≈ 4h,
calendar day ≈ 1d). Validate `timeframe` stays {1m, 5m, 15m}.

## Alignment with ML [PR #9](https://github.com/fuserleertec/snipertrader/pull/9)

Setups 4–6 `setup_type` and product keys match PR #9. Validate omits `id`,
`contributing_factors`, and `factor_breakdown`. Those two fields are
**publish-only** on Kafka `setup_signals` (`factor_breakdown` =
`{name, weight, score, note?}[]`, `sum(score)` ≈ conviction).

Dormant `mss_break` / `order_block` / `sweep_mss` are **not** in the
validate enum (PR #9 E2E still has a Setup 2 `ob_fvg` alias — Quant does
**not** accept it on `/risk/validate`; use `fvg_entry`).

S4–S6 defaults (bold) match [PR #9](https://github.com/fuserleertec/snipertrader/pull/9)
`SetupParams`: S4 `vol_frac=0.8`, 20-bar avg, `min_rr=1.5` (2.0 at 3σ),
news skip 900s; S5 trend 20 / first-touch **8** / `min_rr=2.0`; S6
`min_rr=2.0`, `min_conviction=70`, approach **0.15×ATR**, HTF `{1h,4h}`,
swing lookback **2**, wire TF 15m. Orchestrator `dedupe_window_sec=300`.
FE `product_key` for 4–6 stays `*_pending_user_confirm` (PM lock) — PR #9
performance keys `4_sd_extension_fade` etc. are not used on `/performance/summary`.

| Quant field | PR #9 `SetupParams` | Env | Default match? |
|---|---|---|---|
| `s4_vol_max_frac` | `s4_vol_frac` | `SETUP4_VOL_FRAC` | **yes** |
| `s4_vol_avg_period` | `s4_vol_avg_period` | `SETUP4_VOL_AVG_PERIOD` | **yes** |
| `s4_min_rr` | `s4_min_rr` | `SETUP4_MIN_RR` | **yes** |
| `s4_min_rr_at_3s` | `s4_min_rr_at_3s` | `SETUP4_MIN_RR_AT_3S` | **yes** |
| `news_skip_minutes` | `s4_news_window_sec` | `SETUP4_NEWS_WINDOW_SEC` | **yes** |
| `s5_trend_lookback_bars` | `s5_trend_bars` | `SETUP5_TREND_BARS` | **yes** |
| `s5_first_touch_window_bars` | `s5_first_touch_lookback_bars` | `SETUP5_FIRST_TOUCH_LOOKBACK_BARS` | **yes** |
| `s5_min_rr` | `s5_min_rr` | `SETUP5_MIN_RR` | **yes** |
| `s6_min_rr` | `s6_min_rr` | `SETUP6_MIN_RR` | **yes** |
| `s6_min_conviction` | `s6_min_conviction` | `SETUP6_MIN_CONVICTION` | **yes** |
| `s6_approach_tol_atr` | `s6_approach_tol_atr` | `SETUP6_APPROACH_TOL_ATR` | **yes** |
| `s6_swing_lookback` | `s6_swing_lookback` | `SETUP6_SWING_LOOKBACK` | **yes** |
| `dedupe_window_sec` | `dedupe_window_sec` | `SETUP_DEDUPE_WINDOW_SEC` | **yes** |

Conviction reporting here stays 40/30/30. PR #9 uses additive bonuses
`conv_kill_zone_bonus=10` / volume 10 / multi-pattern 10 on a different
scale — we still apply a KZ **bonus** on S4–S6, not a hard gate on S5/S6.

## Alignment with ML PR #7

Baseline = PR #7 `SetupParams` defaults. Quant walk-forward keeps extra knobs
(VWAP band, confluence, confirmation, entry mode) that PR #7 does not expose
on `SETUP_*` env — those stay on the grid for retune only.

| Quant field | PR #7 `SetupParams` | Env | Default match? |
|---|---|---|---|
| `stop_buffer_atr` | `stop_buffer_atr` | `SETUP_STOP_BUFFER_ATR` | **yes** |
| `min_rr` | `s1_min_rr` | `SETUP1_MIN_RR` | **yes** |
| `mss_swing_lookback` | `s1_mss_swing_lookback` | `SETUP1_MSS_SWING_LOOKBACK` | **yes** |
| `max_bars_sweep_to_mss` | `s1_max_bars_sweep_to_mss` | `SETUP1_MAX_BARS_SWEEP_TO_MSS` | **yes** |
| `require_confirmed_sweep` | `s1_require_confirmed_sweep` | `SETUP1_REQUIRE_CONFIRMED_SWEEP` | **yes** |
| `timeframe` | `s1_timeframes` | `SETUP1_TIMEFRAMES` | **yes** |
| `fvg_overlap_tol_atr` | `s2_overlap_tol_atr` | `SETUP2_OVERLAP_TOL_ATR` | **yes** |
| `pin_wick_ratio` | `s2_pin_wick_ratio` | `SETUP2_PIN_WICK_RATIO` | **yes** |
| `max_fvg_age_hours` | `s2_max_fvg_age_hours` | `SETUP2_MAX_FVG_AGE_HOURS` | **yes** |
| `target_rr_fallback` | `s2_target_rr_fallback` | `SETUP2_TARGET_RR_FALLBACK` | **yes** |
| `accumulation_session` | `s3_accum_session` | `SETUP3_ACCUM_SESSION` | **yes** |
| `kill_zone` | `s3_kill_zone` | `SETUP3_KILL_ZONE` | **yes** |
| `displacement_min_body_atr` | `s3_displacement_min_body_atr` | `SETUP3_DISPLACEMENT_MIN_BODY_ATR` | **yes** |
| `require_band_tag` | `s3_require_band_tag` | `SETUP3_REQUIRE_BAND_TAG` | **yes** |
| `max_bars_sweep_to_displace` | `s3_max_bars_sweep_to_displace` | `SETUP3_MAX_BARS_SWEEP_TO_DISPLACE` | **yes** |
| `dedupe_window_sec` | `dedupe_window_sec` | `SETUP_DEDUPE_WINDOW_SEC` | **yes** |
| `min_conviction` | `min_conviction_to_validate` | `SETUP_MIN_CONVICTION_TO_VALIDATE` | **yes** |
| `atr_period` | `atr_period` | `SETUP_ATR_PERIOD` | **yes** |

### Divergences (intentional)

- `s3_kill_zone` default is **`ny_am`** (PR #7). On **crypto**, PR #7
  `manipulation_zones` also allows London — Quant `resolved_kill_zone('crypto')`
  returns `either`. Equity/futures stay `ny_am`.
- `s3_require_band_tag` is a **bool** on PR #7 (`True`). Walk-forward encodes
  that as `require_band_tag='either'` (grid: `1s` / `2s` / `either` / `none`);
  `none` ↔ `False`.
- `s2_target_rr_fallback=2.0` is PR #7; Quant also has `target_mode=prior_swing`
  (fallback uses `target_rr_fallback`).
- Extra Quant-only knobs (not on PR #7 `SetupParams`): `vwap_target_band`,
  `confluence_mode`, `confirmation`, `entry_mode`, `partial_mid`,
  `stop_buffer_ticks`, `session_vwap_anchor`.
- Detectors here replay OHLCV; PR #7 detectors consume DE Redis/Kafka zones.
  Same `setup_type` strings and locked validate fields.

## Locked ranges and defaults

### Setup 1 — `sweep_reclaim`

| Knob | Default | Grid | Notes |
|---|---|---|---|
| `stop_buffer` | **0.05×ATR(14)** (futures **1 tick**) | {0, 0.05, 0.1}×ATR or {0, 1, 2} ticks | Beyond sweep extreme |
| `vwap_target_band` | **1σ if R:R ok else 2σ** (`auto`) | {1, 2}σ | Nearer band with R:R ≥ min_rr; hard discard if R:R < 1.2 |
| `min_rr` | **2.0** | {1.5, 2.0} | Live uses 2.0 |
| `mss_swing_lookback` | **5** | {3, 5, 8} | |
| `max_bars_sweep_to_mss` | **15** | {5, 15, 30} | |
| `require_confirmed_sweep` | **true** | true, false | false = sensitivity |
| `session_vwap_anchor` | **session** | session only | Not weekly/rolling |
| `timeframe` | **5m** | {5m, 15m} (+1m crypto optional) | Primary tape is 5m |

### Setup 2 — `fvg_entry`

| Knob | Default | Grid |
|---|---|---|
| `confluence_mode` | **vwap_or_hvn** | vwap_touch, hvn_overlap, vwap_or_hvn, vwap_and_hvn |
| `fvg_overlap_tol` | **0.05×ATR** | {0, 0.05, 0.1}×ATR |
| `confirmation` | **either** | engulfing, pin_bar, either |
| `pin_wick_ratio` | **2.5** | {2.0, 2.5, 3.0} |
| `entry_mode` | **confirm_close** | zone_boundary, confirm_close |
| `stop_buffer` | **0.05×ATR** beyond opposite FVG bound | {0, 0.05}×ATR |
| `target_mode` | **prior_swing** (fallback 2R) | prior_swing, 1.5R, 2R |
| `max_fvg_age_hours` | **24** | {6, 24, 48} |
| `timeframe` | **5m** | {1m, 5m, 15m} |

### Setup 3 — `po3_judas`

| Knob | Default | Grid |
|---|---|---|
| `accumulation_session` | **asia** | asia, globex |
| `kill_zone` | **ny_am** (crypto resolves to **either**, equity/futures **ny_am**) | ny_am, london, either |
| `displacement_min_body_atr` | **1.2** | {0.8, 1.2, 1.5} |
| `require_band_tag` | **either** | 1σ, 2σ, either, none |
| `stop_buffer` | **0.05×ATR** beyond manipulation wick | {0, 0.05}×ATR |
| `target` | opposite Asia/accum extreme | fixed |
| `partial_mid` | **off** | off, on |
| `max_bars_sweep_to_displace` | **6** | {3, 6, 12} |

### Setup 4 — `sd_extension_fade`

| Knob | Default | Grid |
|---|---|---|
| `band_trigger` | **either** (≥2σ) | 2σ, 3σ, either |
| `vol_max_frac_of_20bar_avg` | **0.8** | {0.7, 0.8, 0.9} |
| `confirm` | **either** | engulfing, pin, mss_1m5m, either |
| `pin_wick_ratio` | **2.5** | {2.0, 2.5, 3.0} |
| `stop` | beyond 3σ + **0.05×ATR** | {0, 0.05}×ATR |
| `tp` | session VWAP | fixed |
| `min_rr` | **1.5** (prefer 2.0 when trigger was 3σ) | {1.5, 2.0} |
| `news_skip_minutes` | **15** (stub calendar) | 15 |
| `min_conviction` | **60** | 60 |

### Setup 5 — `vwap_pullback_cont`

| Knob | Default | Grid |
|---|---|---|
| `trend_lookback_bars` | **20** on 5m | {10, 20, 30} |
| `pullback_level` | **either** | vwap, band_1σ, either |
| `require_ob_or_fvg` | **true** | true |
| `first_touch_window_bars` | **8** | {3, 5, 8} |
| `confirm` | with-trend engulfing \| strong_body | fixed |
| `stop_buffer` | **0.05×ATR** behind swing | 0.05×ATR |
| `tp` | prior swing liquidity | fixed |
| `min_rr` | **2.0** | 2.0 |
| `min_conviction` | **60** | 60 |

### Setup 6 — `avwap_ob_confluence`

| Knob | Default | Grid |
|---|---|---|
| `ob_timeframes` | **4h** | 4h, 1d |
| `approach_tol` | **0.15×ATR** | {0.05, 0.15}×ATR |
| `confirm` | **rejection** on **1h** | rejection \| mss × {1h, 4h} |
| `stop` | opposite OB bound + **0.05×ATR** | 0.05×ATR |
| `tp` | HTF old high/low | fixed |
| `min_rr` | **2.0** | 2.0 |
| `min_conviction` | **70** | 70 |
| `s6_anchor` | **either** (OB + swing_high/low + earnings/news stubs) | ob, swing_high, swing_low, earnings, news, either |
| `s6_swing_lookback` | **2** | 2 (PR #9 default; grid does not retune) |

PM extras (on top of the ML tunables): S4–S6 apply a kill-zone
conviction bonus (`kill_zone_align` **30**) when the confirm bar is in
KZ — not a hard gate on S5/S6 (S4 still skips outside KZ). S6 AVWAP
may anchor to `swing_high` / `swing_low` or stub `earnings` / `news`.
Walk-forward S4–S6 uses `sd_extension_fade` / `vwap_pullback_cont` /
`avwap_ob_confluence` only — never `mss_break` / `order_block` /
`sweep_mss`. `contributing_factors` is `string[]` on publish/store,
not on `POST /risk/validate`.

### Orchestrator (shared)

| Knob | Default | Grid |
|---|---|---|
| `dedupe_window_sec` | **300** | {180, 300, 600} |
| `min_conviction_to_validate` | **60** → confidence 0.60 | {50, 60, 70} |

Conviction weights (**reporting only**, not on `POST /risk/validate`):

- confluence_count **40**
- volume_confirm **30**
- kill_zone_align **30**

VWAP is **session-anchored** (DE crypto clocks: Asia 00:00–07:00, London
07:00–13:30, NY AM 13:30–15:00 UTC).

## Method

- Baseline: ML defaults on the full tape and on the same OOS fold slices (no fit).
- Walk-forward: expanding window (first 40% train; remaining 60% in 3 OOS slices). Each fold grid-searches **train only**, freezes params on **test**.
- Train objective: `2×win_rate + avg_R − max_drawdown` (empty books score −100).
- Event backtester: same-bar SL+TP → SL wins; 2% risk/trade; 1 bp + 2 bp costs.
- Recommended params = majority vote of fold winners (per knob).
- `globex` accumulation is a futures path; this crypto tape scores it poorly on purpose.

## Baseline (ML defaults) vs walk-forward OOS

| Setup | Baseline full | Baseline OOS | WF OOS | Grid n |
|---|---|---|---|---:|
| 4 `sd_extension_fade` | n=10  win=0.0%  avgR=-1.286  Sharpe=-14.388  maxDD=36.2%  pnl=-31560.54 | n=4  win=0.0%  avgR=-1.513  Sharpe=-0.282  maxDD=14.7%  pnl=-22220.12 | n=3  win=0.0%  avgR=-1.396  Sharpe=-0.055  maxDD=9.9%  pnl=-13609.55 | 16 |
| 5 `vwap_pullback_cont` | n=2  win=100.0%  avgR=4.114  Sharpe=7.135  maxDD=0.0%  pnl=18590.13 | n=1  win=100.0%  avgR=4.091  Sharpe=0.466  maxDD=0.0%  pnl=8883.13 | n=1  win=100.0%  avgR=4.091  Sharpe=0.466  maxDD=0.0%  pnl=8883.13 | 4 |
| 6 `avwap_ob_confluence` | n=56  win=5.4%  avgR=-1.391  Sharpe=-14.294  maxDD=100.0%  pnl=-86492.93 | n=30  win=6.7%  avgR=-1.333  Sharpe=0.357  maxDD=94.1%  pnl=-167242.41 | n=14  win=7.1%  avgR=-1.150  Sharpe=0.403  maxDD=94.1%  pnl=-79244.65 | 8 |

## Recommended params for ML retune

### Setup 4 — `sd_extension_fade`

| Knob | Default | Recommended (fold majority) |
|---|---|---|
| `s4_band_trigger` | either | **2s** |
| `s4_vol_max_frac` | 0.8 | **0.8** |
| `s4_confirm` | either | **either** |
| `pin_wick_ratio` | 2.5 | **2.5** |
| `s4_stop_buffer_atr` | 0.05 | **0.05** |
| `s4_min_rr` | 1.5 | **1.5** |

WF OOS P&L ≥ default OOS on this tape — lean toward the recommended column.

### Setup 5 — `vwap_pullback_cont`

| Knob | Default | Recommended (fold majority) |
|---|---|---|
| `s5_trend_lookback_bars` | 20 | **20** |
| `s5_pullback_level` | either | **either** |
| `s5_require_ob_or_fvg` | True | **True** |
| `s5_first_touch_window_bars` | 8 | **8** |
| `s5_stop_buffer_atr` | 0.05 | **0.05** |
| `s5_min_rr` | 2.0 | **2.0** |

WF OOS P&L ≥ default OOS on this tape — lean toward the recommended column.

### Setup 6 — `avwap_ob_confluence`

| Knob | Default | Recommended (fold majority) |
|---|---|---|
| `s6_ob_timeframe` | 4h | **4h** |
| `s6_approach_tol_atr` | 0.15 | **0.15** |
| `s6_confirm` | rejection | **mss** |
| `s6_confirm_tf` | 1h | **1h** |
| `s6_stop_buffer_atr` | 0.05 | **0.05** |
| `s6_min_rr` | 2.0 | **2.0** |
| `s6_anchor` | either | **either** |
| `s6_swing_lookback` | 2 | **2** |

WF OOS P&L ≥ default OOS on this tape — lean toward the recommended column.

## Fold detail

### Setup 4 — `sd_extension_fade`

**Fold 1** — train 853 bars, test 427 bars.

Chosen: `s4_band_trigger=either`, `s4_vol_max_frac=0.8`, `s4_confirm=either`, `pin_wick_ratio=2.5`, `s4_stop_buffer_atr=0.05`, `s4_min_rr=1.5`

- Train: n=3  win=0.0%  avgR=-1.151  Sharpe=-29.907  maxDD=10.9%  pnl=-7507.09
- Test:  n=1  win=0.0%  avgR=-1.833  Sharpe=-5.881  maxDD=9.9%  pnl=-8238.49

**Fold 2** — train 1280 bars, test 427 bars.

Chosen: `s4_band_trigger=2s`, `s4_vol_max_frac=0.8`, `s4_confirm=either`, `pin_wick_ratio=2.5`, `s4_stop_buffer_atr=0.05`, `s4_min_rr=1.5`

- Train: n=5  win=0.0%  avgR=-1.137  Sharpe=-15.992  maxDD=15.1%  pnl=-11905.89
- Test:  n=1  win=0.0%  avgR=-1.246  Sharpe=-12.441  maxDD=5.9%  pnl=-2982.31

**Fold 3** — train 1707 bars, test 427 bars.

Chosen: `s4_band_trigger=2s`, `s4_vol_max_frac=0.8`, `s4_confirm=either`, `pin_wick_ratio=2.5`, `s4_stop_buffer_atr=0.05`, `s4_min_rr=1.5`

- Train: n=7  win=0.0%  avgR=-1.153  Sharpe=-26.460  maxDD=19.8%  pnl=-16649.47
- Test:  n=1  win=0.0%  avgR=-1.108  Sharpe=-16.253  maxDD=3.0%  pnl=-2388.75

OOS pooled (WF): n=3  win=0.0%  avgR=-1.396  Sharpe=-0.055  maxDD=9.9%  pnl=-13609.55

OOS pooled (defaults): n=4  win=0.0%  avgR=-1.513  Sharpe=-0.282  maxDD=14.7%  pnl=-22220.12

### Setup 5 — `vwap_pullback_cont`

**Fold 1** — train 853 bars, test 427 bars.

Chosen: `s5_trend_lookback_bars=20`, `s5_pullback_level=either`, `s5_require_ob_or_fvg=True`, `s5_first_touch_window_bars=8`, `s5_stop_buffer_atr=0.05`, `s5_min_rr=2.0`

- Train: n=1  win=100.0%  avgR=4.137  Sharpe=7.937  maxDD=0.0%  pnl=8921.44
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

**Fold 2** — train 1280 bars, test 427 bars.

Chosen: `s5_trend_lookback_bars=20`, `s5_pullback_level=either`, `s5_require_ob_or_fvg=True`, `s5_first_touch_window_bars=8`, `s5_stop_buffer_atr=0.05`, `s5_min_rr=2.0`

- Train: n=1  win=100.0%  avgR=4.137  Sharpe=6.000  maxDD=0.0%  pnl=8921.44
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

**Fold 3** — train 1707 bars, test 427 bars.

Chosen: `s5_trend_lookback_bars=20`, `s5_pullback_level=either`, `s5_require_ob_or_fvg=True`, `s5_first_touch_window_bars=8`, `s5_stop_buffer_atr=0.05`, `s5_min_rr=2.0`

- Train: n=1  win=100.0%  avgR=4.137  Sharpe=5.292  maxDD=0.0%  pnl=8921.44
- Test:  n=1  win=100.0%  avgR=4.091  Sharpe=11.225  maxDD=0.0%  pnl=8883.13

OOS pooled (WF): n=1  win=100.0%  avgR=4.091  Sharpe=0.466  maxDD=0.0%  pnl=8883.13

OOS pooled (defaults): n=1  win=100.0%  avgR=4.091  Sharpe=0.466  maxDD=0.0%  pnl=8883.13

### Setup 6 — `avwap_ob_confluence`

**Fold 1** — train 853 bars, test 427 bars.

Chosen: `s6_ob_timeframe=4h`, `s6_approach_tol_atr=0.15`, `s6_confirm=rejection`, `s6_confirm_tf=1h`, `s6_stop_buffer_atr=0.05`, `s6_min_rr=2.0`, `s6_anchor=either`, `s6_swing_lookback=2`

- Train: n=26  win=3.8%  avgR=-1.458  Sharpe=-10.403  maxDD=93.1%  pnl=-80476.20
- Test:  n=14  win=7.1%  avgR=-1.150  Sharpe=-13.140  maxDD=94.1%  pnl=-79244.65

**Fold 2** — train 1280 bars, test 427 bars.

Chosen: `s6_ob_timeframe=4h`, `s6_approach_tol_atr=0.15`, `s6_confirm=mss`, `s6_confirm_tf=1h`, `s6_stop_buffer_atr=0.05`, `s6_min_rr=2.0`, `s6_anchor=either`, `s6_swing_lookback=2`

- Train: n=1  win=100.0%  avgR=2.828  Sharpe=6.107  maxDD=0.3%  pnl=5809.42
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

**Fold 3** — train 1707 bars, test 427 bars.

Chosen: `s6_ob_timeframe=4h`, `s6_approach_tol_atr=0.15`, `s6_confirm=mss`, `s6_confirm_tf=1h`, `s6_stop_buffer_atr=0.05`, `s6_min_rr=2.0`, `s6_anchor=either`, `s6_swing_lookback=2`

- Train: n=1  win=100.0%  avgR=2.828  Sharpe=5.382  maxDD=0.3%  pnl=5809.42
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

OOS pooled (WF): n=14  win=7.1%  avgR=-1.150  Sharpe=0.403  maxDD=94.1%  pnl=-79244.65

OOS pooled (defaults): n=30  win=6.7%  avgR=-1.333  Sharpe=0.357  maxDD=94.1%  pnl=-167242.41

## Notes for ML

- Call `POST /risk/validate` **before** publishing to Kafka `setup_signals`.
- Do not send `id` on validate. After `approved: true`, assign `id` and persist
  `adjusted_position_size` (**asset units**, `size_unit: "asset"`).
- `min_conviction_to_validate` maps to `confidence` on the validate payload
  (default **0.60**). Conviction weights stay off the risk API.
- Geometry gate: long `stop < entry < target`, short inverse, take-profit ≥ 1.5R
  (setup min_rr default **2.0**; hard discard < 1.2 after band adjust).
- Conflict rule: same-symbol **opposite direction** only.
- Re-run on live Timescale `ohlcv_bars` (5m) before promoting a retune:
  `sniper-quant backtest --setups 1,2,3 --timeframe 5m --report …`
- If this report used `--inmemory`, the tape is patterned synthetic days —
  a high OOS win rate is **not** a live edge.

## Integration evidence (Quant Phase 3, after ML PR #9)

Re-run these after each merge. Commands assume `cd quant` and `PYTHONPATH=src`.

### Alerts

- Four channels stubbed: Telegram, Discord, email, Slack
  (`test_alerts_four_channels_and_throttle`).
- Throttle: **5 alerts / hour / user** (`429` after the fifth).

### API load

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_phase3.py -k load
```

- Target: `GET /signals` p95 **< 200 ms** under 100 concurrent in-process
  clients (`USE_INMEMORY=1`).
- Last measured p95: **56.37 ms** (2026-09-05).

### Paper

```bash
curl -sS -X POST http://127.0.0.1:8001/paper/demo-fortnight \
  -H 'content-type: application/json'
```

- Demo fortnight seeds **14 calendar days**, **12 closed** paper trades,
  `live_trading: false`.

### ML PR #9 → Quant replay

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_pr9_replay.py
# or against a live in-memory API:
curl -sS -X POST http://127.0.0.1:8001/risk/validate \
  -H 'content-type: application/json' \
  --data-binary @tests/fixtures/pr9_quant_replay/sd_extension_fade.validate.json
```

- Locked-field sample bodies for `sd_extension_fade` / `vwap_pullback_cont` /
  `avwap_ob_confluence` **approve** (live `:8001` replay 2026-09-05:
  S4 R:R 1.60, S5 3.62, S6 5.70; all `reason: ok`).
- Setup-specific 409s: S4 `news_window`, S5 `invalid_levels`, S6
  `low_conviction` (0.65 < 0.70).
- `contributing_factors` / `factor_breakdown` on validate → **422**; on
  publish → stored, not gated.
- Paper: `POST /paper/demo-fortnight` → 14 days / 12 closed /
  `live_trading: false`. Alerts: 4 channels, `max_per_hour: 5`.
