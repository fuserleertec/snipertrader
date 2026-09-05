# Phase 3 Quant evidence (PR #2) — for PM

Quant = step 3 after ML [PR #9](https://github.com/fuserleertec/snipertrader/pull/9) (green). **No live trading.**

Repo: `fuserleertec/snipertrader` · branch `cursor/quant-risk-backtest-1981` ·
PR https://github.com/fuserleertec/snipertrader/pull/2

## PASS / FAIL

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Backtest Setups 4–6 | **PASS** | [`quant/reports/setups_4_6_walkforward.md`](setups_4_6_walkforward.md). Enum excludes `mss_break` / `order_block` / `sweep_mss`. FE `product_key` for 4–6 is `*_pending_user_confirm` — no invented entry-rule names. |
| 2 | Risk API (S4–S6 rules + validate-before-publish) | **PASS** | `tests/test_phase3.py` + `tests/test_validate.py`. Reasons: `invalid_levels`, `news_window`, `low_conviction`, plus existing size/daily/corr/conflict. |
| 3 | Alerts (Telegram/Discord/Email/webhook) + 5/hour throttle | **PASS** | `test_alerts_four_channels_and_throttle`: 4 stubs, max 5/hour/user, extras throttled. |
| 4 | Public API auth + history + performance + load 100 | **PASS** | `GET /signals/history`, `GET /performance/summary` `by_setup` product keys, `X-API-Key` optional. Load: **p95 = 50.52 ms** (target &lt; 200 ms). |
| 5 | Paper 2-week gate | **PASS** | `POST /paper/demo-fortnight` → 14 days, 12 closed trades, `live_trading: false`. |

**pytest:** `cd quant && PYTHONPATH=src python3 -m pytest -q` → **83 passed**.

## 1) Walk-forward 4–6 (synthetic 5m tape, 2134 bars, 3 folds, `core` grid)

| Setup | `setup_type` (live validate / WF) | WF OOS n | WF OOS win | Baseline full n |
|---|---|---:|---:|---:|
| 4 | `sd_extension_fade` | 3 | 0% | 10 |
| 5 | `vwap_pullback_cont` | 1 | 100% | 2 |
| 6 | `avwap_ob_confluence` | 14 | 7.1% | 56 |

Frontend `GET /performance/summary` `product_key` is a **separate** PM/DE lock (do not invent Setup 4–6 entry-rule names):

| `setup_type` (`by_setup` key) | `product_key` |
|---|---|
| `sweep_reclaim` | `1_liquidity_sweep_vwap_reclaim` |
| `fvg_entry` | `2_fvg_mitigation_vwap` |
| `po3_judas` | `3_po3_asia_range_sweep` |
| `mss_break` | `4_pending_user_confirm` |
| `order_block` | `5_pending_user_confirm` |
| `sweep_mss` | `6_pending_user_confirm` |

Tape is **patterned synthetic** — OOS win rate is **not** a live edge. Re-run on Timescale `ohlcv_bars` before promoting a retune.

HTF for S6 is synthesized from 5m (12≈1h, 48≈4h, calendar day≈1d). Validate timeframe stays {1m,5m,15m}.

## 2) Risk API

Locked enum (422 on dormant): `sweep_reclaim`, `fvg_entry`, `po3_judas`, `sd_extension_fade`, `vwap_pullback_cont`, `avwap_ob_confluence`.

| setup | min RR | min conviction | extra |
|---|---|---|---|
| S4 | 1.5 | 60 | ±15m stub news → `news_window` |
| S5 | 2.0 | 60 | |
| S6 | 2.0 | 70 | |

Validate **omits** `id`, `contributing_factors`, `factor_breakdown`. Publish/ingest accept factors (PR #9: `factor_breakdown` = `{name,weight,score,note?}[]`). Rejected candidates never persist (`409` on `POST /signals`).

## 3) Alerts

Stubs only (no network). Channels: `telegram`, `discord`, `email`, `webhook`. Immediate if `confidence ≥ 0.80`. Throttle **5 / hour / user**. Subscribe: `POST /alerts/subscribe`.

## 4) Public API + load

- History: `GET /signals` **and** `GET /signals/history` (same list; `side` filter added).
- Performance: `GET /performance/summary` → `by_setup` keyed by `setup_type` (`sweep_reclaim`, `fvg_entry`, `po3_judas`, `mss_break`, `order_block`, `sweep_mss`). `product_key` lock: `1_liquidity_sweep_vwap_reclaim`, `2_fvg_mitigation_vwap`, `3_po3_asia_range_sweep` (not `3_po3_judas`), `4_pending_user_confirm`, `5_pending_user_confirm`, `6_pending_user_confirm`. Do not invent Setup 4–6 entry-rule names. Drift: rolling 20-trade WR &lt; 45% → `drift_warning`.
- Auth: `SNIPER_API_KEY` → require `X-API-Key` (default **off**). Optional `RATE_LIMIT_PER_MIN`.
- Load methodology: **100 concurrent** in-process `TestClient` threads (`GET /signals?limit=20`), not 100 real sockets. Measured: min 8.08 ms · p50 30.37 ms · **p95 50.52 ms** · p99 61.19 ms · max 62.30 ms. Target p95 &lt; 200 ms → **PASS**.

## 5) Paper (2-week gate, no broker)

```bash
USE_INMEMORY=1 PYTHONPATH=src python3 -m sniper_quant.cli api --inmemory --port 8001
# POST /paper/reset
# POST /risk/validate → POST /signals  (or POST /paper/demo-fortnight)
# POST /v1/lifecycle/bar to close
# GET /paper/account
```

`POST /paper/demo-fortnight` simulates 14 days / 12 scripted trades. `live_trading` is always `false`.
