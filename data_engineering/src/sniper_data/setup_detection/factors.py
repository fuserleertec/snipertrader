"""Publish-only explainability for ``setup_signals``.

``contributing_factors`` are stable factor ids (labels, not chart ids).
Join a signal to the chart via ``id`` + ``trigger_event_ids``.

``factor_breakdown`` rows are ``{name, weight, score, note?}``.
``sum(score)`` is scaled to the candidate conviction (0–100);
``confidence = conviction / 100`` on the wire.
Never send these fields on ``POST /risk/validate``.
"""

from __future__ import annotations

from typing import Any, TypedDict

STABLE_FACTORS = (
    "liquidity_sweep",
    "mss",
    "fvg",
    "order_block",
    "vwap_reclaim",
    "vwap_band_extension",
    "vwap_pullback",
    "first_touch",
    "low_volume",
    "volume_confirm",
    "rejection_candle",
    "engulfing",
    "avwap",
    "htf_ob",
    "kill_zone",
    "multi_pattern",
    "trend_align",
)

STABLE_FACTOR_SET = frozenset(STABLE_FACTORS)

FACTOR_WEIGHTS: dict[str, float] = {
    "liquidity_sweep": 15.0,
    "mss": 15.0,
    "fvg": 15.0,
    "order_block": 15.0,
    "vwap_reclaim": 15.0,
    "vwap_band_extension": 20.0,
    "vwap_pullback": 15.0,
    "first_touch": 10.0,
    "low_volume": 10.0,
    "volume_confirm": 10.0,
    "rejection_candle": 15.0,
    "engulfing": 10.0,
    "avwap": 20.0,
    "htf_ob": 20.0,
    "kill_zone": 10.0,
    "multi_pattern": 10.0,
    "trend_align": 15.0,
}

FACTOR_NOTES: dict[str, str] = {
    "liquidity_sweep": "Session high/low sweep (chart via trigger_event_ids)",
    "mss": "Market-structure shift (chart via trigger_event_ids)",
    "fvg": "Fair-value gap at the entry zone",
    "order_block": "Order block overlapping the entry zone",
    "vwap_reclaim": "Close reclaimed session VWAP",
    "vwap_band_extension": "Session VWAP ±2σ/±3σ extension",
    "vwap_pullback": "Pullback into session VWAP or ±1σ",
    "first_touch": "First clean VWAP touch in the lookback window",
    "low_volume": "Bar volume below the tunable average fraction",
    "volume_confirm": "Volume / delta confirmation",
    "rejection_candle": "Rejection candle (pin / hammer / shooting star)",
    "engulfing": "Engulfing confirmation with the setup",
    "avwap": "Anchored VWAP line (Phase 2 nested bands)",
    "htf_ob": "Higher-timeframe order block confluence",
    "kill_zone": "Active kill-zone window",
    "multi_pattern": "More than one setup fired same symbol+side",
    "trend_align": "Price aligned with rising/falling session VWAP",
}


class FactorRow(TypedDict, total=False):
    name: str
    weight: float
    score: float
    note: str


def factor_row(name: str, score: float | None = None, *, note: str | None = None) -> FactorRow:
    if name not in STABLE_FACTOR_SET:
        raise ValueError(f"unknown contributing factor {name!r}; expected one of {sorted(STABLE_FACTOR_SET)}")
    weight = FACTOR_WEIGHTS[name]
    row: FactorRow = {
        "name": name,
        "weight": weight,
        "score": float(score) if score is not None else weight,
    }
    text = note if note is not None else FACTOR_NOTES.get(name)
    if text:
        row["note"] = text
    return row


def add_factor(
    rows: list[FactorRow],
    name: str,
    score: float | None = None,
    *,
    note: str | None = None,
) -> list[FactorRow]:
    if any(r["name"] == name for r in rows):
        return rows
    rows.append(factor_row(name, score, note=note))
    return rows


def scale_breakdown(rows: list[FactorRow], conviction: int) -> list[FactorRow]:
    """Scale row scores so ``sum(score)`` equals ``conviction`` (0–100)."""
    target = max(0.0, min(100.0, float(conviction)))
    if not rows:
        return rows
    total = sum(float(r["score"]) for r in rows)
    if total <= 0:
        share = target / len(rows)
        for row in rows:
            row["score"] = round(share, 2)
    else:
        scale = target / total
        for row in rows:
            row["score"] = round(float(row["score"]) * scale, 2)
    drift = round(target - sum(float(r["score"]) for r in rows), 2)
    rows[-1]["score"] = round(float(rows[-1]["score"]) + drift, 2)
    return rows


def explain(
    names: list[str],
    *,
    conviction: int,
    scores: dict[str, float] | None = None,
    notes: dict[str, str] | None = None,
) -> tuple[list[str], list[FactorRow]]:
    rows: list[FactorRow] = []
    for name in names:
        extra_score = scores.get(name) if scores else None
        extra_note = notes.get(name) if notes else None
        add_factor(rows, name, extra_score, note=extra_note)
    rows = scale_breakdown(rows, conviction)
    return [r["name"] for r in rows], rows


def breakdown_payload(rows: list[FactorRow] | list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not rows:
        return None
    out: list[dict[str, Any]] = []
    for row in rows:
        item = {"name": row["name"], "weight": float(row["weight"]), "score": float(row["score"])}
        if row.get("note"):
            item["note"] = row["note"]
        out.append(item)
    return out
