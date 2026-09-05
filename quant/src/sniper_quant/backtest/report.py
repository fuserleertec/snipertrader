"""Markdown report for ML — locked defaults, baseline, walk-forward, retune."""

from __future__ import annotations

from pathlib import Path

from sniper_quant.backtest.params import (
    CONVICTION_WEIGHTS,
    DEFAULT_PARAMS,
    HARD_RR_FLOOR,
    ML_PR7_FIELD_MAP,
    ML_PR9_FIELD_MAP,
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
        "# Setups walk-forward (Quant Phase 3)",
        "",
        "Locked tunable ranges from **ML / PM STOP**. Bold values are in-repo **defaults**.",
        "Walk-forward sweeps the listed grids; this file is the retune brief.",
        "",
        "Enum is six values only. Dormant `mss_break` / `order_block` / `sweep_mss` /",
        "`ob_fvg` are **not** validated and are **not** walked-forward.",
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
        "| 4 | SD extension fade | `sd_extension_fade` |",
        "| 5 | VWAP pullback continuation | `vwap_pullback_cont` |",
        "| 6 | AVWAP + HTF order block | `avwap_ob_confluence` |",
        "",
        "HTF for Setup 6 is **synthesized from 5m** (12 bars ≈ 1h, 48 ≈ 4h,",
        "calendar day ≈ 1d). Validate `timeframe` stays {1m, 5m, 15m}.",
        "",
        "## Alignment with ML [PR #9](https://github.com/fuserleertec/snipertrader/pull/9)",
        "",
        "Setups 4–6 `setup_type` and product keys match PR #9. Validate omits `id`,",
        "`contributing_factors`, and `factor_breakdown`. Those two fields are",
        "**publish-only** on Kafka `setup_signals` (`factor_breakdown` =",
        "`{name, weight, score, note?}[]`, `sum(score)` ≈ conviction).",
        "",
        "Dormant `mss_break` / `order_block` / `sweep_mss` are **not** in the",
        "validate enum (PR #9 E2E still has a Setup 2 `ob_fvg` alias — Quant does",
        "**not** accept it on `/risk/validate`; use `fvg_entry`).",
        "",
        "S4–S6 defaults (bold) match [PR #9](https://github.com/fuserleertec/snipertrader/pull/9)",
        "`SetupParams`: S4 `vol_frac=0.8`, 20-bar avg, `min_rr=1.5` (2.0 at 3σ),",
        "news skip 900s; S5 trend 20 / first-touch **8** / `min_rr=2.0`; S6",
        "`min_rr=2.0`, `min_conviction=70`, approach **0.15×ATR**, HTF `{1h,4h}`,",
        "swing lookback **2**, wire TF 15m. Orchestrator `dedupe_window_sec=300`.",
        "`GET /performance/summary` `by_setup` is keyed by product strings",
        "`1_liquidity_sweep_vwap_reclaim` … `6_avwap_ob_confluence`; each bucket",
        "includes `setup_type`. Dormant / `*_pending_user_confirm` are omitted.",
        "",
        "| Quant field | PR #9 `SetupParams` | Env | Default match? |",
        "|---|---|---|---|",
    ]
    for quant_name, ml_name, env_name in ML_PR9_FIELD_MAP:
        lines.append(f"| `{quant_name}` | `{ml_name}` | `{env_name}` | **yes** |")
    lines += [
        "",
        "Conviction reporting here stays 40/30/30. PR #9 uses additive bonuses",
        "`conv_kill_zone_bonus=10` / volume 10 / multi-pattern 10 on a different",
        "scale — we still apply a KZ **bonus** on S4–S6, not a hard gate on S5/S6.",
        "",
        "## Alignment with ML PR #7",
        "",
        "Baseline = PR #7 `SetupParams` defaults. Quant walk-forward keeps extra knobs",
        "(VWAP band, confluence, confirmation, entry mode) that PR #7 does not expose",
        "on `SETUP_*` env — those stay on the grid for retune only.",
        "",
        "| Quant field | PR #7 `SetupParams` | Env | Default match? |",
        "|---|---|---|---|",
    ]
    for quant_name, ml_name, env_name in ML_PR7_FIELD_MAP:
        lines.append(f"| `{quant_name}` | `{ml_name}` | `{env_name}` | **yes** |")
    lines += [
        "",
        "### Divergences (intentional)",
        "",
        "- `s3_kill_zone` default is **`ny_am`** (PR #7). On **crypto**, PR #7",
        "  `manipulation_zones` also allows London — Quant `resolved_kill_zone('crypto')`",
        "  returns `either`. Equity/futures stay `ny_am`.",
        "- `s3_require_band_tag` is a **bool** on PR #7 (`True`). Walk-forward encodes",
        "  that as `require_band_tag='either'` (grid: `1s` / `2s` / `either` / `none`);",
        "  `none` ↔ `False`.",
        "- `s2_target_rr_fallback=2.0` is PR #7; Quant also has `target_mode=prior_swing`",
        "  (fallback uses `target_rr_fallback`).",
        "- Extra Quant-only knobs (not on PR #7 `SetupParams`): `vwap_target_band`,",
        "  `confluence_mode`, `confirmation`, `entry_mode`, `partial_mid`,",
        "  `stop_buffer_ticks`, `session_vwap_anchor`.",
        "- Detectors here replay OHLCV; PR #7 detectors consume DE Redis/Kafka zones.",
        "  Same `setup_type` strings and locked validate fields.",
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
        f"| `kill_zone` | **{d.kill_zone}** (crypto resolves to **either**, equity/futures **ny_am**) | ny_am, london, either |",
        f"| `displacement_min_body_atr` | **{d.displacement_min_body_atr}** | {{0.8, 1.2, 1.5}} |",
        f"| `require_band_tag` | **{d.require_band_tag}** | 1σ, 2σ, either, none |",
        f"| `stop_buffer` | **{d.po3_stop_buffer_atr}×ATR** beyond manipulation wick | {{0, 0.05}}×ATR |",
        "| `target` | opposite Asia/accum extreme | fixed |",
        f"| `partial_mid` | **off** | off, on |",
        f"| `max_bars_sweep_to_displace` | **{d.max_bars_sweep_to_displace}** | {{3, 6, 12}} |",
        "",
        "### Setup 4 — `sd_extension_fade`",
        "",
        "| Knob | Default | Grid |",
        "|---|---|---|",
        f"| `band_trigger` | **{d.s4_band_trigger}** (≥2σ) | 2σ, 3σ, either |",
        f"| `vol_max_frac_of_20bar_avg` | **{d.s4_vol_max_frac}** | {{0.7, 0.8, 0.9}} |",
        f"| `confirm` | **{d.s4_confirm}** | engulfing, pin, mss_1m5m, either |",
        f"| `pin_wick_ratio` | **{d.pin_wick_ratio}** | {{2.0, 2.5, 3.0}} |",
        f"| `stop` | beyond 3σ + **{d.s4_stop_buffer_atr}×ATR** | {{0, 0.05}}×ATR |",
        "| `tp` | session VWAP | fixed |",
        f"| `min_rr` | **{d.s4_min_rr}** (prefer 2.0 when trigger was 3σ) | {{1.5, 2.0}} |",
        f"| `news_skip_minutes` | **{d.news_skip_minutes}** (stub calendar) | 15 |",
        "| `min_conviction` | **60** | 60 |",
        "",
        "### Setup 5 — `vwap_pullback_cont`",
        "",
        "| Knob | Default | Grid |",
        "|---|---|---|",
        f"| `trend_lookback_bars` | **{d.s5_trend_lookback_bars}** on 5m | {{10, 20, 30}} |",
        f"| `pullback_level` | **{d.s5_pullback_level}** | vwap, band_1σ, either |",
        f"| `require_ob_or_fvg` | **{str(d.s5_require_ob_or_fvg).lower()}** | true |",
        f"| `first_touch_window_bars` | **{d.s5_first_touch_window_bars}** | {{3, 5, 8}} |",
        "| `confirm` | with-trend engulfing \\| strong_body | fixed |",
        f"| `stop_buffer` | **{d.s5_stop_buffer_atr}×ATR** behind swing | 0.05×ATR |",
        "| `tp` | prior swing liquidity | fixed |",
        f"| `min_rr` | **{d.s5_min_rr}** | 2.0 |",
        "| `min_conviction` | **60** | 60 |",
        "",
        "### Setup 6 — `avwap_ob_confluence`",
        "",
        "| Knob | Default | Grid |",
        "|---|---|---|",
        f"| `ob_timeframes` | **{d.s6_ob_timeframe}** | 4h, 1d |",
        f"| `approach_tol` | **{d.s6_approach_tol_atr}×ATR** | {{0.05, 0.15}}×ATR |",
        f"| `confirm` | **{d.s6_confirm}** on **{d.s6_confirm_tf}** | rejection \\| mss × {{1h, 4h}} |",
        f"| `stop` | opposite OB bound + **{d.s6_stop_buffer_atr}×ATR** | 0.05×ATR |",
        "| `tp` | HTF old high/low | fixed |",
        f"| `min_rr` | **{d.s6_min_rr}** | 2.0 |",
        f"| `min_conviction` | **{d.s6_min_conviction}** | 70 |",
        f"| `s6_anchor` | **{d.s6_anchor}** (OB + swing_high/low + earnings/news stubs) | ob, swing_high, swing_low, earnings, news, either |",
        f"| `s6_swing_lookback` | **{d.s6_swing_lookback}** | 2 (PR #9 default; grid does not retune) |",
        "",
        "PM extras (on top of the ML tunables): S4–S6 apply a kill-zone",
        "conviction bonus (`kill_zone_align` **30**) when the confirm bar is in",
        "KZ — not a hard gate on S5/S6 (S4 still skips outside KZ). S6 AVWAP",
        "may anchor to `swing_high` / `swing_low` or stub `earnings` / `news`.",
        "Walk-forward S4–S6 uses `sd_extension_fade` / `vwap_pullback_cont` /",
        "`avwap_ob_confluence` only — never `mss_break` / `order_block` /",
        "`sweep_mss`. `contributing_factors` is `string[]` on publish/store,",
        "not on `POST /risk/validate`.",
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
        "- Train objective: `2×win_rate + avg_R − max_drawdown` (empty books score −100).",
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
        "## Integration evidence (Quant Phase 3, after ML PR #9)",
        "",
        "Re-run these after each merge. Commands assume `cd quant` and `PYTHONPATH=src`.",
        "",
        "### Alerts",
        "",
        "- Four channels stubbed: Telegram, Discord, email, Slack",
        "  (`test_alerts_four_channels_and_throttle`).",
        "- Throttle: **5 alerts / hour / user** (`429` after the fifth).",
        "",
        "### API load",
        "",
        "```bash",
        "PYTHONPATH=src python3 -m pytest -q tests/test_phase3.py -k load",
        "```",
        "",
        "- Target: `GET /signals` p95 **< 200 ms** under 100 concurrent in-process",
        "  clients (`USE_INMEMORY=1`).",
        "- Last measured p95: **56.37 ms** (2026-09-05).",
        "",
        "### Paper",
        "",
        "```bash",
        "curl -sS -X POST http://127.0.0.1:8001/paper/demo-fortnight \\",
        "  -H 'content-type: application/json'",
        "```",
        "",
        "- Demo fortnight seeds **14 calendar days**, **12 closed** paper trades,",
        "  `live_trading: false`.",
        "",
        "### ML PR #9 → Quant replay",
        "",
        "```bash",
        "PYTHONPATH=src python3 -m pytest -q tests/test_pr9_replay.py",
        "# or against a live in-memory API:",
        "curl -sS -X POST http://127.0.0.1:8001/risk/validate \\",
        "  -H 'content-type: application/json' \\",
        "  --data-binary @tests/fixtures/pr9_quant_replay/sd_extension_fade.validate.json",
        "```",
        "",
        "- Locked-field sample bodies for `sd_extension_fade` / `vwap_pullback_cont` /",
        "  `avwap_ob_confluence` **approve**.",
        "- Setup-specific 409s: S4 `news_window`, S5 `invalid_levels`, S6",
        "  `low_conviction` (0.65 < 0.70).",
        "- `contributing_factors` / `factor_breakdown` on validate → **422**; on",
        "  publish → stored, not gated.",
        "",
    ]
    return "\n".join(lines)


def write_walkforward_report(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path
