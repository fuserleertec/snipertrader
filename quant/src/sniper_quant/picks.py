"""Quantum Ensemble Picks — paper/signal-book ranking (no live trading).

``GET /picks/ensemble`` returns a dynamic top-10. Scores come from the
paper/signal book (recent approved publishes) plus an optional ML overlay.
When the book is thin, an in-memory demo universe (≥20 symbols) fills
remaining slots with a refresh-bucket hash so the list rotates every
``REFRESH_SEC`` (900s / 15 minutes) instead of being a fixed mock.

Paper path only. ``live_trading`` stays false. No Alpaca / broker.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from sniper_quant.models import (
    AssetClass,
    CategorizedPick,
    CategorizedPicksResponse,
    EnsemblePick,
    EnsemblePicksResponse,
    PickCategory,
    SignalStatus,
    StoredSignal,
    normalize_symbol,
)
from sniper_quant.setups import SETUP_TYPES

REFRESH_SEC = 900
TOP_N = 10
N_LIVE_SETUPS = len(SETUP_TYPES)

# Book mix (weights on a 0–100 scale). Optional ML overlay is additive.
W_RECENCY = 0.40
W_CONFIDENCE = 0.35
W_DIVERSITY = 0.25
RECENCY_SATURATION = 3.0  # ~3 half-life-weighted approvals saturate recency
ML_BOOST_MAX = 15.0  # added as ML_BOOST_MAX * ml_score (ml_score in [0, 1])
DEMO_SCORE_SCALE = 20.0  # synthetic-only ceiling so a real book outranks demo

# Rotating in-memory universe (≥20). Used when the book has fewer symbols
# than TOP_N, and as a scored backdrop so empty books still rotate.
DEMO_UNIVERSE: tuple[tuple[str, AssetClass], ...] = (
    ("BTCUSDT", AssetClass.CRYPTO),
    ("ETHUSDT", AssetClass.CRYPTO),
    ("SOLUSDT", AssetClass.CRYPTO),
    ("BNBUSDT", AssetClass.CRYPTO),
    ("XRPUSDT", AssetClass.CRYPTO),
    ("ADAUSDT", AssetClass.CRYPTO),
    ("AVAXUSDT", AssetClass.CRYPTO),
    ("DOGEUSDT", AssetClass.CRYPTO),
    ("LINKUSDT", AssetClass.CRYPTO),
    ("DOTUSDT", AssetClass.CRYPTO),
    ("LTCUSDT", AssetClass.CRYPTO),
    ("ATOMUSDT", AssetClass.CRYPTO),
    ("AAPL", AssetClass.EQUITY),
    ("MSFT", AssetClass.EQUITY),
    ("NVDA", AssetClass.EQUITY),
    ("AMZN", AssetClass.EQUITY),
    ("META", AssetClass.EQUITY),
    ("GOOGL", AssetClass.EQUITY),
    ("TSLA", AssetClass.EQUITY),
    ("AMD", AssetClass.EQUITY),
    ("NFLX", AssetClass.EQUITY),
    ("SPY", AssetClass.EQUITY),
    ("ES", AssetClass.FUTURES),
    ("NQ", AssetClass.FUTURES),
    ("CL", AssetClass.FUTURES),
    ("GC", AssetClass.FUTURES),
)

# setup_type → FE category for GET /picks/categorized
SETUP_TO_CATEGORY: dict[str, PickCategory] = {
    "vwap_pullback_cont": PickCategory.MOMENTUM,
    "sweep_reclaim": PickCategory.MEAN_REVERSION,
    "fvg_entry": PickCategory.MEAN_REVERSION,
    "po3_judas": PickCategory.MEAN_REVERSION,
    "sd_extension_fade": PickCategory.MEAN_REVERSION,
    "avwap_ob_confluence": PickCategory.CONFLUENCE,
}

_DEMO_ASSET: dict[str, AssetClass] = {sym: ac for sym, ac in DEMO_UNIVERSE}

LN2 = math.log(2.0)


def refresh_bucket(as_of_ts_ms: int, refresh_sec: int = REFRESH_SEC) -> int:
    """Integer 15-minute bucket. Ranking of a thin book rotates with this."""
    width = max(int(refresh_sec), 1) * 1000
    return int(as_of_ts_ms) // width


def demo_unit_score(symbol: str, bucket: int) -> float:
    """Deterministic 0–1 unit from ``sha256(symbol:bucket)``."""
    digest = hashlib.sha256(f"{normalize_symbol(symbol)}:{bucket}".encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def categorize_setups(setup_types: Sequence[str]) -> PickCategory:
    """Map a symbol's live ``setup_types`` to one FE category.

    - ``vwap_pullback_cont`` → momentum (trend continuation)
    - ``sweep_reclaim``, ``fvg_entry``, ``po3_judas``, ``sd_extension_fade``
      → mean_reversion (sweep/fade/mitigation)
    - ``avwap_ob_confluence`` → confluence
    - no setups (demo fill) → other
    - mixed momentum + mean_reversion (no confluence setup) → confluence
    """
    cats = {SETUP_TO_CATEGORY.get(str(name), PickCategory.OTHER) for name in setup_types}
    if not cats:
        return PickCategory.OTHER
    cats.discard(PickCategory.OTHER)
    if not cats:
        return PickCategory.OTHER
    if PickCategory.CONFLUENCE in cats:
        return PickCategory.CONFLUENCE
    if cats == {PickCategory.MOMENTUM}:
        return PickCategory.MOMENTUM
    if cats == {PickCategory.MEAN_REVERSION}:
        return PickCategory.MEAN_REVERSION
    return PickCategory.CONFLUENCE


def infer_asset_class(symbol: str, fallback: AssetClass | None = None) -> AssetClass:
    cleaned = normalize_symbol(symbol)
    if cleaned in _DEMO_ASSET:
        return _DEMO_ASSET[cleaned]
    if fallback is not None:
        return fallback
    if cleaned.endswith(("USDT", "USDC", "BUSD")):
        return AssetClass.CRYPTO
    return AssetClass.EQUITY


def parse_ml_scores(raw: str | None) -> dict[str, float]:
    """Parse optional ``ml_scores`` query JSON ``{\"BTCUSDT\": 0.82}``.

    Values are clamped to ``[0, 1]``. Empty / omitted → ``{}``.
    """
    if raw is None or str(raw).strip() == "":
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("ml_scores must be a JSON object of symbol → 0..1")
    out: dict[str, float] = {}
    for key, value in data.items():
        out[normalize_symbol(str(key))] = max(0.0, min(1.0, float(value)))
    return out


def _half_life_weight(age_sec: float, half_life_sec: float) -> float:
    if age_sec < 0:
        age_sec = 0.0
    hl = max(float(half_life_sec), 1.0)
    return math.exp(-LN2 * age_sec / hl)


def _setup_name(row: StoredSignal) -> str:
    setup = row.setup_type
    return setup.value if hasattr(setup, "value") else str(setup)


def _is_approved(row: StoredSignal) -> bool:
    """Persisted non-cancelled rows already passed risk (the paper book)."""
    return row.status is not SignalStatus.CANCELLED


def _book_components(
    rows: Sequence[StoredSignal],
    *,
    as_of_ts_ms: int,
    refresh_sec: int,
) -> tuple[float, float, float, list[str], str | None]:
    """Return ``(recency_norm, mean_conf, diversity, setup_types, ref_session)``."""
    approved = [r for r in rows if _is_approved(r)]
    if not approved:
        return 0.0, 0.0, 0.0, [], None
    recency_sum = 0.0
    confs: list[float] = []
    setups: set[str] = set()
    newest = max(approved, key=lambda r: r.ts_ms)
    for row in approved:
        age_sec = (as_of_ts_ms - row.ts_ms) / 1000.0
        recency_sum += _half_life_weight(age_sec, refresh_sec)
        if row.confidence is not None:
            confs.append(max(0.0, min(1.0, float(row.confidence))))
        setups.add(_setup_name(row))
    recency_norm = min(1.0, recency_sum / RECENCY_SATURATION)
    mean_conf = (sum(confs) / len(confs)) if confs else 0.0
    diversity = len(setups) / float(N_LIVE_SETUPS)
    ordered = sorted(setups)
    return recency_norm, mean_conf, diversity, ordered, newest.ref_session


def score_symbol(
    symbol: str,
    rows: Sequence[StoredSignal],
    *,
    as_of_ts_ms: int,
    ml_score: float = 0.0,
    refresh_sec: int = REFRESH_SEC,
) -> dict[str, Any]:
    """Score one symbol. Real book terms dominate the demo hash."""
    recency_norm, mean_conf, diversity, setups, ref_session = _book_components(
        rows, as_of_ts_ms=as_of_ts_ms, refresh_sec=refresh_sec
    )
    ml = max(0.0, min(1.0, float(ml_score)))
    book_score = 100.0 * (
        W_RECENCY * recency_norm + W_CONFIDENCE * mean_conf + W_DIVERSITY * diversity
    )
    has_book = bool(rows) and any(_is_approved(r) for r in rows)
    bucket = refresh_bucket(as_of_ts_ms, refresh_sec)
    if has_book:
        score = book_score + ML_BOOST_MAX * ml
        source = "book"
        confidence = mean_conf
        notes = (
            f"book recency={recency_norm:.3f} conf={mean_conf:.3f} "
            f"diversity={diversity:.3f} ml={ml:.3f}"
        )
    else:
        unit = demo_unit_score(symbol, bucket)
        score = DEMO_SCORE_SCALE * unit + ML_BOOST_MAX * ml
        source = "demo"
        confidence = unit
        notes = f"demo_universe bucket={bucket} hash={unit:.3f} ml={ml:.3f}"
    asset = infer_asset_class(
        symbol,
        fallback=rows[-1].asset_class if rows else None,
    )
    if rows:
        # Prefer the most recent row's asset_class when the book has it.
        newest = max(rows, key=lambda r: r.ts_ms)
        asset = newest.asset_class
    return {
        "symbol": normalize_symbol(symbol),
        "asset_class": asset,
        "score": round(score, 4),
        "setup_types": setups,
        "confidence": round(confidence, 4),
        "ref_session": ref_session,
        "notes": notes,
        "source": source,
    }


def rank_ensemble(
    rows: Sequence[StoredSignal],
    *,
    as_of_ts_ms: int | None = None,
    ml_scores: Mapping[str, float] | None = None,
    top_n: int = TOP_N,
    refresh_sec: int = REFRESH_SEC,
) -> EnsemblePicksResponse:
    """Rank the demo universe plus every symbol present in ``rows``.

    Always considers ≥20 symbols (``DEMO_UNIVERSE``). Book symbols not in
    the demo list are added. Returns the top ``top_n`` (default 10).
    """
    now = int(as_of_ts_ms if as_of_ts_ms is not None else time.time() * 1000)
    overlay = {normalize_symbol(k): float(v) for k, v in (ml_scores or {}).items()}
    by_symbol: dict[str, list[StoredSignal]] = defaultdict(list)
    for row in rows:
        by_symbol[normalize_symbol(row.symbol)].append(row)

    universe: dict[str, AssetClass] = {sym: ac for sym, ac in DEMO_UNIVERSE}
    for symbol, group in by_symbol.items():
        universe.setdefault(symbol, infer_asset_class(symbol, group[-1].asset_class))
    for symbol in overlay:
        universe.setdefault(symbol, infer_asset_class(symbol))

    scored = _score_universe(
        universe,
        by_symbol,
        overlay,
        as_of_ts_ms=now,
        refresh_sec=refresh_sec,
    )
    n = max(1, min(int(top_n), 20))
    items = [
        EnsemblePick(
            rank=i + 1,
            symbol=row["symbol"],
            asset_class=row["asset_class"],
            score=row["score"],
            setup_types=row["setup_types"],
            confidence=row["confidence"],
            ref_session=row["ref_session"],
            notes=row["notes"],
        )
        for i, row in enumerate(scored[:n])
    ]
    return EnsemblePicksResponse(
        as_of_ts_ms=now,
        refresh_sec=refresh_sec,
        items=items,
    )


def _score_universe(
    universe: Mapping[str, AssetClass],
    by_symbol: Mapping[str, Sequence[StoredSignal]],
    overlay: Mapping[str, float],
    *,
    as_of_ts_ms: int,
    refresh_sec: int,
) -> list[dict[str, Any]]:
    scored = [
        score_symbol(
            symbol,
            by_symbol.get(symbol, []),
            as_of_ts_ms=as_of_ts_ms,
            ml_score=overlay.get(symbol, 0.0),
            refresh_sec=refresh_sec,
        )
        for symbol in universe
    ]
    scored.sort(key=lambda item: (-item["score"], item["symbol"]))
    return scored


def rank_categorized(
    rows: Sequence[StoredSignal],
    *,
    as_of_ts_ms: int | None = None,
    asset_class: AssetClass | None = None,
    limit: int = 20,
    refresh_sec: int = REFRESH_SEC,
) -> CategorizedPicksResponse:
    """Same book/demo scores as ensemble, tagged with a FE category. ≤20 rows."""
    now = int(as_of_ts_ms if as_of_ts_ms is not None else time.time() * 1000)
    by_symbol: dict[str, list[StoredSignal]] = defaultdict(list)
    for row in rows:
        by_symbol[normalize_symbol(row.symbol)].append(row)

    universe: dict[str, AssetClass] = {sym: ac for sym, ac in DEMO_UNIVERSE}
    for symbol, group in by_symbol.items():
        universe.setdefault(symbol, infer_asset_class(symbol, group[-1].asset_class))

    scored = _score_universe(
        universe,
        by_symbol,
        {},
        as_of_ts_ms=now,
        refresh_sec=refresh_sec,
    )
    if asset_class is not None:
        scored = [row for row in scored if row["asset_class"] is asset_class]
    n = max(1, min(int(limit), 20))
    items = [
        CategorizedPick(
            rank=i + 1,
            symbol=row["symbol"],
            asset_class=row["asset_class"],
            category=categorize_setups(row["setup_types"]),
            score=row["score"],
            setup_types=row["setup_types"],
            confidence=row["confidence"],
        )
        for i, row in enumerate(scored[:n])
    ]
    return CategorizedPicksResponse(
        as_of_ts_ms=now,
        refresh_sec=refresh_sec,
        items=items,
    )
