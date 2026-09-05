# 2-week paper trading gate — kickoff (PR #2)

**Status: STARTED.** `live_trading` is **false** and has no enable switch on this API.
No broker. No production. Not for `main`.

## Clock

| | UTC | America/New_York (EDT, UTC−4) |
|---|---|---|
| **Gate start** | **2026-09-05 07:33:14Z** | **2026-09-05 03:33 EDT** |
| First weekly check | 2026-09-12 07:33:14Z | 2026-09-12 03:33 EDT |
| **Gate end** (14 calendar days) | **2026-09-19 07:33:14Z** | **2026-09-19 03:33 EDT** |

`POST /paper/demo-fortnight` and `POST /paper/gate/start` both stamp this window
on `GET /paper/account` (`gate_started_at_utc` / `gate_ends_at_utc`).
Resetting the book does **not** clear the clock.

## What was started

Two layers. Do not mix their numbers.

### A) Scripted smoke — `POST /paper/demo-fortnight` (done at kickoff)

This is **not** a true 14-day market simulation. It replays
`run_inmemory_demo`: 6 live `setup_type`s × 2 scripted trades (one TP, one SL)
stamped across 14 calendar-day slots. Same-bar costs apply. Use it only to prove
the paper book, risk gate, and account snapshot.

Kickoff capture (in-memory, 2026-09-05 07:33:14Z):

| Metric | Value |
|---|---|
| `live_trading` | **false** |
| `starting_equity` | 100,000 |
| `equity` | 138,158.49 |
| `realized_pnl` | **+11,538.19** |
| `closed_trades` | **12** |
| `open_positions` | 0 |
| `win_rate` | **50.0%** (6 TP / 6 SL) |
| `average_rr` | **+0.470** |
| Trades per setup | 2 each: `sweep_reclaim`, `fvg_entry`, `po3_judas`, `sd_extension_fade`, `vwap_pullback_cont`, `avwap_ob_confluence` |

### B) Continuous paper path (the real 14-day gate)

Incoming approved candidates only:

```
POST /risk/validate   → must be approved:true (omit id / factors)
POST /signals         → paper book opens (409 + no persist if rejected)
POST /v1/lifecycle/bar  or PATCH /signals/{id}  → TP/SL close
GET  /paper/account
GET  /performance/summary
```

`ob_fvg` stays **422**. Setup 2 overlaps publish as `fvg_entry` only.

## Walk-forward backtest expectations (comparison baseline)

Source: [`setups_1_3_walkforward.md`](setups_1_3_walkforward.md) and
[`setups_4_6_walkforward.md`](setups_4_6_walkforward.md). Both tapes are
**patterned synthetic 5m** — OOS win rate is **not** a live edge.

| Setup | `setup_type` | WF OOS n | WF OOS win | WF OOS avg R | Baseline full n / win / avg R |
|---|---|---:|---:|---:|---|
| 1 | `sweep_reclaim` | 1 | 100% | +1.898 | 4 / 100% / +1.840 |
| 2 | `fvg_entry` | 1 | 100% | +2.214 | 4 / 100% / +1.845 |
| 3 | `po3_judas` | 3 | 100% | +2.256 | 4 / 100% / +2.263 |
| 4 | `sd_extension_fade` | 3 | 0% | −1.396 | 10 / 0% / −1.286 |
| 5 | `vwap_pullback_cont` | 1 | 100% | +4.091 | 2 / 100% / +4.114 |
| 6 | `avwap_ob_confluence` | 14 | 7.1% | −1.150 | 56 / 5.4% / −1.391 |

Kickoff smoke vs those rows: **not comparable**. Demo WR 50% / avg R +0.47 is
the scripted 1:1 TP/SL book, not detector edge. Do not fail or pass the
strategy on demo-fortnight vs walk-forward.

## Tolerance rules

### Smoke (`demo-fortnight`) — already applied

| Rule | Threshold | Kickoff |
|---|---|---|
| `live_trading` | must be `false` | **PASS** |
| Closed trades | 12 | **PASS** |
| Days stamped | 14 | **PASS** |
| All 6 live types present | 2 each | **PASS** |
| Equity | > 0 | **PASS** (138,158) |

### Continuous 14-day book vs walk-forward

Apply only to **continuous** paper fills (validate → signals → lifecycle),
never to the scripted smoke book.

| Rule | When | Threshold |
|---|---|---|
| Hard fail | any time | `live_trading` is true, any broker order, or rejected candidate persisted |
| Sample floor | per `setup_type` | `n_closed < 20` → **informational only** (WF OOS n is 1–14; ±15pp is noise) |
| Win rate | `n_closed ≥ 20` | within **±15 percentage points** of that setup’s WF OOS win rate |
| Avg R | `n_closed ≥ 20` | within **±0.50 R** of that setup’s WF OOS avg R |
| Drift warn | rolling 20 closed (any mix) | `GET /performance/summary` `drift_warning` when WR < 45% |
| Overall | gate end | no live trading; paper book intact; write a close-out note in this file |

Pooled WF OOS (all six, synthetic) is too thin and too setup-skewed to use as
a single blended target. Compare **per setup** after the sample floor.

## How to monitor

Base: `http://127.0.0.1:8001` (in-memory) or the PR #2 preview host.

```bash
# clock + PnL + WR + avg R (live_trading must stay false)
curl -sS http://127.0.0.1:8001/paper/account
curl -sS http://127.0.0.1:8001/paper/positions
curl -sS http://127.0.0.1:8001/performance/summary
curl -sS http://127.0.0.1:8001/health
# start / restart the 14-day clock (does not enable live)
curl -sS -X POST http://127.0.0.1:8001/paper/gate/start
# re-seed scripted smoke only (keeps gate clock)
curl -sS -X POST http://127.0.0.1:8001/paper/demo-fortnight
```

`GET /performance/summary` `by_setup` keys (locked product strings):

`1_liquidity_sweep_vwap_reclaim` · `2_fvg_mitigation_vwap` ·
`3_po3_asia_range_sweep` · `4_sd_extension_fade` ·
`5_vwap_pullback_cont` · `6_avwap_ob_confluence`

## 14-calendar-day loop (2026-09-05 → 2026-09-19)

### Daily (UTC morning, or 09:00 ET desk)

1. `GET /health` — process up.
2. `GET /paper/account` — record `equity`, `realized_pnl`, `closed_trades`,
   `win_rate`, `average_rr`, `open_positions`, **`live_trading` (must be false)**,
   `gate_days_remaining`.
3. `GET /performance/summary` — overall + each product-key bucket
   (`n_closed`, `win_rate`, `average_rr`, `drift_warning`).
4. Log any `409` / `422` from validate/publish (expected for rejects / `ob_fvg`).

### Weekly

| Check | When (UTC / ET) | What |
|---|---|---|
| **W1** | **2026-09-12 07:33Z / 03:33 EDT** | Snapshot account + `by_setup`. Flag drift_warning. Confirm `live_trading=false`. |
| **W2 / close** | **2026-09-19 07:33Z / 03:33 EDT** | Final snapshot. Apply ±15pp / ±0.50R only where `n_closed ≥ 20`. Append close-out to this file. **Do not** set `live_trading` true. |

### Continuous ingest (whenever ML publishes)

1. `POST /risk/validate` (locked fields only).
2. On `approved: true`, assign `id` and `POST /signals` with
   `adjusted_position_size`.
3. Close via `POST /v1/lifecycle/bar` or `PATCH /signals/{id}`.
4. Paper engine opens/closes automatically. No broker.

## Kickoff summary (for PM)

- **Start:** 2026-09-05 07:33:14 UTC / 03:33 EDT
- **End / next close-out:** 2026-09-19 07:33:14 UTC / 03:33 EDT
- **Next weekly check:** 2026-09-12 07:33:14 UTC / 03:33 EDT
- **Endpoints:** `GET /paper/account`, `GET /paper/positions`,
  `GET /performance/summary`, `POST /paper/gate/start`,
  `POST /paper/demo-fortnight`, `POST /risk/validate` → `POST /signals`
- **Smoke baseline:** 12 trades, WR 50%, avg R +0.470, PnL +11,538,
  equity 138,158, `live_trading=false`
- **WF expectation:** synthetic; S1–S3 OOS ~100% on n=1–3; S4 0% n=3;
  S5 100% n=1; S6 7.1% n=14 — **not** a live target for the smoke book
- **Production:** off. `live_trading` stays **false**.
