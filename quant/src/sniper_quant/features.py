"""Kafka ``ensemble_features`` 15m snapshots (paper only).

Topic key = ``symbol``. Latest snapshot per symbol drives
``GET /picks/ensemble`` / ``/picks/categorized``.

``active_levels=false`` rows are skipped. Prefer ML ``ensemble_score``;
otherwise recompute from ``rank_components`` with locked weights
(setup_quality 40, confluence 20, kill_zone 15, volume 15, freshness 10).
ML publisher scale is **0–100** per field (canonical key ``confluence``;
``risk_adjusted`` is a legacy alias). Raw components are kept on the pick.

In-memory bus/store for tests. ``live_trading`` stays false.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from sniper_quant.bus import ENSEMBLE_FEATURES_TOPIC, InMemoryBus, consume_keyed_topic
from sniper_quant.config import Settings, get_settings
from sniper_quant.models import EnsembleFeatures, FeatureRankComponents, RankComponents, normalize_symbol

log = logging.getLogger(__name__)

# Locked recompute weights (points on a 0–100 score). confluence is canonical;
# risk_adjusted is a legacy alias handled in score_from_components.
FEATURE_WEIGHTS: dict[str, float] = {
    "setup_quality": 40.0,
    "confluence": 20.0,
    "kill_zone": 15.0,
    "volume": 15.0,
    "freshness": 10.0,
}


def _component_raw(components: Any, name: str) -> float | None:
    if name == "confluence":
        raw = getattr(components, "confluence", None)
        if raw is None:
            raw = getattr(components, "risk_adjusted", None)
        return None if raw is None else float(raw)
    raw = getattr(components, name, None)
    return None if raw is None else float(raw)


def _component_contrib(raw: float, weight: float) -> float:
    """Map one component onto its locked weight.

    * ``v ≤ 1`` → unit scale: ``weight * v``
    * ``1 < v ≤ 100`` → FE/ML 0–100: ``weight * (v / 100)``
    * else → ``min(v, weight)``
    """
    if raw <= 1.0:
        return weight * raw
    if raw <= 100.0:
        return weight * (raw / 100.0)
    return min(raw, weight)


def score_from_components(components: FeatureRankComponents | RankComponents | None) -> float | None:
    """Recompute 0–100 from ML ``rank_components``. None if no values.

    FE/ML lock is **0–100** per field. Canonical slot is ``confluence``
    (``risk_adjusted`` is a legacy alias). Unit values ≤1 still map as
    ``weight * v``.
    """
    if components is None:
        return None
    total = 0.0
    n = 0
    for name, weight in FEATURE_WEIGHTS.items():
        raw = _component_raw(components, name)
        if raw is None:
            continue
        total += _component_contrib(raw, weight)
        n += 1
    if n == 0:
        return None
    return max(0.0, min(100.0, total))


def parse_ensemble_features(
    payload: dict[str, Any],
    *,
    key: str | None = None,
) -> EnsembleFeatures:
    data = dict(payload)
    if not data.get("symbol") and key:
        data["symbol"] = key
    return EnsembleFeatures.model_validate(data)


class InMemoryEnsembleStore:
    """Latest-N 15m snapshots per symbol (tests / API cache)."""

    def __init__(self, maxlen_per_symbol: int = 64) -> None:
        self._rows: dict[str, deque[EnsembleFeatures]] = defaultdict(
            lambda: deque(maxlen=maxlen_per_symbol)
        )
        self.accepted = 0
        self.rejected = 0
        self.skipped_inactive = 0

    def upsert(self, feature: EnsembleFeatures) -> EnsembleFeatures:
        symbol = normalize_symbol(feature.symbol)
        stored = feature.model_copy(update={"symbol": symbol})
        bucket = self._rows[symbol]
        # Replace same ts_ms if the snapshot is republished.
        for i, row in enumerate(bucket):
            if row.ts_ms == stored.ts_ms:
                bucket[i] = stored
                break
        else:
            bucket.append(stored)
            if len(bucket) > 1 and bucket[-2].ts_ms > stored.ts_ms:
                ordered = sorted(bucket, key=lambda r: r.ts_ms)
                bucket.clear()
                bucket.extend(ordered)
        self.accepted += 1
        return stored

    def latest(
        self,
        symbol: str,
        *,
        as_of_ts_ms: int | None = None,
    ) -> EnsembleFeatures | None:
        rows = self._rows.get(normalize_symbol(symbol))
        if not rows:
            return None
        if as_of_ts_ms is None:
            return rows[-1]
        eligible = [row for row in rows if row.ts_ms <= int(as_of_ts_ms)]
        return eligible[-1] if eligible else None

    def all_latest(self, *, as_of_ts_ms: int | None = None) -> list[EnsembleFeatures]:
        out: list[EnsembleFeatures] = []
        for symbol in self._rows:
            row = self.latest(symbol, as_of_ts_ms=as_of_ts_ms)
            if row is not None:
                out.append(row)
        return out

    def dump(self, *, as_of_ts_ms: int | None = None) -> dict[str, Any]:
        latest = self.all_latest(as_of_ts_ms=as_of_ts_ms)
        return {
            "topic": ENSEMBLE_FEATURES_TOPIC,
            "live_trading": False,
            "refresh_sec": 900,
            "n": len(latest),
            "accepted": self.accepted,
            "rejected": self.rejected,
            "skipped_inactive": self.skipped_inactive,
            "symbols": [row.symbol for row in latest],
        }


class EnsembleFeatureService:
    """Parse + store ``ensemble_features`` payloads. Paper only."""

    def __init__(self, store: InMemoryEnsembleStore | None = None) -> None:
        self.store = store or InMemoryEnsembleStore()

    async def handle(
        self,
        payload: dict[str, Any],
        *,
        key: str | None = None,
    ) -> EnsembleFeatures | None:
        try:
            feature = parse_ensemble_features(payload, key=key)
        except (KeyError, TypeError, ValueError) as exc:
            self.store.rejected += 1
            log.warning("ensemble_features discarded (parse): %s payload=%s", exc, payload)
            return None
        stored = self.store.upsert(feature)
        if stored.active_levels is False:
            self.store.skipped_inactive += 1
            log.info(
                "ensemble_features inactive symbol=%s skip_reason=%s",
                stored.symbol,
                stored.skip_reason,
            )
        else:
            log.info(
                "ensemble_features accepted symbol=%s score=%s ts_ms=%s",
                stored.symbol,
                stored.ensemble_score,
                stored.ts_ms,
            )
        return stored


async def run_inmemory_ensemble_consumer(
    bus: InMemoryBus,
    service: EnsembleFeatureService,
    *,
    topic: str = ENSEMBLE_FEATURES_TOPIC,
) -> None:
    async def _on(payload: dict) -> None:
        await service.handle(payload)

    bus.subscribe(topic, _on)
    await bus.start()


async def run_ensemble_kafka_consumer(
    service: EnsembleFeatureService,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    group = getattr(settings, "kafka_group_ensemble", None) or "sniper-quant-ensemble"
    log.info(
        "consuming %s at %s group=%s (paper only)",
        ENSEMBLE_FEATURES_TOPIC,
        settings.kafka_bootstrap,
        group,
    )
    async for key, payload in consume_keyed_topic(
        settings.kafka_bootstrap,
        ENSEMBLE_FEATURES_TOPIC,
        group,
    ):
        await service.handle(payload, key=key)
