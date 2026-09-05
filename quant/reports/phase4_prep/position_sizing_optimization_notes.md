# Position sizing optimization notes (Phase 4 prep)

**PREP ONLY. NO live. NO Alpaca live.** Experiments run on the **paper book**
only. `live_trading` stays **false**. Paper gate through **2026-09-19 07:33:14Z**
is unchanged.

There is **no** live broker path in `sniper_quant`. Do not add one from this
note. Alpaca keys (if present for **equities klines** on the site backend) are
**not** for paper-gate order routing.

## Default (locked)

`fixed_fractional_size(equity, risk_fraction=0.02, risk_per_unit)`

- Risk **2% of equity** per approved trade (`RISK_FRACTION=0.02`).
- `adjusted_position_size` is **asset units**, not USD notional.
- Daily cap: `MAX_DAILY_LOSS_FRAC=0.03`.
- Validate may shrink size (`position_size_exceeds_limit`) but does not
  rewrite `entry` / `stop` / `target`.

## Paper-only alternatives (do not enable live)

Try **one** knob at a time on a **forked in-memory API** or a dated paper
reset. PM approves via the
[risk playbook](risk_parameter_adjustment_playbook.md) change log.

| Experiment | Paper setting | Hypothesis | Measure |
|---|---|---|---|
| A — default | `RISK_FRACTION=0.02` | Baseline | equity path, maxDD, avg R |
| B — half risk | `0.01` | Cut DD ~half; same WR / avg R | maxDD &lt; 10% easier |
| C — 1.5% | `0.015` | Between A and B | PnL vs DD |
| D — 2% + tighter daily | `0.02` + `MAX_DAILY_LOSS_FRAC=0.02` | Stop a hot losing day earlier | days stopped vs missed winners |

Do **not** run `RISK_FRACTION > 0.02` without a **PM loosen** row.
Do **not** combine C and D in the same week.

## How to measure on the paper book

After each closed trade (continuous path, not demo-fortnight):

```
GET /paper/account          → equity, realized_pnl, closed_trades, win_rate, average_rr
GET /performance/summary    → max_drawdown_pct, by_setup[*].n_closed / win_rate / average_rr
```

| Metric | How | Pass hint (n≥20) |
|---|---|---|
| Win rate | `/paper/account` `win_rate` | > 60% |
| Avg R | `average_rr` | > 2.0 |
| Max DD | `/performance/summary` `max_drawdown_pct` | < 10% |
| Size sanity | last `adjusted_position_size` × (entry−stop) ≈ 2% equity | within a few bp |
| Daily halt | `daily_loss_limit` reasons in validate checks | expected after −3% day |

Log one row per experiment week:

| utc_start | utc_end | fraction | daily_loss | n_closed | WR | avg R | maxDD | equity | PM |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| | | 0.02 | 0.03 | | | | | | default |
| | | | | | | | | | |

`n_closed < 20`: informational. Demo-fortnight (12 scripted trades) is **not**
a sizing experiment.

## Explicit bans

- **NO live trading.** `live_trading` must read `false` on every snapshot.
- **NO Alpaca live** (no `submit_order`, no live/paper-broker dual-write).
- **NO** production env change of `RISK_FRACTION` without PM.
- **NO** “just this one live fill to check size.”
