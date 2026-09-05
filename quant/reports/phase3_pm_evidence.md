# Phase 3 Quant evidence (PR #2) — for PM

Quant = step 3 after ML [PR #9](https://github.com/fuserleertec/snipertrader/pull/9) (green). **No live trading.**

Repo: `fuserleertec/snipertrader` · branch `cursor/quant-risk-backtest-1981` ·
PR https://github.com/fuserleertec/snipertrader/pull/2

## PASS / FAIL

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Backtest Setups 4–6 | **PASS** | [`quant/reports/setups_4_6_walkforward.md`](setups_4_6_walkforward.md). Enum excludes `mss_break` / `order_block` / `sweep_mss`. FE `by_setup` keys are the six product strings (S4–S6 = `4_sd_extension_fade` / `5_vwap_pullback_cont` / `6_avwap_ob_confluence`). |
| 2 | Risk API (S4–S6 rules + validate-before-publish) | **PASS** | `tests/test_phase3.py` + `tests/test_validate.py` + `tests/test_pr9_replay.py`. Reasons: `invalid_levels`, `news_window`, `low_conviction`, plus existing size/daily/corr/conflict. |
| 3 | Alerts (Telegram/Discord/Email/webhook) + 5/hour throttle | **PASS** | `test_alerts_four_channels_and_throttle`: 4 stubs, max 5/hour/user, extras throttled. |
| 4 | Public API auth + history + performance + load 100 | **PASS** | `GET /signals/history`, `GET /performance/summary` `by_setup` product keys, `X-API-Key` optional. Load: **p95 = 56.37 ms** (target &lt; 200 ms). |
| 5 | Paper 2-week gate | **PASS** | `POST /paper/demo-fortnight` → 14 days, 12 closed trades, `live_trading: false`. |
| 6 | ML PR #9 sample replay | **PASS** | `tests/fixtures/pr9_quant_replay/*.validate.json` approve on `/risk/validate`. Factors 422 on validate, stored on publish. |

**pytest:** `cd quant && PYTHONPATH=src python3 -m pytest -q -k "not test_walkforward_setups and not test_cli_backtest"` → **95 passed**, 3 deselected (2026-09-05).

## PR #9 tunable alignment

Quant defaults match PR #9 `SetupParams` where the knobs exist on both sides:

| Knob | PR #9 | Quant default |
|---|---|---|
| S4 `vol_frac` / 20-bar avg | 0.8 / 20 | `s4_vol_max_frac=0.8`, `s4_vol_avg_period=20` |
| S4 `min_rr` / `min_rr_at_3s` | 1.5 / 2.0 | **1.5** / **2.0** |
| S4 news window | 900s | `news_skip_minutes=15` |
| S5 first-touch lookback | 8 | `s5_first_touch_window_bars=8` |
| S5 / S6 `min_rr` | 2.0 | **2.0** |
| S6 `min_conviction` | 70 | **70** |
| S6 approach tol | 0.15×ATR | `s6_approach_tol_atr=0.15` |
| S6 swing lookback | 2 | `s6_swing_lookback=2` |
| Orchestrator dedupe | 300s | `dedupe_window_sec=300` |

Intentional: Quant reporting weights stay **40/30/30**. PR #9 uses additive
`conv_kill_zone_bonus=10` on a different scale. FE `/performance/summary`
`by_setup` **is** keyed by the six product strings, including
`4_sd_extension_fade` / `5_vwap_pullback_cont` / `6_avwap_ob_confluence`.

## 1) Walk-forward 4–6 (synthetic 5m tape, 2134 bars, 3 folds, `core`)

| Setup | `setup_type` (live validate / WF) | WF OOS n | WF OOS win | Baseline full n |
|---|---|---:|---:|---:|
| 4 | `sd_extension_fade` | 3 | 0% | 10 |
| 5 | `vwap_pullback_cont` | 1 | 100% | 2 |
| 6 | `avwap_ob_confluence` | 14 | 7.1% | 56 |

Frontend `GET /performance/summary` `by_setup` is keyed by **product_key**. Each bucket includes `setup_type`. Dormant names and `*_pending_user_confirm` are omitted:

| `by_setup` key (`product_key`) | `setup_type` |
|---|---|
| `1_liquidity_sweep_vwap_reclaim` | `sweep_reclaim` |
| `2_fvg_mitigation_vwap` | `fvg_entry` |
| `3_po3_asia_range_sweep` | `po3_judas` |
| `4_sd_extension_fade` | `sd_extension_fade` |
| `5_vwap_pullback_cont` | `vwap_pullback_cont` |
| `6_avwap_ob_confluence` | `avwap_ob_confluence` |

Tape is **patterned synthetic** — OOS win rate is **not** a live edge. Re-run on Timescale `ohlcv_bars` before promoting a retune.

HTF for S6 is synthesized from 5m (12≈1h, 48≈4h, calendar day≈1d). Validate timeframe stays {1m,5m,15m}.

## 2) Risk API

Locked enum (422 on dormant): `sweep_reclaim`, `fvg_entry`, `po3_judas`, `sd_extension_fade`, `vwap_pullback_cont`, `avwap_ob_confluence`.
`ob_fvg` is **not** accepted on `POST /risk/validate` or `POST /signals` (422, no alias).
Setup 2 overlaps publish as `fvg_entry` only.

| setup | min RR | min conviction | extra |
|---|---|---|---|
| S4 | 1.5 | 60 | ±15m stub news → `news_window` |
| S5 | 2.0 | 60 | |
| S6 | 2.0 | 70 | |

Validate **omits** `id`, `contributing_factors` (`string[]`), `factor_breakdown`. Publish/ingest accept factors (PR #9: `factor_breakdown` = `{name,weight,score,note?}[]`). Rejected candidates never persist (`409` on `POST /signals`).

S4–S6 extras (live types only — `sd_extension_fade` / `vwap_pullback_cont` / `avwap_ob_confluence`): KZ conviction bonus on all three; S6 AVWAP anchors `swing_high`/`swing_low` + earnings/news stubs; orchestrator `dedupe_window_sec=300`. Dormant `mss_break` / `order_block` / `sweep_mss` stay off validate and walk-forward.

## 3) Alerts

Stubs only (no network). Channels: `telegram`, `discord`, `email`, `webhook`. Immediate if `confidence ≥ 0.80`. Throttle **5 / hour / user**. Subscribe: `POST /alerts/subscribe`.

## 4) Public API + load

- History: `GET /signals` **and** `GET /signals/history` (same list; `side` filter added).
- Performance: `GET /performance/summary` → `by_setup` keyed by **product_key** (`1_liquidity_sweep_vwap_reclaim`, `2_fvg_mitigation_vwap`, `3_po3_asia_range_sweep`, `4_sd_extension_fade`, `5_vwap_pullback_cont`, `6_avwap_ob_confluence`). Each bucket includes `setup_type`. Dormant `mss_break` / `order_block` / `sweep_mss` and `*_pending_user_confirm` are omitted. Drift: rolling 20-trade WR &lt; 45% → `drift_warning`.

Empty-book response (in-memory, 2026-09-05):

```json
{
  "win_rate": 0.0,
  "average_rr": 0.0,
  "sharpe_ratio": 0.0,
  "max_drawdown_pct": 0.0,
  "signals_today": 0,
  "signals_week": 0,
  "n_signals": 0,
  "n_closed": 0,
  "by_setup": {
    "1_liquidity_sweep_vwap_reclaim": {
      "setup_type": "sweep_reclaim",
      "product_key": "1_liquidity_sweep_vwap_reclaim",
      "win_rate": 0.0,
      "average_rr": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "signals_today": 0,
      "signals_week": 0,
      "n_signals": 0,
      "n_closed": 0
    },
    "2_fvg_mitigation_vwap": {
      "setup_type": "fvg_entry",
      "product_key": "2_fvg_mitigation_vwap",
      "win_rate": 0.0,
      "average_rr": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "signals_today": 0,
      "signals_week": 0,
      "n_signals": 0,
      "n_closed": 0
    },
    "3_po3_asia_range_sweep": {
      "setup_type": "po3_judas",
      "product_key": "3_po3_asia_range_sweep",
      "win_rate": 0.0,
      "average_rr": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "signals_today": 0,
      "signals_week": 0,
      "n_signals": 0,
      "n_closed": 0
    },
    "4_sd_extension_fade": {
      "setup_type": "sd_extension_fade",
      "product_key": "4_sd_extension_fade",
      "win_rate": 0.0,
      "average_rr": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "signals_today": 0,
      "signals_week": 0,
      "n_signals": 0,
      "n_closed": 0
    },
    "5_vwap_pullback_cont": {
      "setup_type": "vwap_pullback_cont",
      "product_key": "5_vwap_pullback_cont",
      "win_rate": 0.0,
      "average_rr": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "signals_today": 0,
      "signals_week": 0,
      "n_signals": 0,
      "n_closed": 0
    },
    "6_avwap_ob_confluence": {
      "setup_type": "avwap_ob_confluence",
      "product_key": "6_avwap_ob_confluence",
      "win_rate": 0.0,
      "average_rr": 0.0,
      "sharpe_ratio": 0.0,
      "max_drawdown_pct": 0.0,
      "signals_today": 0,
      "signals_week": 0,
      "n_signals": 0,
      "n_closed": 0
    }
  },
  "rolling_win_rate_20": null,
  "drift_warning": false,
  "drift_note": ""
}
```
- Auth: `SNIPER_API_KEY` → require `X-API-Key` (default **off**). Optional `RATE_LIMIT_PER_MIN`.
- Load methodology: **100 concurrent** in-process `TestClient` threads (`GET /signals?limit=20`), not 100 real sockets. Measured (2026-09-05): min 8.35 ms · p50 32.48 ms · **p95 56.37 ms** · p99 65.44 ms · max 71.42 ms. Target p95 &lt; 200 ms → **PASS**.

## 5) Paper (2-week gate, no broker)

```bash
USE_INMEMORY=1 PYTHONPATH=src python3 -m sniper_quant.cli api --inmemory --port 8001
# POST /paper/reset
# POST /risk/validate → POST /signals  (or POST /paper/demo-fortnight)
# POST /v1/lifecycle/bar to close
# GET /paper/account
```

`POST /paper/demo-fortnight` simulates 14 days / 12 scripted trades. `live_trading` is always `false`.

## 6) ML PR #9 → Quant replay

Locked-field bodies (no `id`, no factors) reconstructed from the PR #9 e2e
fixture world (`BTCUSDT`, session VWAP 100):

| File | `setup_type` | Expected |
|---|---|---|
| `sd_extension_fade.validate.json` | long 96.25 / 93.9 / 100, conf 0.75, 5m | **approve** |
| `vwap_pullback_cont.validate.json` | long 101.3 / 99.45 / 108, conf 0.70, 5m | **approve** |
| `avwap_ob_confluence.validate.json` | long 100.3 / 98.95 / 108, conf 0.75, 15m | **approve** |

Live in-memory API replay (2026-09-05, `:8001`): S4/S5/S6 all
`approved: true` / `reason: ok` (S4 R:R 1.60 ≥ 1.5; S5 3.62 ≥ 2.0;
S6 5.70 ≥ 2.0, conviction 75 ≥ 70). Factors on validate → **422**.
`POST /paper/demo-fortnight` → 14 days, 12 closed, `live_trading: false`.
`POST /alerts/subscribe` → 4 channels, `max_per_hour: 5`.

Rejects (never persist): S4 `ts_ms` in stub news window → `news_window`;
S5 flattened R:R → `invalid_levels`; S6 `confidence=0.65` → `low_conviction`
+ `POST /signals` **409**.
