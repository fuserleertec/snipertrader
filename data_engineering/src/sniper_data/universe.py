"""Configurable paper universe — DE-owned authoritative contract.

PM / ML lock
------------
Redis ``universe:active`` is the authoritative full list::

    {"as_of_ts_ms": 1725459000000,
     "symbols": [{"symbol": "ES", "asset_class": "futures"}, ...]}

Written on pipeline/API startup and every 15m snapshot. HTTP:

* ``GET /v1/universe`` → that Redis payload (full active list)
* ``GET /v1/universe/top?limit=10|20`` → ranked subset (Redis ``universe:top``)

ML / FE should swap off provisional ``SETUP_UNIVERSE`` once these exist.

Env: ``DASHBOARD_SYMBOLS`` (alias ``UNIVERSE``, fallback ``DEMO_SYMBOLS``),
max 20. Default mix includes ES, CL, GC, NQ plus crypto and equities.
``live_trading`` is always ``false``.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field

from sniper_data.models import AssetClass
from sniper_data.symbols import infer_asset_class, normalize_symbol

log = logging.getLogger(__name__)

MAX_UNIVERSE_SYMBOLS = 20
DEFAULT_UNIVERSE_CSV = (
    "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,AAPL,MSFT,NVDA,SPY,ES,NQ,CL,GC"
)
REDIS_UNIVERSE_ACTIVE = "universe:active"
REDIS_UNIVERSE_TOP = "universe:top"
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
    """Frozen GET /v1/universe/top row — required fields only."""

    symbol: str
    asset_class: AssetClass
    rank: int
    score: float


class UniverseTop(BaseModel):
    """Frozen GET /v1/universe/top envelope. Required fields only."""

    as_of_ts_ms: int
    limit: int
    symbols: list[UniverseMember] = Field(default_factory=list)


class UniverseActiveItem(BaseModel):
    """One row of Redis ``universe:active`` / GET /v1/universe."""

    symbol: str
    asset_class: AssetClass


class UniverseActive(BaseModel):
    """Authoritative full list. Redis ``universe:active``."""

    as_of_ts_ms: int
    symbols: list[UniverseActiveItem] = Field(default_factory=list)
    live_trading: bool = False


class UniverseConfig(BaseModel):
    """Internal helper (Redis ``universe:config``). Not the ML contract."""

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
    """Query ``limit`` is frozen to 10 or 20."""
    value = int(limit)
    if value not in (10, 20):
        raise ValueError("limit must be 10 or 20")
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
        symbols=rank_rows(rows, limit=limit),
    )


def active_payload(
    symbols: list[str],
    *,
    now_ms: int | None = None,
) -> UniverseActive:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    items = [
        UniverseActiveItem(symbol=s, asset_class=infer_asset_class(s))
        for s in symbols
    ]
    return UniverseActive(as_of_ts_ms=now, symbols=items, live_trading=False)


def _frozen_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "asset_class": row["asset_class"],
        "rank": rank,
        "score": float(row.get("score") or 0.0),
    }


def slice_top(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    """Re-slice a stored ``universe:top`` envelope to the frozen wire shape."""
    wanted = clamp_top_limit(limit)
    symbols = list(payload.get("symbols") or [])
    sliced = []
    for i, row in enumerate(symbols[:wanted], start=1):
        if isinstance(row, dict):
            sliced.append(_frozen_row(row, i))
    return {
        "as_of_ts_ms": int(payload.get("as_of_ts_ms") or 0),
        "limit": wanted,
        "symbols": sliced,
    }


async def write_universe_config(store, symbols: list[str], *, cadence_s: int = 900) -> dict[str, Any]:
    body = config_payload(symbols, cadence_s=cadence_s).model_dump(mode="json")
    await store.set(REDIS_UNIVERSE_CONFIG, body)
    return body


async def write_universe_active(
    store,
    symbols: list[str] | UniverseActive,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Write Redis ``universe:active`` as ``{as_of_ts_ms, symbols:[{symbol,asset_class}]}``."""
    if isinstance(symbols, UniverseActive):
        body = symbols.model_dump(mode="json")
    else:
        body = active_payload(list(symbols), now_ms=now_ms).model_dump(mode="json")
    body["live_trading"] = False
    await store.set(REDIS_UNIVERSE_ACTIVE, body)
    return body


async def write_universe_top(store, envelope: UniverseTop | dict[str, Any]) -> dict[str, Any]:
    if isinstance(envelope, UniverseTop):
        body = envelope.model_dump(mode="json")
    else:
        body = slice_top(envelope, clamp_top_limit(int(envelope.get("limit") or 20)))
        body["as_of_ts_ms"] = int(envelope.get("as_of_ts_ms") or body["as_of_ts_ms"])
    await store.set(REDIS_UNIVERSE_TOP, body)
    return body


async def read_universe_active(store) -> dict[str, Any] | None:
    raw = await store.get(REDIS_UNIVERSE_ACTIVE)
    return raw if isinstance(raw, dict) else None


async def read_universe_top(store) -> dict[str, Any] | None:
    raw = await store.get(REDIS_UNIVERSE_TOP)
    return raw if isinstance(raw, dict) else None


# ── ML / detector consumer (swap off SETUP_UNIVERSE) ─────────────────────────
# Primary: GET /v1/universe/top matching universe_top.schema.json.
# Helpers: Redis universe:top, Redis universe:active, GET /v1/universe.
# Env SETUP_UNIVERSE is offline-only when those DE surfaces are unreachable.

REQUIRED_FUTURES = ("ES", "CL", "GC", "NQ")
UNIVERSE_HTTP_PATH = "/v1/universe"
UNIVERSE_TOP_HTTP_PATH = "/v1/universe/top"
# Backward-compatible alias used by older ML tests / docs.
UNIVERSE_ACTIVE_KEY = REDIS_UNIVERSE_ACTIVE


def coerce_member_symbol(item: Any) -> str | None:
    """Accept frozen ``{symbol, asset_class, rank, score}`` or a plain string."""
    if isinstance(item, str):
        token = item
    elif isinstance(item, dict):
        token = item.get("symbol")
    else:
        token = None
    if not token:
        return None
    try:
        return normalize_symbol(str(token))
    except ValueError:
        return None


def symbols_from_payload(raw: Any) -> tuple[list[str], int | None, list[dict[str, Any]]]:
    """Parse DE wire payloads. ``symbols`` may be objects or strings."""
    if raw is None:
        return [], None, []
    as_of: int | None = None
    rows: list[Any]
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = list(raw.get("symbols") or raw.get("universe") or raw.get("tickers") or [])
        if raw.get("as_of_ts_ms") is not None:
            as_of = int(raw["as_of_ts_ms"])
    else:
        return [], None, []
    names: list[str] = []
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows:
        sym = coerce_member_symbol(item)
        if not sym or sym in seen:
            continue
        seen.add(sym)
        names.append(sym)
        if isinstance(item, dict):
            members.append(dict(item))
        else:
            members.append({"symbol": sym, "asset_class": infer_asset_class(sym).value})
        if len(names) >= MAX_UNIVERSE_SYMBOLS:
            break
    return names, as_of, members


def parse_symbol_csv(raw: str | None) -> list[str]:
    return parse_universe(raw or "")


@dataclass(frozen=True)
class UniverseSnapshot:
    """Detector-facing snapshot. Wire GET /v1/universe/top stays DE-owned."""

    symbols: tuple[str, ...]
    as_of_ts_ms: int
    source: str
    backend: str
    live_trading: bool = False
    ranked: bool = False
    limit: int | None = None
    members: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "as_of_ts_ms": self.as_of_ts_ms,
            "source": self.source,
            "backend": self.backend,
            "live_trading": False,
            "ranked": self.ranked,
            "limit": self.limit,
            "count": len(self.symbols),
            "members": list(self.members),
        }


class UniverseProvider(Protocol):
    backend: str

    async def snapshot(self, *, limit: int | None = None, ranked: bool = False) -> UniverseSnapshot: ...

    async def symbols(self, *, limit: int | None = None) -> list[str]: ...


def _now_ms() -> int:
    return int(time.time() * 1000)


def _cap_limit(limit: int | None, *, ranked: bool) -> int:
    if ranked:
        if limit is None:
            return 20
        return 10 if int(limit) <= 10 else 20
    if limit is None:
        return MAX_UNIVERSE_SYMBOLS
    return max(1, min(int(limit), MAX_UNIVERSE_SYMBOLS))


def env_fallback_symbols(settings: Any | None = None) -> tuple[list[str], str]:
    """Offline fallback only. ``SETUP_UNIVERSE`` wins when set; else DE env chain."""
    from sniper_data.config import Settings, get_settings

    s = settings or get_settings()
    setup_u = (getattr(s, "setup_universe", None) or os.environ.get("SETUP_UNIVERSE") or "").strip()
    if setup_u:
        parsed = parse_universe(setup_u)
        if parsed:
            return parsed, "SETUP_UNIVERSE"
    if isinstance(s, Settings):
        return list(s.symbols), "settings"
    return parse_universe(""), "default"


class EnvUniverseProvider:
    """Offline fallback when DE HTTP / Redis are unreachable."""

    backend = "env"

    def __init__(self, settings=None, *, override: list[str] | None = None) -> None:
        self.settings = settings
        self.override = override

    async def snapshot(self, *, limit: int | None = None, ranked: bool = False) -> UniverseSnapshot:
        if self.override is not None:
            names = parse_universe(",".join(self.override))
            source = "override"
        else:
            names, source = env_fallback_symbols(self.settings)
        cap = _cap_limit(limit, ranked=ranked)
        names = names[:cap]
        return UniverseSnapshot(
            symbols=tuple(names),
            as_of_ts_ms=_now_ms(),
            source=source,
            backend=self.backend,
            live_trading=False,
            ranked=ranked,
            limit=cap if ranked else None,
            members=tuple(
                {"symbol": s, "asset_class": infer_asset_class(s).value} for s in names
            ),
        )

    async def symbols(self, *, limit: int | None = None) -> list[str]:
        return list((await self.snapshot(limit=limit)).symbols)


class RedisUniverseProvider:
    """Helpers: Redis ``universe:top`` (ranked) and ``universe:active`` (full list)."""

    backend = "redis"

    def __init__(self, store, fallback: UniverseProvider) -> None:
        self.store = store
        self.fallback = fallback

    async def snapshot(self, *, limit: int | None = None, ranked: bool = False) -> UniverseSnapshot:
        cap = _cap_limit(limit, ranked=ranked)
        try:
            if ranked:
                raw = await read_universe_top(self.store)
                if raw and raw.get("symbols"):
                    names, as_of, members = symbols_from_payload(raw)
                    names = names[:cap]
                    members = members[:cap]
                    if names:
                        return UniverseSnapshot(
                            symbols=tuple(names),
                            as_of_ts_ms=as_of or _now_ms(),
                            source=REDIS_UNIVERSE_TOP,
                            backend=self.backend,
                            live_trading=False,
                            ranked=True,
                            limit=cap,
                            members=tuple(members),
                        )
            raw = await read_universe_active(self.store)
        except Exception as exc:  # noqa: BLE001
            log.info("universe redis miss: %s", exc)
            raw = None
        names, as_of, members = symbols_from_payload(raw)
        names = names[:cap]
        members = members[:cap]
        if names:
            return UniverseSnapshot(
                symbols=tuple(names),
                as_of_ts_ms=as_of or _now_ms(),
                source=REDIS_UNIVERSE_ACTIVE,
                backend=self.backend,
                live_trading=False,
                ranked=ranked,
                limit=cap if ranked else None,
                members=tuple(members),
            )
        log.info("universe redis empty; falling back to %s", getattr(self.fallback, "backend", "env"))
        return await self.fallback.snapshot(limit=limit, ranked=ranked)

    async def symbols(self, *, limit: int | None = None) -> list[str]:
        return list((await self.snapshot(limit=limit, ranked=True)).symbols)


class HttpUniverseProvider:
    """Primary: ``GET /v1/universe/top?limit=10|20``. Helper: ``GET /v1/universe``."""

    backend = "http"

    def __init__(
        self,
        base_url: str,
        fallback: UniverseProvider,
        *,
        timeout_s: float = 3.0,
        transport=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback = fallback
        self.timeout_s = timeout_s
        self._transport = transport

    def _url(self, *, ranked: bool, limit: int | None) -> str:
        if ranked:
            cap = _cap_limit(limit, ranked=True)
            return f"{self.base_url}{UNIVERSE_TOP_HTTP_PATH}?limit={cap}"
        return f"{self.base_url}{UNIVERSE_HTTP_PATH}"

    async def snapshot(self, *, limit: int | None = None, ranked: bool = False) -> UniverseSnapshot:
        if not self.base_url:
            return await self.fallback.snapshot(limit=limit, ranked=ranked)
        try:
            import httpx

            kwargs: dict[str, Any] = {"timeout": self.timeout_s}
            if self._transport is not None:
                kwargs["transport"] = self._transport
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(self._url(ranked=ranked, limit=limit))
                resp.raise_for_status()
                body = resp.json()
        except Exception as exc:  # noqa: BLE001 — DE unreachable → fallback
            log.info("universe http miss (%s): %s", self.base_url, exc)
            return await self.fallback.snapshot(limit=limit, ranked=ranked)
        names, as_of, members = symbols_from_payload(body)
        cap = _cap_limit(limit, ranked=ranked)
        names = names[:cap]
        members = members[:cap]
        if not names:
            return await self.fallback.snapshot(limit=limit, ranked=ranked)
        return UniverseSnapshot(
            symbols=tuple(names),
            as_of_ts_ms=as_of or _now_ms(),
            source=self._url(ranked=ranked, limit=limit),
            backend=self.backend,
            live_trading=False,
            ranked=ranked,
            limit=cap if ranked else None,
            members=tuple(members),
        )

    async def symbols(self, *, limit: int | None = None) -> list[str]:
        return list((await self.snapshot(limit=limit, ranked=True)).symbols)


class FallbackUniverseProvider:
    """Detectors: HTTP /top → Redis ``universe:top`` → helpers → env."""

    backend = "auto"

    def __init__(
        self,
        *,
        env: UniverseProvider,
        redis: UniverseProvider | None = None,
        http: UniverseProvider | None = None,
    ) -> None:
        self.env = env
        self.redis = redis
        self.http = http

    async def snapshot(self, *, limit: int | None = None, ranked: bool = False) -> UniverseSnapshot:
        if ranked:
            if self.http is not None:
                snap = await self.http.snapshot(limit=limit, ranked=True)
                if snap.backend == "http" and snap.symbols:
                    return snap
            if self.redis is not None:
                snap = await self.redis.snapshot(limit=limit, ranked=True)
                if snap.backend == "redis" and snap.symbols:
                    return snap
            return await self.env.snapshot(limit=limit, ranked=True)
        if self.redis is not None:
            snap = await self.redis.snapshot(limit=limit, ranked=False)
            if snap.backend == "redis" and snap.symbols:
                return snap
        if self.http is not None:
            snap = await self.http.snapshot(limit=limit, ranked=False)
            if snap.backend == "http" and snap.symbols:
                return snap
        return await self.env.snapshot(limit=limit, ranked=False)

    async def symbols(self, *, limit: int | None = None) -> list[str]:
        return list((await self.snapshot(limit=limit, ranked=True)).symbols)


def build_universe_provider(
    settings=None,
    *,
    store=None,
    override: list[str] | None = None,
) -> UniverseProvider:
    """Factory. ``UNIVERSE_BACKEND`` = ``auto`` | ``env`` | ``redis`` | ``http``."""
    from sniper_data.config import get_settings

    s = settings or get_settings()
    env = EnvUniverseProvider(s, override=override)
    if override is not None:
        return env
    backend = (getattr(s, "universe_backend", None) or os.environ.get("UNIVERSE_BACKEND") or "auto").strip().lower()
    http_url = (getattr(s, "universe_http_url", None) or os.environ.get("UNIVERSE_HTTP_URL") or "").strip()
    redis_p = RedisUniverseProvider(store, env) if store is not None else None
    http_p = HttpUniverseProvider(http_url, env) if http_url else None
    if backend == "env":
        return env
    if backend == "redis":
        return redis_p or env
    if backend == "http":
        return http_p or env
    return FallbackUniverseProvider(env=env, redis=redis_p, http=http_p)


async def resolve_scan_universe(
    provider: UniverseProvider,
    *,
    limit: int = 20,
) -> UniverseSnapshot:
    """Authoritative detector list: ``GET /v1/universe/top?limit=10|20``."""
    cap = 10 if int(limit) <= 10 else 20
    return await provider.snapshot(limit=cap, ranked=True)
