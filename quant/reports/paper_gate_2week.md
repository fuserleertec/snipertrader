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

If **compose inter-container TCP is broken** (docker bridge cannot reach
`timescaledb:5432` from `risk-api`), run host `sniper-quant api` — do **not**
enable `live_trading`:

```bash
export USE_INMEMORY=false
export DATABASE_URL=postgresql://sniper:sniper@127.0.0.1:5432/market
export KAFKA_BOOTSTRAP=127.0.0.1:19092
# restore kickoff window 2026-09-05 07:33:14Z → 2026-09-19 07:33:14Z
export PAPER_GATE_STARTED_AT_MS=1757057594000
export PAPER_GATE_ENDS_AT_MS=1758267194000
sniper-quant api --host 127.0.0.1 --port 8001
curl -sS -X POST http://127.0.0.1:8001/paper/gate/start
```

Timescale is non-SSL; Quant pools use `ssl=False`. `02-signals.sql`
(`signals` hypertable, `account_daily`, `signal_performance`) is mounted
next to `init.sql` in `data_engineering/docker-compose.yml` (fresh volumes
only — existing DB needs `psql -f`).

**Paper hydrate on start** (box churn): `PaperEngine` is in-process RAM.
On lifespan (host `USE_INMEMORY=false`) the API calls
`PaperEngine.load_snapshot(path)` on `PAPER_SNAPSHOT_PATH` (default
`/workspace/quant-data/backups/paper/LATEST.json`) when that file exists
(`{meta, account}` or `GET /paper/account` JSON). Snapshots with
`live_trading=true` are **refused** and the API falls back to
`signals.all()` + `mark_signal`. Then `start_gate()` so
`PAPER_GATE_STARTED_AT_MS` / `PAPER_GATE_ENDS_AT_MS` keep
**2026-09-05 → 2026-09-19** (env wins over snapshot gate). Missing /
unreadable / refused snapshot does **not** crash the API.
Do **not** enable `live_trading`.

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
- **Phase 4 prep** (templates only, no live): [`phase4_prep/README.md`](phase4_prep/README.md)

## Check-in log

### Day 3 — 2026-09-07 (weekday, America/New_York)

**Status: WATCH / infra.** `live_trading` is **false**. No enable switch. No broker.

The kickoff paper API was **in-memory and ephemeral**. Morning check: still **no durable `QUANT_API_BASE`**, so the **continuous** 14-day book had not accumulated fills yet. Later the same day, joint-smoke / DB path produced fills (closed=2); see the joint-smoke note below and **Day 4**.

Do **not** treat `POST /paper/demo-fortnight` smoke numbers (12 closed, WR 50%, avg R +0.470) as the continuous book.

| Continuous book (validate → signals → lifecycle) | Value |
|---|---|
| As-of | **2026-09-07 ET** (Day 3 of 14; gate 2026-09-05 → 2026-09-19) |
| `live_trading` | **false** |
| Closed since kickoff | **0** |
| Open | **0** |
| Per-setup WF ±15pp / ±0.50R | **N/A** (`n_closed < 20` on every `setup_type`; informational only) |
| Action | Standing paper API required for remaining gate days so ML publishes persist |

Need a long-lived paper process (same clock: `POST /paper/gate/start` if the host is new; do not reset the 2026-09-05 → 2026-09-19 window) wired as `QUANT_API_BASE` before W1 (2026-09-12). **Do not** set `live_trading` true.

### Day 3 — 2026-09-07 joint-smoke (continuous book, **not** demo-fortnight)

**Status: continuous fills started.** `live_trading` is **false**. Smoke `demo-fortnight` numbers are **not** this book.

Joint ML → Quant smoke on the paper path (`POST /risk/validate` → `POST /signals` → lifecycle). The in-memory API process was ephemeral; signal rows that landed in Timescale were later hydrated on the **Day 4** host restore. Public `QUANT_API_BASE` for off-box ingest was still missing at this check-in.

| Step | Result |
|---|---|
| `POST /risk/validate` | **4/4** approved |
| `POST /signals` | **NQ + ES** opened |
| `POST /signals` CL / GC | **409** `position_size_exceeds_limit` |
| NQ | **TP_HIT** R ≈ **+2.93** |
| ES | **SL_HIT** R = **−1** |
| Closed | **2** |
| Open | **0** |
| `realized_pnl` | ≈ **+3,859.9** |
| `equity` | ≈ **92,140** |
| `live_trading` | **false** |
| Per-setup WF ±15pp / ±0.50R | **N/A** (`n_closed < 20`) |

**`rank_components` scale mismatch (fixed in this PR):** ML publisher uses **0–100** fields `setup_quality` / `confluence` / `kill_zone` / `volume` / `freshness` (ensemble_features lock). Quant previously expected **0–1** + `risk_adjusted` on publish (and a 0–40/20/15/15/10 point cap on `ensemble_features`). Quant now accepts the ML 0–100 / `confluence` lock; `risk_adjusted` remains a legacy alias. **Do not** send 0–1 as if it were the publisher scale.

### Day 4 — 2026-09-08 (weekday, America/New_York)

**Status: WATCH → restored.** `live_trading` is **false**. No broker / Alpaca live.

Shared-box churn took `:8001` down (no docker socket / run tree). sniperteam restored **host DB-backed** `sniper-quant` on `QUANT_API_BASE=http://127.0.0.1:8001` with host-net Timescale / redis / redpanda (no compose `risk-api`). Gate env preserved: **2026-09-05T07:33:14Z → 2026-09-19T07:33:14Z** (no `POST /paper/gate/start` reset).

Quant verify after restore:

- `GET /health` → ok, `inmemory=false`
- `POST /risk/validate` → 200 (~3ms) approved
- `GET /signals` → 200
- `POST /signals` with FE/ML `rank_components` 0–100 + `confluence` → 201 (probe CANCELLED)

| Continuous book | Value |
|---|---|
| As-of | **2026-09-08 ET** (Day ~4 of 14; gate 2026-09-05 → 2026-09-19) |
| `live_trading` | **false** |
| sniperteam note at bring-up | fresh paper snapshot closed=0 equity=100000 (prior volume loss; new `sniper-ts-data` volume persists going forward) |
| Quant post-hydrate from durable signals | closed=**2**, realized≈**+3859.9**, equity≈**92140**, open=**0** |
| Per-setup WF ±15pp / ±0.50R | **N/A** (`n_closed < 20`; informational only) |

ML resuming continuous emit to `http://127.0.0.1:8001`. Public tunnel / Railway still optional for off-box clients. **Do not** set `live_trading` true.

### Day 5 — 2026-09-09 (weekday, America/New_York) — formal WF (supersedes earlier Day 5 snapshots)

**Status: formal WF FAIL (all six).** `live_trading` is **false**. No broker / Alpaca live. Verified on `http://127.0.0.1:8001`. Gate **unchanged**: 2026-09-05T07:33:14Z → 2026-09-19T07:33:14Z.

Earlier same-day rows (morning thin book closed=2 / `closed_trades=3`; mid-day denser `closed_trades=23`, max n=5) are **superseded**. This snapshot is the continuous book after densify to **n_closed=20 per setup**. Do **not** mix with `demo-fortnight` smoke.

`GET /paper/account`:

| | Value |
|---|---|
| As-of | **2026-09-09 ET** (Day ~5 of 14) |
| `live_trading` | **false** |
| `closed_trades` | **121** (TP=**81**, SL=**39**, CANCELLED=**1**) |
| `realized_pnl` | ≈**+75,048.76** |
| `equity` | ≈**94,019.24** |
| open | **0** |
| Gate | **2026-09-05T07:33:14Z → 2026-09-19T07:33:14Z** |

`GET /performance/summary`: n_signals=**121**, n_closed=**120**, win_rate=**67.5%**, average_rr≈**1.427**, sharpe≈**11.48**, max_drawdown_pct≈**0.04**, `drift_warning`=**false** (API rolling-20 WR flag; overall WR ≥ 45%), signals_today=**118**.

**WF gate now applies** (sample floor `n_closed ≥ 20` on every `setup_type`). Compare to synthetic WF OOS in this file. **All six FAIL** ±15pp WR and ±0.50R.

| by_setup | `setup_type` | n | paper WR | paper avg R | WF OOS WR / avg R | WR_DRIFT | R_DRIFT | Gate |
|---|---|---:|---:|---:|---|---:|---:|---|
| `1_liquidity_sweep_vwap_reclaim` | `sweep_reclaim` | 20 | 65% | 1.171 | 100% / +1.898 | **−35pp** | **−0.73** | **FAIL** |
| `2_fvg_mitigation_vwap` | `fvg_entry` | 20 | 65% | 1.156 | 100% / +2.214 | **−35pp** | **−1.06** | **FAIL** |
| `3_po3_asia_range_sweep` | `po3_judas` | 20 | 70% | 1.677 | 100% / +2.256 | **−30pp** | **−0.58** | **FAIL** |
| `4_sd_extension_fade` | `sd_extension_fade` | 20 | 65% | 1.392 | 0% / −1.396 | **+65pp** | **+2.79** | **FAIL** |
| `5_vwap_pullback_cont` | `vwap_pullback_cont` | 20 | 70% | 1.744 | 100% / +4.091 | **−30pp** | **−2.35** | **FAIL** |
| `6_avwap_ob_confluence` | `avwap_ob_confluence` | 20 | 70% | 1.419 | 7.1% / −1.150 | **+62.9pp** | **+2.57** | **FAIL** |

Caveat: WF OOS n was **1–14 synthetic 5m**; paper densify is **n=20/setup**. Formal gate still flags all six. S4/S6 paper look hot vs a 0% / 7.1% OOS tape; S1–S3/S5 look cold vs 100% OOS on tiny n. API `drift_warning` stays false (pooled WR 67.5% is not under 45%). **This book was later lost** in the ~15:00 ET box churn — see Day 5 afternoon. **Do not** set `live_trading` true.

### Day 5 afternoon — 2026-09-09 ~15:00–15:07 ET (America/New_York)

**Status: WATCH / infra (restored).** `live_trading` is **false**. No broker / Alpaca live.

At ~15:00 ET shared-box churn took host `:8001` down again (connection refused; `sniper-quant-run` + docker socket missing). sniperteam restored host DB-backed API:

- `QUANT_API_BASE=http://127.0.0.1:8001`
- `GET /health` → ok, `inmemory=false`
- `POST /risk/validate` → 200 (~2.5ms)
- Gate env **preserved**: **2026-09-05T07:33:14Z → 2026-09-19T07:33:14Z** (no `POST /paper/gate/start` reset)
- Deps: Timescale / redis / redpanda; no compose `risk-api`

**Volume / book persistence failure:** despite preferring `sniper-ts-data`, the continuous paper book **did not survive**. Verified post-restore:

| Field | Value |
|---|---|
| `live_trading` | **false** |
| `closed_trades` | **0** |
| equity | **100000** |
| `realized_pnl` | **0** |
| open | **0** |
| signals | **0** |

Last good pre-outage densify (~11:27 ET / earlier Day 5 formal WF): closed≈**133**, S1–S6 n≈**22**, formal WF **FAIL-all-six** at n=20 — **lost**. ML re-densifying from an empty book.

**Action / risk:** treat Timescale volume + paper in-memory ledger as **not durable across box churn**. Need a restore playbook that actually rehydrates signals + paper (or an external snapshot) before calling the gate book continuous. **Do not** set `live_trading` true.
