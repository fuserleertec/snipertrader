# Setups 1–3 walk-forward (Quant Phase 2)

Share this with ML for detector parameter tuning. Numbers below are
**in-memory synthetic tape** on `BTCUSDT` `1h` (340 bars, 3 expanding folds).

## Mapping

| # | Product name | `setup_type` | Detector |
|---|---|---|---|
| 1 | Liquidity Sweep + VWAP Reclaim | `sweep_reclaim` | sweep of N-bar extreme + close back through the extreme **and** VWAP |
| 2 | FVG @ VWAP / HVN | `fvg_entry` | 3-bar FVG whose zone overlaps VWAP ± kσ |
| 3 | PO3 / Judas Swing | `po3_judas` | range accumulation, Judas sweep of the range, close through midpoint |

Setups 4–7 (`mss_break`, `order_block`, `sweep_mss`, `ob_fvg`) are accepted
by `POST /risk/validate` but are **not** in this walk-forward.

## Defaults (in-repo until ML publishes params)

ML detectors are not in this repository yet. Quant uses the following
documented defaults. **Treat the grid as the tunable range.**

| Knob | Default | Grid (walk-forward) | Role |
|---|---|---|---|
| `stop_atr_mult` | 2.0 | 1.5, 2.0, 2.5 | Stop distance in ATR(14) |
| `vwap_band_sigma` | 2.0 | 1.0, 2.0, 3.0 | Target at VWAP ± kσ of (typical − VWAP) |
| `confirm_bars` | 1 | 1, 2 | Extra closes that must hold VWAP |
| `lookback` | 20 | fixed | Sweep lookback (Setup 1) |
| `range_bars` | 12 | fixed | PO3 accumulation window (Setup 3) |
| `min_rr` | 1.5 | fixed (USME floor) | Target is the farther of VWAP ± kσ and 1.5R |

Grid size: **18** combinations. Train objective =
`2×win_rate + avg_R − max_drawdown` (empty books score −1).

## Method

- Expanding walk-forward: first 40% of the tape is the initial train window;
  the remaining 60% is split into 3 sequential out-of-sample slices.
- Each fold grid-searches on **train only**, then freezes those params on **test**.
- Event backtester: same-bar SL+TP → SL wins; 2% risk/trade; 1 bp commission + 2 bp slippage.
- Historical path: `TimescaleOHLCVLoader` on DE `ohlcv_bars`. In-memory path:
  `synthetic_setup_tape` (patterned blocks, not live market data).

## Out-of-sample by setup

| Setup | OOS trades | Win rate | Avg R:R | Sharpe | Max DD | Net P&L |
|---|---:|---:|---:|---:|---:|---:|
| 1 `sweep_reclaim` | 5 | 100.0% | 1.437 | 0.812 | 5.6% | 14770.63 |
| 2 `fvg_entry` | 2 | 100.0% | 1.417 | 0.680 | 3.1% | 5787.32 |
| 3 `po3_judas` | 3 | 100.0% | 1.443 | 0.631 | 2.8% | 8784.59 |

## Fold detail

### Setup 1 — `sweep_reclaim`

**Fold 1** — train 136 bars, test 68 bars. Chosen: `stop_atr_mult=2.5`, `vwap_band_sigma=1.0`, `confirm_bars=1`.

- Train: n=3  win=100.0%  avgR=1.432  Sharpe=14.491  maxDD=0.0%  pnl=8996.62
- Test:  n=2  win=100.0%  avgR=1.442  Sharpe=18.330  maxDD=0.0%  pnl=5939.58

**Fold 2** — train 204 bars, test 68 bars. Chosen: `stop_atr_mult=2.5`, `vwap_band_sigma=1.0`, `confirm_bars=1`.

- Train: n=5  win=100.0%  avgR=1.436  Sharpe=16.733  maxDD=0.0%  pnl=15467.42
- Test:  n=1  win=100.0%  avgR=1.441  Sharpe=9.165  maxDD=0.0%  pnl=2924.78

**Fold 3** — train 272 bars, test 68 bars. Chosen: `stop_atr_mult=2.5`, `vwap_band_sigma=1.0`, `confirm_bars=1`.

- Train: n=6  win=100.0%  avgR=1.437  Sharpe=15.198  maxDD=0.0%  pnl=18842.09
- Test:  n=2  win=100.0%  avgR=1.430  Sharpe=22.573  maxDD=0.0%  pnl=5906.28

OOS pooled: n=5  win=100.0%  avgR=1.437  Sharpe=0.812  maxDD=5.6%  pnl=14770.63

### Setup 2 — `fvg_entry`

**Fold 1** — train 136 bars, test 68 bars. Chosen: `stop_atr_mult=2.5`, `vwap_band_sigma=2.0`, `confirm_bars=1`.

- Train: n=1  win=100.0%  avgR=1.462  Sharpe=6.935  maxDD=0.4%  pnl=2951.27
- Test:  n=0  win=0.0%  avgR=0.000  Sharpe=9.165  maxDD=0.0%  pnl=0.00

**Fold 2** — train 204 bars, test 68 bars. Chosen: `stop_atr_mult=1.5`, `vwap_band_sigma=3.0`, `confirm_bars=1`.

- Train: n=2  win=100.0%  avgR=1.674  Sharpe=8.216  maxDD=0.6%  pnl=6962.97
- Test:  n=1  win=100.0%  avgR=1.393  Sharpe=9.165  maxDD=0.0%  pnl=2861.98

**Fold 3** — train 272 bars, test 68 bars. Chosen: `stop_atr_mult=1.5`, `vwap_band_sigma=3.0`, `confirm_bars=1`.

- Train: n=3  win=100.0%  avgR=1.580  Sharpe=8.914  maxDD=0.6%  pnl=10022.96
- Test:  n=1  win=100.0%  avgR=1.441  Sharpe=16.140  maxDD=0.6%  pnl=2925.34

OOS pooled: n=2  win=100.0%  avgR=1.417  Sharpe=0.680  maxDD=3.1%  pnl=5787.32

### Setup 3 — `po3_judas`

**Fold 1** — train 136 bars, test 68 bars. Chosen: `stop_atr_mult=2.5`, `vwap_band_sigma=1.0`, `confirm_bars=1`.

- Train: n=2  win=100.0%  avgR=1.440  Sharpe=10.247  maxDD=0.0%  pnl=5931.66
- Test:  n=1  win=100.0%  avgR=1.444  Sharpe=9.165  maxDD=0.0%  pnl=2929.91

**Fold 2** — train 204 bars, test 68 bars. Chosen: `stop_atr_mult=2.5`, `vwap_band_sigma=1.0`, `confirm_bars=1`.

- Train: n=3  win=100.0%  avgR=1.441  Sharpe=10.583  maxDD=0.0%  pnl=9034.46
- Test:  n=1  win=100.0%  avgR=1.441  Sharpe=9.165  maxDD=0.0%  pnl=2924.78

**Fold 3** — train 272 bars, test 68 bars. Chosen: `stop_atr_mult=2.5`, `vwap_band_sigma=1.0`, `confirm_bars=1`.

- Train: n=4  win=100.0%  avgR=1.441  Sharpe=10.747  maxDD=0.0%  pnl=12222.13
- Test:  n=1  win=100.0%  avgR=1.444  Sharpe=11.252  maxDD=0.0%  pnl=2929.91

OOS pooled: n=3  win=100.0%  avgR=1.443  Sharpe=0.631  maxDD=2.8%  pnl=8784.59

## Notes for ML

- Call `POST /risk/validate` **before** publishing to Kafka `setup_signals`.
- Do not send `id` on validate. After `approved: true`, assign `id` and persist
  `adjusted_position_size` (**asset units**, `size_unit: "asset"`).
- Geometry gate (also re-checked by the quant consumer): long `stop < entry < target`,
  short inverse, take-profit ≥ 1.5R.
- Conflict rule: same-symbol **opposite direction** only. Same-direction pyramid is allowed.
- These OOS numbers are a baseline for the rule-based detectors. When ML params land,
  re-run `sniper-quant backtest --setups 1,2,3 --report …` on the same tape.
- If this report was generated with `--inmemory`, treat metrics as a smoke-test of the
  pipeline (patterned synthetic tape), not as live-edge expectancy. A 100% OOS win rate
  on this tape means the injected patterns resolved in-favor; it is **not** a live edge.
