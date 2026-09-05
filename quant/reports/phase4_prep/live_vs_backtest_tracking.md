# Live vs backtest tracking (Phase 4 prep)

**PREP ONLY.** “Live” here means the **paper book** (`GET /paper/account`,
`GET /performance/summary`). `live_trading` stays **false**. No broker.
Paper gate through **2026-09-19 07:33:14Z** is unchanged
([`../paper_gate_2week.md`](../paper_gate_2week.md)).

Reuse the paper vs walk-forward comparison from the gate note. Walk-forward
sources: [`../setups_1_3_walkforward.md`](../setups_1_3_walkforward.md),
[`../setups_4_6_walkforward.md`](../setups_4_6_walkforward.md). Those tapes
are patterned synthetic — WF OOS is **not** a live edge.

## KPI targets (PM Phase 4)

| KPI | Target | Source field |
|---|---|---|
| Accuracy / win rate | **> 60%** | `win_rate` on `/paper/account` and `/performance/summary` |
| Avg R:R | **> 1:2** (avg realized R **> 2.0**) | `average_rr` |
| Max drawdown | **< 10%** | `max_drawdown_pct` on `/performance/summary` |

Sample floor: **`n_closed ≥ 20` per `by_setup` product key** before a KPI
or ±15pp / ±0.50R delta is scored. Below the floor: fill numbers, mark
**informational**. Scripted `POST /paper/demo-fortnight` (12 trades, WR 50%)
is smoke only — never score it against these targets.

## Locked `by_setup` product keys

| `by_setup` key | `setup_type` | WF OOS n | WF OOS win | WF OOS avg R |
|---|---|---:|---:|---:|
| `1_liquidity_sweep_vwap_reclaim` | `sweep_reclaim` | 1 | 100% | +1.898 |
| `2_fvg_mitigation_vwap` | `fvg_entry` | 1 | 100% | +2.214 |
| `3_po3_asia_range_sweep` | `po3_judas` | 3 | 100% | +2.256 |
| `4_sd_extension_fade` | `sd_extension_fade` | 3 | 0% | −1.396 |
| `5_vwap_pullback_cont` | `vwap_pullback_cont` | 1 | 100% | +4.091 |
| `6_avwap_ob_confluence` | `avwap_ob_confluence` | 14 | 7.1% | −1.150 |

Dormant `mss_break` / `order_block` / `sweep_mss` / `ob_fvg` are not keys.

## Overall sheet (copy a block each week)

**Week of:** YYYY-MM-DD (UTC) · **Filled by:** · `live_trading` = **false** ☐

| KPI | Paper | WF OOS (pooled / note) | Delta | Target | Score (`n≥20`?) |
|---|---|---|---|---|---|
| n_closed | | thin (1–14 / setup) | | ≥ 20 to score | |
| win_rate | | n/a blended | | > 60% | |
| average_rr | | n/a blended | | > 2.0 | |
| max_drawdown_pct | | see WF maxDD | | < 10% | |
| realized_pnl | | | | n/a | |
| drift_warning | | — | | false | |

Pooled WF is not a single blended target. Score **per product key** below.

## By setup — paper vs WF vs delta

**Week of:** YYYY-MM-DD · Poll: `GET /performance/summary`

| `by_setup` key | Paper n | Paper WR | Paper avg R | Paper maxDD | WF n | WF WR | WF avg R | Δ WR (pp) | Δ avg R | Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `1_liquidity_sweep_vwap_reclaim` | | | | | 1 | 100% | +1.898 | | | info if n&lt;20 |
| `2_fvg_mitigation_vwap` | | | | | 1 | 100% | +2.214 | | | info if n&lt;20 |
| `3_po3_asia_range_sweep` | | | | | 3 | 100% | +2.256 | | | info if n&lt;20 |
| `4_sd_extension_fade` | | | | | 3 | 0% | −1.396 | | | info if n&lt;20 |
| `5_vwap_pullback_cont` | | | | | 1 | 100% | +4.091 | | | info if n&lt;20 |
| `6_avwap_ob_confluence` | | | | | 14 | 7.1% | −1.150 | | | info if n&lt;20 |

**Score legend (only if paper `n_closed ≥ 20`):**

- WR vs target: pass if paper WR **> 60%**
- WR vs WF: flag if \|Δ WR\| **> 15 pp**
- Avg R vs target: pass if paper avg R **> 2.0**
- Avg R vs WF: flag if \|Δ avg R\| **> 0.50**
- Max DD vs target: pass if paper maxDD **< 10%**

## Weekly fill instructions

1. Confirm `GET /paper/account` → `live_trading: false`. If true: **stop** and page PM.
2. Pull `GET /paper/account` (equity, realized_pnl, closed_trades, win_rate, average_rr).
3. Pull `GET /performance/summary` (overall + each product-key bucket + `drift_warning`).
4. Copy a blank overall + by_setup block into this file (or the weekly report).
5. If any bucket `n_closed < 20`, write **informational** — do not pass/fail KPIs.
6. Do not use `POST /paper/demo-fortnight` numbers as the Phase 4 score.
7. Next paper-gate weekly check: **2026-09-12 07:33Z**. Gate end: **2026-09-19 07:33Z**.
8. After 2026-09-19, keep filling weekly until PM closes Phase 4 prep. Still no live.

## Endpoints

```
GET /paper/account
GET /paper/positions
GET /performance/summary
GET /health
```
