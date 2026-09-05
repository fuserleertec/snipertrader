"""Markdown report for ML — walk-forward findings + tunable ranges."""

from __future__ import annotations

from pathlib import Path

from sniper_quant.backtest.detectors import DEFAULT_PARAMS, PARAM_GRID
from sniper_quant.backtest.walkforward import SetupWalkForward, params_as_dict
from sniper_quant.models import BacktestMetrics


def _fmt(m: BacktestMetrics) -> str:
    return (
        f"n={m.n_trades}  win={m.win_rate:.1%}  avgR={m.avg_rr:.3f}  "
        f"Sharpe={m.sharpe:.3f}  maxDD={m.max_drawdown:.1%}  pnl={m.net_pnl:.2f}"
    )


def render_walkforward_markdown(
    results: list[SetupWalkForward],
    *,
    symbol: str,
    timeframe: str,
    source: str,
    n_bars: int,
    n_folds: int,
) -> str:
    lines: list[str] = [
        "# Setups 1–3 walk-forward (Quant Phase 2)",
        "",
        "Share this with ML for detector parameter tuning. Numbers below are",
        f"**{source}** on `{symbol}` `{timeframe}` ({n_bars} bars, {n_folds} expanding folds).",
        "",
        "## Mapping",
        "",
        "| # | Product name | `setup_type` | Detector |",
        "|---|---|---|---|",
        "| 1 | Liquidity Sweep + VWAP Reclaim | `sweep_reclaim` | sweep of N-bar extreme + close back through the extreme **and** VWAP |",
        "| 2 | FVG @ VWAP / HVN | `fvg_entry` | 3-bar FVG whose zone overlaps VWAP ± kσ |",
        "| 3 | PO3 / Judas Swing | `po3_judas` | range accumulation, Judas sweep of the range, close through midpoint |",
        "",
        "Setups 4–7 (`mss_break`, `order_block`, `sweep_mss`, `ob_fvg`) are accepted",
        "by `POST /risk/validate` but are **not** in this walk-forward.",
        "",
        "## Defaults (in-repo until ML publishes params)",
        "",
        "ML detectors are not in this repository yet. Quant uses the following",
        "documented defaults. **Treat the grid as the tunable range.**",
        "",
        "| Knob | Default | Grid (walk-forward) | Role |",
        "|---|---|---|---|",
        f"| `stop_atr_mult` | {DEFAULT_PARAMS.stop_atr_mult} | 1.5, 2.0, 2.5 | Stop distance in ATR(14) |",
        f"| `vwap_band_sigma` | {DEFAULT_PARAMS.vwap_band_sigma} | 1.0, 2.0, 3.0 | Target at VWAP ± kσ of (typical − VWAP) |",
        f"| `confirm_bars` | {DEFAULT_PARAMS.confirm_bars} | 1, 2 | Extra closes that must hold VWAP |",
        f"| `lookback` | {DEFAULT_PARAMS.lookback} | fixed | Sweep lookback (Setup 1) |",
        f"| `range_bars` | {DEFAULT_PARAMS.range_bars} | fixed | PO3 accumulation window (Setup 3) |",
        f"| `min_rr` | {DEFAULT_PARAMS.min_rr} | fixed (USME floor) | Target is the farther of VWAP ± kσ and 1.5R |",
        "",
        f"Grid size: **{len(PARAM_GRID)}** combinations. Train objective =",
        "`2×win_rate + avg_R − max_drawdown` (empty books score −1).",
        "",
        "## Method",
        "",
        "- Expanding walk-forward: first 40% of the tape is the initial train window;",
        f"  the remaining 60% is split into {n_folds} sequential out-of-sample slices.",
        "- Each fold grid-searches on **train only**, then freezes those params on **test**.",
        "- Event backtester: same-bar SL+TP → SL wins; 2% risk/trade; 1 bp commission + 2 bp slippage.",
        "- Historical path: `TimescaleOHLCVLoader` on DE `ohlcv_bars`. In-memory path:",
        "  `synthetic_setup_tape` (patterned blocks, not live market data).",
        "",
        "## Out-of-sample by setup",
        "",
        "| Setup | OOS trades | Win rate | Avg R:R | Sharpe | Max DD | Net P&L |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        m = row.oos
        lines.append(
            f"| {row.setup_index} `{row.setup_type}` | {m.n_trades} | {m.win_rate:.1%} | "
            f"{m.avg_rr:.3f} | {m.sharpe:.3f} | {m.max_drawdown:.1%} | {m.net_pnl:.2f} |"
        )
    lines += ["", "## Fold detail", ""]
    for row in results:
        lines += [f"### Setup {row.setup_index} — `{row.setup_type}`", ""]
        for fold in row.folds:
            p = params_as_dict(fold.params)
            lines += [
                f"**Fold {fold.fold}** — train {fold.train_n_bars} bars, "
                f"test {fold.test_n_bars} bars. "
                f"Chosen: `stop_atr_mult={p['stop_atr_mult']}`, "
                f"`vwap_band_sigma={p['vwap_band_sigma']}`, "
                f"`confirm_bars={p['confirm_bars']}`.",
                "",
                f"- Train: {_fmt(fold.train)}",
                f"- Test:  {_fmt(fold.test)}",
                "",
            ]
        lines += [f"OOS pooled: {_fmt(row.oos)}", ""]
    lines += [
        "## Notes for ML",
        "",
        "- Call `POST /risk/validate` **before** publishing to Kafka `setup_signals`.",
        "- Do not send `id` on validate. After `approved: true`, assign `id` and persist",
        "  `adjusted_position_size` (**asset units**, `size_unit: \"asset\"`).",
        "- Geometry gate (also re-checked by the quant consumer): long `stop < entry < target`,",
        "  short inverse, take-profit ≥ 1.5R.",
        "- Conflict rule: same-symbol **opposite direction** only. Same-direction pyramid is allowed.",
        "- These OOS numbers are a baseline for the rule-based detectors. When ML params land,",
        "  re-run `sniper-quant backtest --setups 1,2,3 --report …` on the same tape.",
        "- If this report was generated with `--inmemory`, treat metrics as a smoke-test of the",
        "  pipeline (patterned synthetic tape), not as live-edge expectancy. A 100% OOS win rate",
        "  on this tape means the injected patterns resolved in-favor; it is **not** a live edge.",
        "",
    ]
    return "\n".join(lines)


def write_walkforward_report(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path
