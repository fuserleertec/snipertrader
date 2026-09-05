# Setups 1–3 walk-forward (Quant Phase 2)

Locked tunable ranges from **ML Researchers**. Bold values are the
in-repo **defaults**. Walk-forward sweeps the listed grids; this file
is the retune brief.

Tape: **in-memory synthetic tape** · `BTCUSDT` · `5m` · 2160 bars · 3 expanding folds · grid mode `core`.

## Integration kickoff verdict (PM 2026-09-05)

| Expectation | Result | Pass? |
|---|---|---|
| Baseline defaults produce trades for all 3 setups | sweep 4 / fvg 4 / po3 4 (full tape) | **PASS** |
| Walk-forward OOS reports win rate, avg R:R, Sharpe, max DD | see table below | **PASS** |
| ML locked defaults seeded in this file | bold column = ML PR defaults | **PASS** |
| Live-edge expectancy | patterned synthetic tape; 100% WR is **not** live | n/a (smoke) |

OOS sample is thin (1–3 trades/setup) because the synthetic book has one pattern-day per cycle. Re-run on Timescale 5m `ohlcv_bars` before promoting a retune. Full cartesian: `sniper-quant backtest --setups 1,2,3 --grid-mode full`.

## Mapping

| # | Product name | `setup_type` |
|---|---|---|
| 1 | Liquidity Sweep + VWAP Reclaim | `sweep_reclaim` |
| 2 | FVG @ VWAP / HVN | `fvg_entry` |
| 3 | PO3 / Judas Swing | `po3_judas` |

Setups 4–7 (`mss_break`, `order_block`, `sweep_mss`, `ob_fvg`) are accepted
by `POST /risk/validate` but are **not** in this walk-forward.

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
| `kill_zone` | **asset-map** (crypto **either**, equity/futures **ny_am**) | ny_am, london, either |
| `displacement_min_body_atr` | **1.2** | {0.8, 1.2, 1.5} |
| `require_band_tag` | **either** | 1σ, 2σ, either, none |
| `stop_buffer` | **0.05×ATR** beyond manipulation wick | {0, 0.05}×ATR |
| `target` | opposite Asia/accum extreme | fixed |
| `partial_mid` | **off** | off, on |
| `max_bars_sweep_to_displace` | **6** | {3, 6, 12} |

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
- Train objective: `2×win_rate + avg_R − max_drawdown` (empty books score −1).
- Event backtester: same-bar SL+TP → SL wins; 2% risk/trade; 1 bp + 2 bp costs.
- Recommended params = majority vote of fold winners (per knob).
- `globex` accumulation is a futures path; this crypto tape scores it poorly on purpose.

## Baseline (ML defaults) vs walk-forward OOS

| Setup | Baseline full | Baseline OOS | WF OOS | Grid n |
|---|---|---|---|---:|
| 1 `sweep_reclaim` | n=4  win=100.0%  avgR=1.840  Sharpe=9.269  maxDD=0.1%  pnl=16843.65 | n=1  win=100.0%  avgR=1.832  Sharpe=0.012  maxDD=3.7%  pnl=3962.68 | n=1  win=100.0%  avgR=1.898  Sharpe=0.013  maxDD=3.9%  pnl=4116.36 | 36 |
| 2 `fvg_entry` | n=4  win=100.0%  avgR=1.845  Sharpe=11.440  maxDD=0.0%  pnl=16174.94 | n=2  win=100.0%  avgR=1.838  Sharpe=0.349  maxDD=3.6%  pnl=7625.19 | n=1  win=100.0%  avgR=2.214  Sharpe=0.015  maxDD=4.6%  pnl=4898.93 | 72 |
| 3 `po3_judas` | n=4  win=100.0%  avgR=2.263  Sharpe=11.441  maxDD=0.0%  pnl=20686.48 | n=3  win=100.0%  avgR=2.256  Sharpe=0.229  maxDD=4.5%  pnl=14427.82 | n=3  win=100.0%  avgR=2.256  Sharpe=0.229  maxDD=4.5%  pnl=14427.82 | 72 |

## Recommended params for ML retune

### Setup 1 — `sweep_reclaim`

| Knob | Default | Recommended (fold majority) |
|---|---|---|
| `stop_buffer_atr` | 0.05 | **0.0** |
| `vwap_target_band` | auto | **2** |
| `min_rr` | 2.0 | **1.5** |
| `mss_swing_lookback` | 5 | **3** |
| `max_bars_sweep_to_mss` | 15 | **15** |
| `require_confirmed_sweep` | True | **True** |

WF OOS P&L ≥ default OOS on this tape — lean toward the recommended column.

### Setup 2 — `fvg_entry`

| Knob | Default | Recommended (fold majority) |
|---|---|---|
| `confluence_mode` | vwap_or_hvn | **vwap_touch** |
| `fvg_overlap_tol_atr` | 0.05 | **0.05** |
| `confirmation` | either | **pin_bar** |
| `pin_wick_ratio` | 2.5 | **2.5** |
| `entry_mode` | confirm_close | **zone_boundary** |
| `fvg_stop_buffer_atr` | 0.05 | **0.05** |
| `target_mode` | prior_swing | **prior_swing** |
| `max_fvg_age_hours` | 24 | **24** |

Defaults held up as well or better on OOS P&L — keep defaults unless live tape disagrees.

### Setup 3 — `po3_judas`

| Knob | Default | Recommended (fold majority) |
|---|---|---|
| `accumulation_session` | asia | **asia** |
| `kill_zone` | asset_map | **asset_map** |
| `displacement_min_body_atr` | 1.2 | **0.8** |
| `require_band_tag` | either | **1s** |
| `po3_stop_buffer_atr` | 0.05 | **0.05** |
| `partial_mid` | False | **False** |
| `max_bars_sweep_to_displace` | 6 | **3** |

WF OOS P&L ≥ default OOS on this tape — lean toward the recommended column.

## Fold detail

### Setup 1 — `sweep_reclaim`

**Fold 1** — train 864 bars, test 432 bars.

Chosen: `stop_buffer_atr=0.0`, `vwap_target_band=2`, `min_rr=1.5`, `mss_swing_lookback=3`, `max_bars_sweep_to_mss=15`, `require_confirmed_sweep=True`

- Train: n=2  win=100.0%  avgR=1.923  Sharpe=7.937  maxDD=0.1%  pnl=8463.45
- Test:  n=1  win=100.0%  avgR=1.898  Sharpe=9.165  maxDD=0.1%  pnl=4116.36

**Fold 2** — train 1296 bars, test 432 bars.

Chosen: `stop_buffer_atr=0.0`, `vwap_target_band=2`, `min_rr=1.5`, `mss_swing_lookback=3`, `max_bars_sweep_to_mss=15`, `require_confirmed_sweep=True`

- Train: n=3  win=100.0%  avgR=1.915  Sharpe=9.295  maxDD=0.1%  pnl=12921.63
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

**Fold 3** — train 1728 bars, test 432 bars.

Chosen: `stop_buffer_atr=0.0`, `vwap_target_band=2`, `min_rr=1.5`, `mss_swing_lookback=3`, `max_bars_sweep_to_mss=15`, `require_confirmed_sweep=True`

- Train: n=3  win=100.0%  avgR=1.915  Sharpe=8.000  maxDD=0.1%  pnl=12921.63
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

OOS pooled (WF): n=1  win=100.0%  avgR=1.898  Sharpe=0.013  maxDD=3.9%  pnl=4116.36

OOS pooled (defaults): n=1  win=100.0%  avgR=1.832  Sharpe=0.012  maxDD=3.7%  pnl=3962.68

### Setup 2 — `fvg_entry`

**Fold 1** — train 864 bars, test 432 bars.

Chosen: `confluence_mode=vwap_touch`, `fvg_overlap_tol_atr=0.05`, `confirmation=pin_bar`, `pin_wick_ratio=2.5`, `entry_mode=zone_boundary`, `fvg_stop_buffer_atr=0.05`, `target_mode=prior_swing`, `max_fvg_age_hours=24`

- Train: n=1  win=100.0%  avgR=2.258  Sharpe=7.937  maxDD=0.0%  pnl=4949.70
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

**Fold 2** — train 1296 bars, test 432 bars.

Chosen: `confluence_mode=vwap_touch`, `fvg_overlap_tol_atr=0.05`, `confirmation=pin_bar`, `pin_wick_ratio=2.5`, `entry_mode=zone_boundary`, `fvg_stop_buffer_atr=0.05`, `target_mode=prior_swing`, `max_fvg_age_hours=24`

- Train: n=1  win=100.0%  avgR=2.258  Sharpe=6.000  maxDD=0.0%  pnl=4949.70
- Test:  n=1  win=100.0%  avgR=2.214  Sharpe=0.000  maxDD=0.0%  pnl=4898.93

**Fold 3** — train 1728 bars, test 432 bars.

Chosen: `confluence_mode=vwap_touch`, `fvg_overlap_tol_atr=0.05`, `confirmation=pin_bar`, `pin_wick_ratio=2.5`, `entry_mode=zone_boundary`, `fvg_stop_buffer_atr=0.05`, `target_mode=prior_swing`, `max_fvg_age_hours=24`

- Train: n=2  win=100.0%  avgR=2.236  Sharpe=8.000  maxDD=0.0%  pnl=10086.39
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=0.000  maxDD=0.0%  pnl=0.00

OOS pooled (WF): n=1  win=100.0%  avgR=2.214  Sharpe=0.015  maxDD=4.6%  pnl=4898.93

OOS pooled (defaults): n=2  win=100.0%  avgR=1.838  Sharpe=0.349  maxDD=3.6%  pnl=7625.19

### Setup 3 — `po3_judas`

**Fold 1** — train 864 bars, test 432 bars.

Chosen: `accumulation_session=asia`, `kill_zone=asset_map`, `displacement_min_body_atr=0.8`, `require_band_tag=1s`, `po3_stop_buffer_atr=0.05`, `partial_mid=False`, `max_bars_sweep_to_displace=3`

- Train: n=1  win=100.0%  avgR=2.284  Sharpe=7.937  maxDD=0.0%  pnl=4840.14
- Test:  n=1  win=100.0%  avgR=2.270  Sharpe=9.165  maxDD=0.0%  pnl=4824.70

**Fold 2** — train 1296 bars, test 432 bars.

Chosen: `accumulation_session=asia`, `kill_zone=asset_map`, `displacement_min_body_atr=0.8`, `require_band_tag=1s`, `po3_stop_buffer_atr=0.05`, `partial_mid=False`, `max_bars_sweep_to_displace=3`

- Train: n=2  win=100.0%  avgR=2.277  Sharpe=9.295  maxDD=0.0%  pnl=9895.49
- Test:  n=1  win=100.0%  avgR=2.256  Sharpe=11.225  maxDD=0.0%  pnl=4809.27

**Fold 3** — train 1728 bars, test 432 bars.

Chosen: `accumulation_session=asia`, `kill_zone=asset_map`, `displacement_min_body_atr=0.8`, `require_band_tag=1s`, `po3_stop_buffer_atr=0.05`, `partial_mid=False`, `max_bars_sweep_to_displace=3`

- Train: n=3  win=100.0%  avgR=2.270  Sharpe=10.583  maxDD=0.0%  pnl=15174.65
- Test:  n=1  win=100.0%  avgR=2.243  Sharpe=11.225  maxDD=0.0%  pnl=4793.84

OOS pooled (WF): n=3  win=100.0%  avgR=2.256  Sharpe=0.229  maxDD=4.5%  pnl=14427.82

OOS pooled (defaults): n=3  win=100.0%  avgR=2.256  Sharpe=0.229  maxDD=4.5%  pnl=14427.82

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
