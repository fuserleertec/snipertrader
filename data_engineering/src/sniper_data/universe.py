"""Configurable paper universe + locked top-N ranking contract.

PM lock
-------
``GET /v1/universe/top?limit=10|20`` is the authoritative shared contract
for ML / Quant / Frontend. It **replaces** any provisional ``SETUP_UNIVERSE``.
Redis backing key: ``universe:active`` (same JSON envelope, typically
computed for the full configured set so ``?limit=10`` is a prefix slice).

``live_trading`` is always ``false``. Ranking scores are DE inputs
(volume / volatility / session activity / levels / pattern counts) — not
Frontend display names.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from pydantic import BaseModel, Field

from sniper_data.models import AssetClass
from sniper_data.symbols import infer_asset_class, normalize_symbol

log = logging.getLogger(__name__)

MAX_UNIVERSE_SYMBOLS = 20
DEFAULT_UNIVERSE_CSV = (
    "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AAPL,MSFT,NVDA,SPY,ES,NQ,CL,GC"
)
REDIS_UNIVERSE_ACTIVE = "universe:active"
REDIS_UNIVERSE_CONFIG = "universe:config"

SCORE_INPUTS = (
    "volume",
    "volatility",
    "session_active",
    "levels_available",
    "pattern_count",
)

# Weights for the paper ranking. Documented; not an FE field.
_WEIGHTS = {
    "volume": 0.30,
    "volatility": 0.25,
    "session_active": 0.20,
    "levels_available": 0.15,
    "pattern_count": 0.10,
}


class UniverseMember(BaseModel):
    """One row of the locked ``/v1/universe/top`` ``symbols`` array."""

    symbol: str
    asset_class: AssetClass
    rank: int
    score: float
    volume: float = 0.0
    volatility: float = 0.0
    session_active: bool = False
    levels_available: int = 0
    pattern_count: int = 0


class UniverseTop(BaseModel):
    """Locked GET /v1/universe/top envelope. Keep this shape stable."""

    as_of_ts_ms: int
    limit: int
    live_trading: bool = False
    score_inputs: list[str] = Field(default_factory=lambda: list(SCORE_INPUTS))
    symbols: list[UniverseMember] = Field(default_factory=list)


class UniverseConfig(BaseModel):
    """Helper payload for Redis ``universe:config`` / GET /v1/universe."""

    as_of_ts_ms: int
    live_trading: bool = False
    max_symbols: int = MAX_UNIVERSE_SYMBOLS
    cadence_s: int = 900
    symbols: list[str] = Field(default_factory=list)
    asset_classes: dict[str, str] = Field(default_factory=dict)


def parse_universe(*candidates: str | None) -> list[str]:
    """First non-empty CSV wins. Dedupe, normalize, cap at ``MAX_UNIVERSE_SYMBOLS``."""
    raw = ""
    for candidate in candidates:
        if candidate and str(candidate).strip():
            raw = str(candidate)
            break
    if not raw.strip():
        raw = DEFAULT_UNIVERSE_CSV
    seen: list[str] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            symbol = normalize_symbol(token)
        except ValueError:
            log.warning("skipping unnormalizable universe token %r", token)
            continue
        if symbol in seen:
            continue
        seen.append(symbol)
        if len(seen) >= MAX_UNIVERSE_SYMBOLS:
            extras = [p.strip() for p in raw.split(",") if p.strip()]
            if len(extras) > MAX_UNIVERSE_SYMBOLS:
                log.warning(
                    "universe truncated to %s symbols (max %s)",
                    MAX_UNIVERSE_SYMBOLS,
                    MAX_UNIVERSE_SYMBOLS,
                )
            break
    return seen or [normalize_symbol(s) for s in DEFAULT_UNIVERSE_CSV.split(",")]


def clamp_top_limit(limit: int) -> int:
    """Accept 10 or 20 (required). Also allow 1–20 so callers can slice."""
    value = int(limit)
    if value < 1 or value > MAX_UNIVERSE_SYMBOLS:
        raise ValueError(f"limit must be 1–{MAX_UNIVERSE_SYMBOLS} (10 and 20 are the locked sizes)")
    return value


def classify_universe(symbols: list[str]) -> dict[str, str]:
    return {s: infer_asset_class(s).value for s in symbols}


def config_payload(
    symbols: list[str],
    *,
    cadence_s: int = 900,
    now_ms: int | None = None,
) -> UniverseConfig:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    return UniverseConfig(
        as_of_ts_ms=now,
        live_trading=False,
        max_symbols=MAX_UNIVERSE_SYMBOLS,
        cadence_s=int(cadence_s),
        symbols=list(symbols),
        asset_classes=classify_universe(symbols),
    )


def _norm_volume(volume: float, peak: float) -> float:
    if peak <= 0:
        return 0.0
    return min(1.0, math.log1p(max(0.0, volume)) / math.log1p(peak))


def _norm_volatility(volatility: float) -> float:
    return min(1.0, max(0.0, float(volatility)) / 0.05)


def score_metrics(
    *,
    volume: float,
    volatility: float,
    session_active: bool,
    levels_available: int,
    pattern_count: int,
    peak_volume: float,
) -> float:
    parts = {
        "volume": _norm_volume(volume, peak_volume),
        "volatility": _norm_volatility(volatility),
        "session_active": 1.0 if session_active else 0.0,
        "levels_available": min(1.0, max(0, levels_available) / 5.0),
        "pattern_count": min(1.0, max(0, pattern_count) / 8.0),
    }
    return round(sum(_WEIGHTS[k] * parts[k] for k in SCORE_INPUTS), 6)


def rank_rows(rows: list[dict[str, Any]], *, limit: int) -> list[UniverseMember]:
    peak = max((float(r.get("volume") or 0.0) for r in rows), default=0.0)
    scored: list[UniverseMember] = []
    for raw in rows:
        symbol = normalize_symbol(raw["symbol"])
        klass = infer_asset_class(symbol, raw.get("asset_class"))
        volume = float(raw.get("volume") or 0.0)
        volatility = float(raw.get("volatility") or 0.0)
        session_active = bool(raw.get("session_active"))
        levels = int(raw.get("levels_available") or 0)
        patterns = int(raw.get("pattern_count") or 0)
        scored.append(
            UniverseMember(
                symbol=symbol,
                asset_class=klass,
                rank=0,
                score=score_metrics(
                    volume=volume,
                    volatility=volatility,
                    session_active=session_active,
                    levels_available=levels,
                    pattern_count=patterns,
                    peak_volume=peak,
                ),
                volume=volume,
                volatility=volatility,
                session_active=session_active,
                levels_available=levels,
                pattern_count=patterns,
            )
        )
    scored.sort(key=lambda m: (-m.score, m.symbol))
    out: list[UniverseMember] = []
    for i, member in enumerate(scored[: clamp_top_limit(limit)], start=1):
        out.append(member.model_copy(update={"rank": i}))
    return out


def top_envelope(
    rows: list[dict[str, Any]],
    *,
    limit: int,
    now_ms: int | None = None,
) -> UniverseTop:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    return UniverseTop(
        as_of_ts_ms=now,
        limit=clamp_top_limit(limit),
        live_trading=False,
        score_inputs=list(SCORE_INPUTS),
        symbols=rank_rows(rows, limit=limit),
    )


def slice_active(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    """Re-slice a stored ``universe:active`` envelope to the requested limit."""
    wanted = clamp_top_limit(limit)
    symbols = list(payload.get("symbols") or [])
    sliced = symbols[:wanted]
    for i, row in enumerate(sliced, start=1):
        if isinstance(row, dict):
            row = {**row, "rank": i}
            sliced[i - 1] = row
    return {
        "as_of_ts_ms": payload.get("as_of_ts_ms") or int(time.time() * 1000),
        "limit": wanted,
        "live_trading": False,
        "score_inputs": list(payload.get("score_inputs") or SCORE_INPUTS),
        "symbols": sliced,
    }


async def write_universe_config(store, symbols: list[str], *, cadence_s: int = 900) -> dict[str, Any]:
    body = config_payload(symbols, cadence_s=cadence_s).model_dump(mode="json")
    await store.set(REDIS_UNIVERSE_CONFIG, body)
    return body


async def write_universe_active(store, envelope: UniverseTop | dict[str, Any]) -> dict[str, Any]:
    body = envelope.model_dump(mode="json") if isinstance(envelope, UniverseTop) else envelope
    body["live_trading"] = False
    await store.set(REDIS_UNIVERSE_ACTIVE, body)
    return body


async def read_universe_active(store) -> dict[str, Any] | None:
    raw = await store.get(REDIS_UNIVERSE_ACTIVE)
    return raw if isinstance(raw, dict) else None
