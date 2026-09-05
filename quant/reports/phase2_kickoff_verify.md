# Phase 2 integration kickoff — Quant PR #2

Verified on `cursor/quant-risk-backtest-1981` against OpenAPI **1.2.0**.
In-memory API: `PYTHONPATH=src USE_INMEMORY=1 python3 -m sniper_quant.cli api --inmemory --host 127.0.0.1 --port 8001`

Do **not** start Phase 3.

## 1) Risk Pre-Filter API — PASS

`POST /risk/validate` · equity 100_000 · 2% risk · omit `id`.

### 1A valid mock candidate → `approved: true`

```http
POST /risk/validate
```

```json
{
  "schema_version": "1.1",
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "setup_type": "sweep_reclaim",
  "side": "long",
  "confidence": 0.87,
  "ts_ms": 1700000000000,
  "entry": 65000.0,
  "stop": 64600.0,
  "target": 65800.0,
  "timeframe": "5m",
  "trigger_event_ids": ["evt-sweep-1"]
}
```

```json
{
  "approved": true,
  "reason": "ok",
  "adjusted_position_size": 5.0,
  "size_unit": "asset",
  "entry": 65000.0,
  "stop": 64600.0,
  "target": 65800.0,
  "risk_per_unit": 400.0,
  "checks": {
    "levels": {"source": "provided", "r_multiple": 2.0, "setup_type": "sweep_reclaim", "timeframe": "5m"},
    "position_sizing": {"ok": true, "max_size": 5.0, "requested": null, "risk_fraction": 0.02},
    "same_symbol_conflict": {"ok": true, "rule": "opposite_direction", "open": []},
    "daily_loss": {"ok": true, "already_breached": false, "remaining_risk_budget": 3000.0, "daily_pnl": 0.0},
    "correlation": {"ok": true, "skipped": true, "max_abs_corr": null, "vs_symbol": null, "threshold": 0.7, "lookback": 60}
  }
}
```

Size math: risk/unit = 400; 2% of 100k = 2000 → `adjusted_position_size` = 5.0 coins.

### 1B oversized `proposed_position_size` → `approved: false`

```json
{
  "schema_version": "1.1",
  "symbol": "ETHUSDT",
  "asset_class": "crypto",
  "setup_type": "fvg_entry",
  "side": "long",
  "confidence": 0.81,
  "ts_ms": 1700000001000,
  "entry": 100.0,
  "stop": 96.0,
  "target": 108.0,
  "timeframe": "15m",
  "trigger_event_ids": ["evt-fvg-1"],
  "proposed_position_size": 10000.0
}
```

```json
{
  "approved": false,
  "reason": "position_size_exceeds_limit",
  "adjusted_position_size": 500.0,
  "size_unit": "asset",
  "entry": 100.0,
  "stop": 96.0,
  "target": 108.0,
  "risk_per_unit": 4.0,
  "checks": {
    "levels": {"source": "provided", "r_multiple": 2.0, "setup_type": "fvg_entry", "timeframe": "15m"},
    "position_sizing": {"ok": false, "max_size": 500.0, "requested": 10000.0, "risk_fraction": 0.02},
    "same_symbol_conflict": {"ok": true, "rule": "opposite_direction", "open": []},
    "daily_loss": {"ok": true, "already_breached": false, "remaining_risk_budget": 3000.0, "daily_pnl": 0.0},
    "correlation": {"ok": true, "skipped": true, "max_abs_corr": null, "vs_symbol": null, "threshold": 0.7, "lookback": 60}
  }
}
```

Max size = 0.02 × 100000 / 4 = 500. Proposed 10000 is rejected; `adjusted_position_size` is the cap.

### 1C opposite-direction same-symbol conflict still rejects

Seed (`POST /signals`, HTTP 201) — ACTIVE long `BTCUSDT`:

```json
{
  "id": "ea611ab6-8e86-49a0-acf0-1f90ccee1d48",
  "symbol": "BTCUSDT",
  "side": "long",
  "status": "ACTIVE",
  "entry": 100.0,
  "stop": 96.0,
  "target": 108.0
}
```

Then validate a short on the same symbol:

```json
{
  "schema_version": "1.1",
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "setup_type": "po3_judas",
  "side": "short",
  "confidence": 0.79,
  "ts_ms": 1700000003000,
  "entry": 100.0,
  "stop": 104.0,
  "target": 92.0,
  "timeframe": "5m",
  "trigger_event_ids": ["evt-conflict"]
}
```

```json
{
  "approved": false,
  "reason": "same_symbol_conflict",
  "adjusted_position_size": 0.0,
  "size_unit": "asset",
  "entry": 100.0,
  "stop": 104.0,
  "target": 92.0,
  "risk_per_unit": 4.0,
  "checks": {
    "same_symbol_conflict": {
      "ok": false,
      "rule": "opposite_direction",
      "open": ["BTCUSDT:long"]
    }
  }
}
```

### 1D control — same-direction pyramid allowed

With the long still open, a second long validates `approved: true`, `reason: ok`,
`checks.same_symbol_conflict.open = ["BTCUSDT:long"]`, `rule: opposite_direction`.

## 2) Backtests Setups 1–3 — PASS (synthetic smoke)

Report: [`setups_1_3_walkforward.md`](setups_1_3_walkforward.md)

Command:

```bash
cd quant && PYTHONPATH=src python3 -m sniper_quant.cli backtest \
  --inmemory --setups 1,2,3 --folds 3 --timeframe 5m --grid-mode core \
  --report reports/setups_1_3_walkforward.md
```

Defaults aligned with ML PR #7 (bold in the walk-forward report).

| Setup | Baseline full | WF OOS | vs expectation |
|---|---|---|---|
| `sweep_reclaim` | n=4 WR 100% avgR 1.840 Sharpe 9.269 maxDD 0.1% | n=1 WR 100% avgR 1.898 Sharpe 0.013 maxDD 3.9% | metrics present — PASS |
| `fvg_entry` | n=4 WR 100% avgR 1.845 Sharpe 11.440 maxDD 0.0% | n=1 WR 100% avgR 2.214 Sharpe 0.015 maxDD 4.6% | metrics present — PASS |
| `po3_judas` | n=4 WR 100% avgR 2.263 Sharpe 11.441 maxDD 0.0% | n=3 WR 100% avgR 2.256 Sharpe 0.229 maxDD 4.5% | metrics present — PASS |

100% win rate is **not** a live edge (patterned synthetic 5m tape). Re-run on Timescale `ohlcv_bars` before promoting a retune.

## 3) E2E support readiness — PASS with blockers

ML simulation **must**:

1. `POST /risk/validate` with locked fields, **omit `id`**.
2. Publish to Kafka `setup_signals` **only** when `approved === true`.
3. Then assign `id` and persist `adjusted_position_size` (`size_unit: "asset"`).
4. Quant second gate (`sniper-quant consume` or `POST /v1/signals/ingest`) re-checks geometry + 1.5R.

Tests (InMemoryBus, no Kafka): `tests/test_validate.py` (`test_e2e_ml_must_validate_before_ingest`), `tests/test_validate_service.py`.

### Joint E2E blockers

- No live Kafka + ML publisher in this repo.
- Walk-forward uses in-memory synthetic 5m tape, not Timescale history.
- Do not start Phase 3 until ML can hit `:8001` and publish approved `setup_signals`.

## ML PR #7 locked bodies (live :8001, 2026-09-05)

Clean in-memory book. `ts_ms` = 1788576847635. Validate does **not** persist (`GET /signals` stayed empty).

### ML1 `sweep_reclaim` — PASS (`approved: true`)

Request:

```json
{
  "schema_version": "1.1",
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "setup_type": "sweep_reclaim",
  "side": "long",
  "entry": 100.5,
  "stop": 99.09,
  "target": 104,
  "timeframe": "5m",
  "trigger_event_ids": ["swp-buy-low", "mss-reclaim-long"],
  "confidence": 0.9,
  "ts_ms": 1788576847635
}
```

Response:

```json
{
  "approved": true,
  "reason": "ok",
  "adjusted_position_size": 1418.43971631,
  "size_unit": "asset",
  "entry": 100.5,
  "stop": 99.09,
  "target": 104.0,
  "risk_per_unit": 1.4099999999999966,
  "checks": {
    "levels": {"source": "provided", "r_multiple": 2.4822695035461053, "setup_type": "sweep_reclaim", "timeframe": "5m"},
    "position_sizing": {"ok": true, "max_size": 1418.4397163120602, "requested": null, "risk_fraction": 0.02},
    "same_symbol_conflict": {"ok": true, "rule": "opposite_direction", "open": []},
    "daily_loss": {"ok": true, "already_breached": false, "remaining_risk_budget": 3000.0, "daily_pnl": 0.0},
    "correlation": {"ok": true, "skipped": true, "max_abs_corr": null, "vs_symbol": null, "threshold": 0.7, "lookback": 60}
  }
}
```

### ML2 `fvg_entry` — PASS (`approved: true`)

Request:

```json
{
  "schema_version": "1.1",
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "setup_type": "fvg_entry",
  "side": "long",
  "entry": 100.45,
  "stop": 99.53,
  "target": 103.5,
  "timeframe": "1m",
  "trigger_event_ids": ["fvg-bull-vwap"],
  "confidence": 1.0,
  "ts_ms": 1788576847635
}
```

Response:

```json
{
  "approved": true,
  "reason": "ok",
  "adjusted_position_size": 2173.91304348,
  "size_unit": "asset",
  "entry": 100.45,
  "stop": 99.53,
  "target": 103.5,
  "risk_per_unit": 0.9200000000000017,
  "checks": {
    "levels": {"source": "provided", "r_multiple": 3.315217391304339, "setup_type": "fvg_entry", "timeframe": "1m"},
    "position_sizing": {"ok": true, "max_size": 2173.913043478257, "requested": null, "risk_fraction": 0.02},
    "same_symbol_conflict": {"ok": true, "rule": "opposite_direction", "open": []},
    "daily_loss": {"ok": true, "already_breached": false, "remaining_risk_budget": 3000.0, "daily_pnl": 0.0},
    "correlation": {"ok": true, "skipped": true, "max_abs_corr": null, "vs_symbol": null, "threshold": 0.7, "lookback": 60}
  }
}
```

### ML3 `po3_judas` — PASS (`approved: true`)

`session_type` is the implemented field (not `session`).

Request:

```json
{
  "schema_version": "1.1",
  "symbol": "BTCUSDT",
  "asset_class": "crypto",
  "setup_type": "po3_judas",
  "side": "short",
  "entry": 100.8,
  "stop": 104.49,
  "target": 90,
  "timeframe": "5m",
  "trigger_event_ids": ["swp-asia-high"],
  "confidence": 1.0,
  "session_type": "ny_am",
  "ts_ms": 1788576847635
}
```

Response:

```json
{
  "approved": true,
  "reason": "ok",
  "adjusted_position_size": 542.00542005,
  "size_unit": "asset",
  "entry": 100.8,
  "stop": 104.49,
  "target": 90.0,
  "risk_per_unit": 3.6899999999999977,
  "checks": {
    "levels": {"source": "provided", "r_multiple": 2.9268292682926838, "setup_type": "po3_judas", "timeframe": "5m"},
    "position_sizing": {"ok": true, "max_size": 542.0054200542008, "requested": null, "risk_fraction": 0.02},
    "same_symbol_conflict": {"ok": true, "rule": "opposite_direction", "open": []},
    "daily_loss": {"ok": true, "already_breached": false, "remaining_risk_budget": 3000.0, "daily_pnl": 0.0},
    "correlation": {"ok": true, "skipped": true, "max_abs_corr": null, "vs_symbol": null, "threshold": 0.7, "lookback": 60}
  }
}
```

### Rejects do not proceed — PASS

| Case | `POST /risk/validate` | `POST /signals` | Persist? |
|---|---|---|---|
| Oversized (`proposed_position_size` 100000 on ML1 levels) | `approved: false` `position_size_exceeds_limit` | HTTP **409** `risk_rejected` | no |
| Inverted long (stop 104 / target 99) | `approved: false` `invalid_levels` | HTTP **409** | no |
| Daily loss (fresh book `daily_pnl=0` cannot trip on live :8001) | injected `RiskState(daily_pnl=-3000)` → `daily_loss_limit` | HTTP **409** | no |

Suite: `test_ml_pr7_locked_bodies_approve`, `test_rejects_do_not_proceed_to_signals`, `test_validate_low_rr_invalid_levels`, `test_engine_rejects_when_daily_limit_hit`, `test_short_geometry_ok_and_inverted_fail`.
