# Risk parameter adjustment playbook (Phase 4 prep)

**PREP ONLY.** Changes apply to the **paper / in-memory risk API** only.
`live_trading` stays **false**. No broker. No production. Paper gate through
**2026-09-19 07:33:14Z** continues unchanged.

**Who approves:** **PM only.** Quant / ML / FE may propose. No env or default
change ships without a filled change-log row and PM initials.

**Never live without sign-off.** There is no `live_trading` enable switch on
this API. Do not add one. Do not add Alpaca or any broker live path.

## Current locked defaults (do not silently drift)

| Param | Default | Where | What it gates |
|---|---|---|---|
| `RISK_FRACTION` | **0.02** | settings / `GET /risk/params` | Size = 2% equity / risk-per-unit |
| `MAX_DAILY_LOSS_FRAC` | **0.03** | settings | `daily_loss_limit` when day PnL or this trade would breach |
| `CORR_THRESHOLD` | **0.70** | settings | `correlation_threshold` (60-day \|ρ\| vs open symbol) |
| `CORR_LOOKBACK_DAYS` | **60** | settings | Correlation window |
| `MIN_RR` | **1.5** | settings (hard floor) | Geometry; setup floors may be higher |
| S1 `min_rr` | **2.0** | `SETUP_MIN_RR` | `sweep_reclaim` |
| S2 / S3 / S4 `min_rr` | **1.5** | `SETUP_MIN_RR` | S4 prefers 2.0 at 3σ |
| S5 / S6 `min_rr` | **2.0** | `SETUP_MIN_RR` | |
| S1–S5 min conviction | **60** | `SETUP_MIN_CONVICTION` | `low_conviction` if `confidence` sent |
| S6 min conviction | **70** | same | |
| S4 news window | **15 min** / 900s | `news_skip_minutes` | `news_window` on `sd_extension_fade` |

## When to change (paper evidence required)

Propose a change only when **continuous** paper (not demo-fortnight) shows
one of the following. Attach `/paper/account` + `/performance/summary` dumps.

| Trigger | Candidate change | Do not change if |
|---|---|---|
| Daily paper loss hits 3% on a normal day (not a one-off gap) | Tighten `MAX_DAILY_LOSS_FRAC` (e.g. 0.02) | n_closed &lt; 20 overall |
| Size blows equity swings; maxDD approaching 10% | Lower `RISK_FRACTION` (e.g. 0.01) | Smoke book or n &lt; 20 |
| Same-theme symbols keep pairing; false `correlation_threshold` | Raise lookback or threshold **only** with PM | You have not checked open-book symbols |
| Many `invalid_levels` on a setup that WF said should trade | Discuss setup `min_rr` with ML; PM approves | You are loosening to “get fills” |
| Many `low_conviction` while quality is fine | Do **not** drop S6 below 70 without PM | Conviction is reporting-scale, not a knob to juice n |
| S4 `news_window` blocking non-events | Keep 15m until a real calendar is wired | Stub calendar is empty — widening is not “alpha” |

Loosening risk (higher size, higher daily loss, lower min_rr / conviction)
needs an explicit **PM loosen** row. Default bias: tighten or hold.

## Approval

1. Quant files a proposal (param, old, new, evidence, rollback).
2. **PM** initials the change-log row (`approved_by`, `utc`).
3. Change is settings / env on the **paper** API only.
4. Announce in the weekly report. Revert on rollback trigger.

ML retunes of detector grids stay on walk-forward reports — this playbook is
**risk API / account** knobs only.

## Change log

| utc | param | old | new | reason (link dump) | approved_by (PM) | rollback trigger | reverted_utc |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
| | | | | | | | |

## Rollback

| If | Then |
|---|---|
| Paper maxDD ≥ 10% after a size/daily-loss change | Revert `RISK_FRACTION` / `MAX_DAILY_LOSS_FRAC` to table defaults the same day |
| Win rate collapses > 15 pp after loosening min_rr / conviction | Revert that setup floor |
| Any `live_trading: true` observed | **Stop ingest.** Page PM. Do not trade. Restore `false`. |
| Change unlogged | Treat as unauthorized; revert to defaults |

Rollback is a new change-log row (`reverted_utc` filled). No live “hotfix.”

## Never

- No production deploy of a risk change without PM sign-off.
- No Alpaca / broker live orders.
- No flipping `live_trading`.
- No silent env edits on a shared host.
