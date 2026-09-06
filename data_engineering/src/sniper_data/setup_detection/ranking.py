"""Dynamic Quantum Ensemble ranking (paper / P0).

Weights (locked for FE / Quant ``GET /picks/ensemble``)::

    setup_quality  0.40
    confluence     0.20
    kill_zone      0.15
    volume         0.15
    freshness      0.10

Each component is 0–100. ``ensemble_score`` is the weighted sum, also 0–100.
Ranking is computed from the current market-state inputs (conviction, session
VWAP extension, kill-zone, volume/delta, recency). It is **not** a hardcoded
ticker list.

Publish-only: attach ``ensemble_score`` + ``rank_components`` on
``setup_signals`` after risk approval. Never send these on
``POST /risk/validate``.

Kafka ``ensemble_features`` carries a 15-minute book snapshot. In-memory
``EnsembleBook`` + ``GET /v1/picks/ensemble`` map to Quant pick fields.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from sniper_data.models import SCHEMA_VERSION, AssetClass, VWAPValues
from sniper_data.symbols import infer_asset_class, normalize_symbol

ENSEMBLE_WEIGHTS: dict[str, float] = {
    "setup_quality": 0.40,
    "confluence": 0.20,
    "kill_zone": 0.15,
    "volume": 0.15,
    "freshness": 0.10,
}

ENSEMBLE_FEATURES_TOPIC = "ensemble_features"
DEFAULT_RANK_WINDOW_MS = 15 * 60 * 1000
TOP_N = 10

# Quant GET /picks/ensemble field map (P0 Quantum Ensemble Picks).
PICKS_ENSEMBLE_FIELDS = (
    "symbol",
    "rank",
    "score",
    "ensemble_score",
    "confidence",
    "best_confidence",
    "conviction",
    "signal",
    "side",
    "category",
    "setup_type",
    "entry",
    "target",
    "rank_components",
    "contributing_factors",
    "active_levels",
    "id",
    "ts_ms",
)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _round(value: float) -> float:
    return round(_clamp(value), 2)


def vwap_extension_score(entry: float | None, vwap: VWAPValues | None) -> float:
    """0–100 from |entry − session VWAP| / σ. 0σ → 0, ≥2σ → 100."""
    if entry is None or vwap is None:
        return 0.0
    sigma = float(vwap.sigma) if vwap.sigma and vwap.sigma > 0 else abs(float(vwap.band_p1) - float(vwap.vwap))
    if sigma <= 0:
        return 0.0
    ext = abs(float(entry) - float(vwap.vwap)) / sigma
    return _clamp(ext / 2.0 * 100.0)


def confluence_score(
    *,
    factors: Iterable[str] | None,
    entry: float | None = None,
    vwap: VWAPValues | None = None,
    multi_pattern: bool = False,
) -> float:
    names = [n for n in (factors or []) if n]
    factor_part = _clamp(len(names) / 6.0 * 100.0)
    ext = vwap_extension_score(entry, vwap)
    bonus = 20.0 if multi_pattern or "multi_pattern" in names else 0.0
    return _clamp(0.55 * factor_part + 0.35 * ext + bonus)


def freshness_score(ts_ms: int, *, now_ms: int | None = None, window_ms: int = DEFAULT_RANK_WINDOW_MS) -> float:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    age = max(0, now - int(ts_ms))
    if window_ms <= 0:
        return 100.0
    return _clamp(100.0 * (1.0 - min(1.0, age / float(window_ms))))


def score_ensemble(
    *,
    conviction: int | float,
    contributing_factors: Iterable[str] | None = None,
    kill_zone_aligned: bool = False,
    volume_confirmed: bool = False,
    entry: float | None = None,
    vwap: VWAPValues | None = None,
    ts_ms: int = 0,
    now_ms: int | None = None,
    window_ms: int = DEFAULT_RANK_WINDOW_MS,
    risk_reward: float | None = None,
) -> tuple[float, dict[str, float]]:
    """Return ``(ensemble_score, rank_components)`` from live inputs."""
    factors = list(contributing_factors or [])
    setup_quality = _clamp(float(conviction))
    # Light risk-adjusted tilt inside setup_quality (not a separate wire field).
    if risk_reward is not None and risk_reward > 0:
        setup_quality = _clamp(0.85 * setup_quality + 0.15 * _clamp(float(risk_reward) / 3.0 * 100.0))
    components = {
        "setup_quality": _round(setup_quality),
        "confluence": _round(confluence_score(factors=factors, entry=entry, vwap=vwap)),
        "kill_zone": _round(100.0 if kill_zone_aligned else 0.0),
        "volume": _round(100.0 if volume_confirmed or "volume_confirm" in factors else 0.0),
        "freshness": _round(freshness_score(ts_ms, now_ms=now_ms, window_ms=window_ms)),
    }
    score = sum(ENSEMBLE_WEIGHTS[k] * components[k] for k in ENSEMBLE_WEIGHTS)
    return _round(score), components


def category_for(symbol: str, asset_class: str | AssetClass | None = None) -> str:
    if asset_class is not None:
        return asset_class.value if isinstance(asset_class, AssetClass) else str(asset_class)
    return infer_asset_class(normalize_symbol(symbol)).value


def signal_stance(side: str | None) -> str:
    if side == "long":
        return "Buy"
    if side == "short":
        return "Sell"
    return "Hold"


def to_picks_ensemble_row(payload: dict[str, Any], *, rank: int) -> dict[str, Any]:
    """Map a published ``setup_signals`` row to Quant ``GET /picks/ensemble``.

    Locked: ``score`` ← ``ensemble_score``, ``confidence`` ← ``best_confidence``.
    Raw ``rank_components`` and ``contributing_factors`` are passed through.
    """
    score = payload.get("ensemble_score")
    if score is None:
        score = payload.get("score")
    if score is None:
        raw_conf = payload.get("best_confidence", payload.get("confidence"))
        score = round(float(raw_conf or 0) * 100.0, 2)
    side = payload.get("side")
    best_confidence = payload.get("best_confidence")
    if best_confidence is None:
        best_confidence = payload.get("confidence")
    if best_confidence is None and score is not None:
        best_confidence = round(float(score) / 100.0, 4)
    return {
        "symbol": payload.get("symbol"),
        "rank": rank,
        "score": score,
        "ensemble_score": score,
        "confidence": best_confidence,
        "best_confidence": best_confidence,
        "conviction": score,
        "signal": signal_stance(side),
        "side": side,
        "category": payload.get("category") or category_for(str(payload.get("symbol") or ""), payload.get("asset_class")),
        "setup_type": payload.get("setup_type"),
        "entry": payload.get("entry"),
        "target": payload.get("target"),
        "rank_components": payload.get("rank_components"),
        "contributing_factors": payload.get("contributing_factors"),
        "active_levels": payload.get("active_levels", True),
        "id": payload.get("id"),
        "ts_ms": payload.get("ts_ms"),
    }


def rank_top(
    signals: Iterable[dict[str, Any]],
    *,
    limit: int = TOP_N,
    now_ms: int | None = None,
    window_ms: int = DEFAULT_RANK_WINDOW_MS,
    universe: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Deterministic top-N by ``ensemble_score`` then ``ts_ms`` (stable, not hardcoded)."""
    raw_rows = [dict(r) for r in signals if isinstance(r, dict) and r.get("symbol")]
    if now_ms is None:
        ts_vals = [int(r.get("ts_ms") or 0) for r in raw_rows]
        now = max(ts_vals) if ts_vals else int(time.time() * 1000)
        # A single paper/scan batch should not drop its own rows when fixture
        # bar times span more than the 15m refresh cadence.
        if ts_vals:
            window_ms = max(int(window_ms), now - min(ts_vals))
    else:
        now = now_ms
    allowed = {normalize_symbol(s) for s in universe} if universe is not None else None
    scored: list[dict[str, Any]] = []
    for raw in raw_rows:
        if raw.get("active_levels") is False or raw.get("skip_reason"):
            continue
        ts = int(raw.get("ts_ms") or 0)
        if window_ms and ts and now - ts > window_ms:
            continue
        sym = raw.get("symbol")
        if not sym:
            continue
        if allowed is not None and normalize_symbol(str(sym)) not in allowed:
            continue
        row = dict(raw)
        if row.get("ensemble_score") is None:
            score, parts = score_ensemble(
                conviction=int(round(float(row.get("confidence") or 0) * 100.0)),
                contributing_factors=row.get("contributing_factors") or [],
                entry=row.get("entry"),
                ts_ms=ts,
                now_ms=now,
                window_ms=window_ms,
            )
            row["ensemble_score"] = score
            row.setdefault("rank_components", parts)
        scored.append(row)
    scored.sort(key=lambda r: (-float(r.get("ensemble_score") or 0), int(r.get("ts_ms") or 0), str(r.get("symbol") or "")))
    top = scored[: max(1, min(int(limit), UNIVERSE_TOP_CAP))]
    return [to_picks_ensemble_row(row, rank=i + 1) for i, row in enumerate(top)]


UNIVERSE_TOP_CAP = 20


def ensemble_features_snapshot(
    picks: list[dict[str, Any]],
    *,
    as_of_ts_ms: int | None = None,
    window_ms: int = DEFAULT_RANK_WINDOW_MS,
    universe: list[str] | None = None,
    signals: list[dict[str, Any]] | None = None,
    skipped: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_picks = [p for p in picks if p.get("active_levels", True) is not False]
    return {
        "schema_version": SCHEMA_VERSION,
        "topic": ENSEMBLE_FEATURES_TOPIC,
        "as_of_ts_ms": as_of_ts_ms if as_of_ts_ms is not None else int(time.time() * 1000),
        "window_ms": window_ms,
        "refresh_seconds": 900,
        "live_trading": False,
        "weights": dict(ENSEMBLE_WEIGHTS),
        "universe": list(universe or []),
        "picks": active_picks,
        "signals": list(signals or []),
        "skipped": list(skipped or []),
        "count": len(active_picks),
    }


def _is_inactive(row: dict[str, Any]) -> bool:
    if row.get("active_levels") is False:
        return True
    if row.get("skip_reason"):
        return True
    return False


def consume_picks_ensemble(
    *,
    features: dict[str, Any] | None = None,
    signals: Iterable[dict[str, Any]] | None = None,
    limit: int = TOP_N,
    universe: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Quant LOCKED consumer: prefer ``ensemble_features``, else ``setup_signals`` mirrors.

    Skips ``active_levels=false`` / ``skip_reason``. Maps
    ``score`` ← ``ensemble_score``, ``confidence`` ← ``best_confidence``.
    """
    skipped: list[dict[str, Any]] = []
    source = "setup_signals"
    raw_picks: list[dict[str, Any]] = []
    if features and (features.get("picks") or features.get("signals")):
        source = ENSEMBLE_FEATURES_TOPIC
        skipped.extend(list(features.get("skipped") or []))
        raw_picks = list(features.get("picks") or [])
        if not raw_picks and features.get("signals"):
            raw_picks = rank_top(features["signals"], limit=limit, universe=universe)
    else:
        raw_picks = rank_top(list(signals or []), limit=limit, universe=universe)

    allowed = {normalize_symbol(s) for s in universe} if universe is not None else None
    picks: list[dict[str, Any]] = []
    for row in raw_picks:
        if _is_inactive(row):
            skipped.append({"symbol": row.get("symbol"), "active_levels": False, "skip_reason": row.get("skip_reason")})
            continue
        sym = row.get("symbol")
        if allowed is not None and (not sym or normalize_symbol(str(sym)) not in allowed):
            continue
        mapped = to_picks_ensemble_row(row, rank=int(row.get("rank") or len(picks) + 1))
        mapped["rank"] = len(picks) + 1
        picks.append(mapped)
        if len(picks) >= max(1, min(int(limit), UNIVERSE_TOP_CAP)):
            break
    return {
        "source": source,
        "picks": picks,
        "skipped": skipped,
        "fields": list(PICKS_ENSEMBLE_FIELDS),
        "weights": dict(ENSEMBLE_WEIGHTS),
        "refresh_seconds": 900,
        "live_trading": False,
        "count": len(picks),
    }


@dataclass
class EnsembleBook:
    """In-memory published-signal book for paper FE / CLI top-10."""

    window_ms: int = DEFAULT_RANK_WINDOW_MS
    signals: list[dict[str, Any]] = field(default_factory=list)
    latest_features: dict[str, Any] | None = None

    def record(self, payload: dict[str, Any]) -> None:
        self.signals.append(dict(payload))

    def record_features(self, payload: dict[str, Any]) -> None:
        self.latest_features = dict(payload)

    def top(
        self,
        *,
        limit: int = TOP_N,
        now_ms: int | None = None,
        universe: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        consumed = consume_picks_ensemble(
            features=self.latest_features,
            signals=self.signals,
            limit=limit,
            universe=universe,
        )
        return consumed["picks"]

    def snapshot(self, **kwargs: Any) -> dict[str, Any]:
        picks = rank_top(
            self.signals,
            limit=int(kwargs.get("limit") or TOP_N),
            now_ms=kwargs.get("now_ms"),
            window_ms=self.window_ms,
            universe=kwargs.get("universe"),
        )
        snap = ensemble_features_snapshot(
            picks,
            as_of_ts_ms=kwargs.get("now_ms"),
            window_ms=self.window_ms,
            universe=list(kwargs.get("universe") or []),
            signals=list(self.signals),
            skipped=list(kwargs.get("skipped") or []),
        )
        self.latest_features = snap
        return snap
