"""Markdown report for ML — locked defaults, baseline, walk-forward, retune."""

from __future__ import annotations

from pathlib import Path

from sniper_quant.backtest.params import (
    CONVICTION_WEIGHTS,
    DEFAULT_PARAMS,
    HARD_RR_FLOOR,
    params_as_dict,
    setup_fields,
)
from sniper_quant.backtest.walkforward import SetupWalkForward
from sniper_quant.models import BacktestMetrics


def _fmt(m: BacktestMetrics) -> str:
    return (
        f"n={m.n_trades}  win={m.win_rate:.1%}  avgR={m.avg_rr:.3f}  "
        f"Sharpe={m.sharpe:.3f}  maxDD={m.max_drawdown:.1%}  pnl={m.net_pnl:.2f}"
    )


def _chosen_line(setup_type: str, params) -> str:
    d = params_as_dict(params)
    bits = [f"`{k}={d[k]}`" for k in setup_fields(setup_type)]
    return ", ".join(bits)


def render_walkforward_markdown(
    results: list[SetupWalkForward],
    *,
    symbol: str,
    timeframe: str,
    source: str,
    n_bars: int,
    n_folds: int,
    mode: str = "full",
) -> str:
    d = DEFAULT_PARAMS
    lines: list[str] = [
        "# Setups 1–3 walk-forward (Quant Phase 2)",
        "",
        "Locked tunable ranges from **ML Researchers**. Bold values are the",
        "in-repo **defaults**. Walk-forward sweeps the listed grids; this file",
        "is the retune brief.",
        "",
        f"Tape: **{source}** · `{symbol}` · `{timeframe}` · {n_bars} bars · "
        f"{n_folds} expanding folds · grid mode `{mode}`.",
        "",
        "## Mapping",
        "",
        "| # | Product name | `setup_type` |",
        "|---|---|---|",
        "| 1 | Liquidity Sweep + VWAP Reclaim | `sweep_reclaim` |",
        "| 2 | FVG @ VWAP / HVN | `fvg_entry` |",
        "| 3 | PO3 / Judas Swing | `po3_judas` |",
        "",
        "Setups 4–7 (`mss_break`, `order_block`, `sweep_mss`, `ob_fvg`) are accepted",
        "by `POST /risk/validate` but are **not** in this walk-forward.",
        "",
        "## Locked ranges and defaults",
        "",
        "### Setup 1 — `sweep_reclaim`",
        "",
        "| Knob | Default | Grid | Notes |",
        "|---|---|---|---|",
        f"| `stop_buffer` | **{d.stop_buffer_atr}×ATR(14)** (futures **{d.stop_buffer_ticks} tick**) | "
        "{0, 0.05, 0.1}×ATR or {0, 1, 2} ticks | Beyond sweep extreme |",
        f"| `vwap_target_band` | **1σ if R:R ok else 2σ** (`auto`) | {{1, 2}}σ | "
        f"Nearer band with R:R ≥ min_rr; hard discard if R:R < {HARD_RR_FLOOR} |",
        f"| `min_rr` | **{d.min_rr}** | {{1.5, 2.0}} | Live uses 2.0 |",
        f"| `mss_swing_lookback` | **{d.mss_swing_lookback}** | {{3, 5, 8}} | |",
        f"| `max_bars_sweep_to_mss` | **{d.max_bars_sweep_to_mss}** | {{5, 15, 30}} | |",
        f"| `require_confirmed_sweep` | **{str(d.require_confirmed_sweep).lower()}** | true, false | false = sensitivity |",
        f"| `session_vwap_anchor` | **session** | session only | Not weekly/rolling |",
        f"| `timeframe` | **5m** | {{5m, 15m}} (+1m crypto optional) | Primary tape is 5m |",
        "",
        "### Setup 2 — `fvg_entry`",
        "",
        "| Knob | Default | Grid |",
        "|---|---|---|",
        f"| `confluence_mode` | **{d.confluence_mode}** | vwap_touch, hvn_overlap, vwap_or_hvn, vwap_and_hvn |",
        f"| `fvg_overlap_tol` | **{d.fvg_overlap_tol_atr}×ATR** | {{0, 0.05, 0.1}}×ATR |",
        f"| `confirmation` | **{d.confirmation}** | engulfing, pin_bar, either |",
        f"| `pin_wick_ratio` | **{d.pin_wick_ratio}** | {{2.0, 2.5, 3.0}} |",
        f"| `entry_mode` | **{d.entry_mode}** | zone_boundary, confirm_close |",
        f"| `stop_buffer` | **{d.fvg_stop_buffer_atr}×ATR** beyond opposite FVG bound | {{0, 0.05}}×ATR |",
        f"| `target_mode` | **{d.target_mode}** (fallback 2R) | prior_swing, 1.5R, 2R |",
        f"| `max_fvg_age_hours` | **{d.max_fvg_age_hours}** | {{6, 24, 48}} |",
        "| `timeframe` | **5m** | {1m, 5m, 15m} |",
        "",
        "### Setup 3 — `po3_judas`",
        "",
        "| Knob | Default | Grid |",
        "|---|---|---|",
        f"| `accumulation_session` | **{d.accumulation_session}** | asia, globex |",
        "| `kill_zone` | **asset-map** (crypto **either**, equity/futures **ny_am**) | ny_am, london, either |",
        f"| `displacement_min_body_atr` | **{d.displacement_min_body_atr}** | {{0.8, 1.2, 1.5}} |",
        f"| `require_band_tag` | **{d.require_band_tag}** | 1σ, 2σ, either, none |",
        f"| `stop_buffer` | **{d.po3_stop_buffer_atr}×ATR** beyond manipulation wick | {{0, 0.05}}×ATR |",
        "| `target` | opposite Asia/accum extreme | fixed |",
        f"| `partial_mid` | **off** | off, on |",
        f"| `max_bars_sweep_to_displace` | **{d.max_bars_sweep_to_displace}** | {{3, 6, 12}} |",
        "",
        "### Orchestrator (shared)",
        "",
        "| Knob | Default | Grid |",
        "|---|---|---|",
        f"| `dedupe_window_sec` | **{d.dedupe_window_sec}** | {{180, 300, 600}} |",
        f"| `min_conviction_to_validate` | **{d.min_conviction}** → confidence 0.{d.min_conviction} | {{50, 60, 70}} |",
        "",
        "Conviction weights (**reporting only**, not on `POST /risk/validate`):",
        "",
        f"- confluence_count **{CONVICTION_WEIGHTS['confluence_count']}**",
        f"- volume_confirm **{CONVICTION_WEIGHTS['volume_confirm']}**",
        f"- kill_zone_align **{CONVICTION_WEIGHTS['kill_zone_align']}**",
        "",
        "VWAP is **session-anchored** (DE crypto clocks: Asia 00:00–07:00, London",
        "07:00–13:30, NY AM 13:30–15:00 UTC).",
        "",
        "## Method",
        "",
        "- Baseline: ML defaults on the full tape and on the same OOS fold slices (no fit).",
        "- Walk-forward: expanding window (first 40% train; remaining 60% in "
        f"{n_folds} OOS slices). Each fold grid-searches **train only**, freezes params on **test**.",
        "- Train objective: `2×win_rate + avg_R − max_drawdown` (empty books score −1).",
        "- Event backtester: same-bar SL+TP → SL wins; 2% risk/trade; 1 bp + 2 bp costs.",
        "- Recommended params = majority vote of fold winners (per knob).",
        "- `globex` accumulation is a futures path; this crypto tape scores it poorly on purpose.",
        "",
        "## Baseline (ML defaults) vs walk-forward OOS",
        "",
        "| Setup | Baseline full | Baseline OOS | WF OOS | Grid n |",
        "|---|---|---|---|---:|",
    ]
    for row in results:
        lines.append(
            f"| {row.setup_index} `{row.setup_type}` | {_fmt(row.baseline_full)} | "
            f"{_fmt(row.baseline_oos)} | {_fmt(row.oos)} | {row.grid_size} |"
        )
    lines += ["", "## Recommended params for ML retune", ""]
    for row in results:
        rec = row.recommended
        lines.append(f"### Setup {row.setup_index} — `{row.setup_type}`")
        lines.append("")
        lines.append("| Knob | Default | Recommended (fold majority) |")
        lines.append("|---|---|---|")
        for field in setup_fields(row.setup_type):
            default = getattr(DEFAULT_PARAMS, field)
            lines.append(f"| `{field}` | {default} | **{rec.get(field)}** |")
        lines.append("")
        better = row.oos.net_pnl >= row.baseline_oos.net_pnl and row.oos.n_trades >= 1
        if better:
            lines.append("WF OOS P&L ≥ default OOS on this tape — lean toward the recommended column.")
        else:
            lines.append("Defaults held up as well or better on OOS P&L — keep defaults unless live tape disagrees.")
        lines.append("")
    lines += ["## Fold detail", ""]
    for row in results:
        lines += [f"### Setup {row.setup_index} — `{row.setup_type}`", ""]
        for fold in row.folds:
            lines += [
                f"**Fold {fold.fold}** — train {fold.train_n_bars} bars, "
                f"test {fold.test_n_bars} bars.",
                "",
                f"Chosen: {_chosen_line(row.setup_type, fold.params)}",
                "",
                f"- Train: {_fmt(fold.train)}",
                f"- Test:  {_fmt(fold.test)}",
                "",
            ]
        lines += [
            f"OOS pooled (WF): {_fmt(row.oos)}",
            "",
            f"OOS pooled (defaults): {_fmt(row.baseline_oos)}",
            "",
        ]
    lines += [
        "## Notes for ML",
        "",
        "- Call `POST /risk/validate` **before** publishing to Kafka `setup_signals`.",
        "- Do not send `id` on validate. After `approved: true`, assign `id` and persist",
        "  `adjusted_position_size` (**asset units**, `size_unit: \"asset\"`).",
        "- `min_conviction_to_validate` maps to `confidence` on the validate payload",
        f"  (default **0.{d.min_conviction}**). Conviction weights stay off the risk API.",
        "- Geometry gate: long `stop < entry < target`, short inverse, take-profit ≥ 1.5R",
        f"  (setup min_rr default **{d.min_rr}**; hard discard < {HARD_RR_FLOOR} after band adjust).",
        "- Conflict rule: same-symbol **opposite direction** only.",
        "- Re-run on live Timescale `ohlcv_bars` (5m) before promoting a retune:",
        "  `sniper-quant backtest --setups 1,2,3 --timeframe 5m --report …`",
        "- If this report used `--inmemory`, the tape is patterned synthetic days —",
        "  a high OOS win rate is **not** a live edge.",
        "",
    ]
    return "\n".join(lines)


def write_walkforward_report(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path
