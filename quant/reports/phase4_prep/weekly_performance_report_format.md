# Weekly performance report format (Phase 4 prep)

Copy this file (or the block below) each week. Cadence starts after paper-gate
kickoff; first scheduled check **2026-09-12 07:33:14Z**. Gate end
**2026-09-19 07:33:14Z** does **not** flip live.

**PREP ONLY.** `live_trading` stays **false**. No production. No broker.

Fill from `GET /paper/account` and `GET /performance/summary`. Score KPIs
only when `n_closed ≥ 20`. Tracking sheet:
[live_vs_backtest_tracking.md](live_vs_backtest_tracking.md).

---

## Week: YYYY-MM-DD → YYYY-MM-DD (UTC)

| Field | Value |
|---|---|
| Report utc | |
| Author | |
| Period | |
| **Status** | `paper_gate` / `phase4_prep` / `blocked` |
| **`live_trading`** | **false** ☐ confirmed on `/paper/account` |
| Gate clock | start `2026-09-05T07:33:14Z` · end `2026-09-19T07:33:14Z` · days remaining: |
| Ingest | validate → signals → lifecycle (continuous) ☐ |

If `live_trading` is not `false`: **status = blocked**. Stop. Ask PM.

## KPIs vs targets

| KPI | Target | This week (paper) | n_closed | Score |
|---|---|---|---:|---|
| Win rate / accuracy | > 60% | | | pass / fail / **info** (n&lt;20) |
| Avg R:R | > 2.0 (1:2) | | | pass / fail / **info** |
| Max drawdown | < 10% | | | pass / fail / **info** |
| Realized PnL | n/a | | | |
| `drift_warning` | false | | | |

## `by_setup` (product keys)

| `by_setup` key | `setup_type` | n | WR | avg R | maxDD | vs WF OOS | vs targets |
|---|---|---:|---:|---:|---:|---|---|
| `1_liquidity_sweep_vwap_reclaim` | `sweep_reclaim` | | | | | | |
| `2_fvg_mitigation_vwap` | `fvg_entry` | | | | | | |
| `3_po3_asia_range_sweep` | `po3_judas` | | | | | | |
| `4_sd_extension_fade` | `sd_extension_fade` | | | | | | |
| `5_vwap_pullback_cont` | `vwap_pullback_cont` | | | | | | |
| `6_avwap_ob_confluence` | `avwap_ob_confluence` | | | | | | |

## Drift / risk / sizing

- `drift_warning` / `drift_note`:
- Risk-param changes this week (link playbook row): **none** /
- Sizing experiment this week (A/B/C/D): **none** /
- Rejects of note (`news_window`, `low_conviction`, `ob_fvg` 422):

## Asks for PM

1.
2.

## Next check

| | UTC |
|---|---|
| Next weekly | 2026-09-12 07:33:14Z (then weekly after gate end) |
| Gate end | 2026-09-19 07:33:14Z — still no live |

---

### Blank copy (duplicate below)

```
Week:
live_trading: false ☐
n_closed / WR / avg R / maxDD:
by_setup: (six product keys)
drift_warning:
asks:
```
