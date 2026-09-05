# Phase 4 prep — ML Researchers (paper / continuous book only)

**Status:** documentation only. This folder is Phase 4 *prep*. It does not
implement detectors, retune knobs, ship pattern variations, or open a live
book.

**`live_trading` remains `false`.** Do not add a live-trading code path, flip
any live flag, or point fills at a live broker. Analysis uses the **paper /
continuous book** and existing setup-detection logs. The static site is
untouched.

These docs sit on top of Phase 3 setups 1–6 (`cursor/ml-research-setups-4-6-d098`,
PR #9). There is no `ml_research/` tree; this is the canonical Phase 4 prep
home.

| Doc | Purpose |
|---|---|
| [false_signal_analysis_plan.md](./false_signal_analysis_plan.md) | Weekly false-signal study on paper fills + validate/publish logs |
| [weekly_tune_cadence.md](./weekly_tune_cadence.md) | Who proposes / who signs knob deltas; ship rule; change-log template |
| [pattern_variation_backlog.md](./pattern_variation_backlog.md) | Ranked S1–S6 ideas — **do not implement** unless paper drift requires |
| [detection_performance_template.md](./detection_performance_template.md) | KPI sheet vs accuracy / FPR / signals-per-day |

## Hard constraints

- Paper book and Timescale OOS only. No live fills, no live `setup_signals` sink.
- Knob recommendations are written into the weekly change log. They are **not**
  auto-applied to `SETUP_*` env or `SetupParams` defaults.
- Pattern variations stay `backlog` / `blocked on paper` until a named paper
  drift metric and PM sign-off exist.
- Quant risk validate stays locked: omit `id`, `contributing_factors`, and
  `factor_breakdown` on `POST /risk/validate`.
