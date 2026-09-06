"""Paper ranking universe — cut over to DE ``GET /v1/universe/top``.

Primary (wired): ``GET {DE_API_BASE}/v1/universe/top?limit=10|20`` (15m cache).

* ``limit=10`` → P0 ensemble ranking book (``GET /picks/ensemble``)
* ``limit=20`` → categorized picks + history consumers

Schema is locked to DE PR #12 / ``schemas/universe_top.schema.json``:
``{as_of_ts_ms, limit, symbols:[{symbol, asset_class, rank, score}]}``.
Extra properties and missing required fields are rejected (DE treated as
unreachable → fallback).

``SETUP_UNIVERSE`` is **not** applied to the ranking book. It remains the
detector allow-list only.

Fallback **only if DE is unreachable** (empty ``DE_API_BASE``, HTTP error,
or invalid body), in order: ``DE_UNIVERSE`` file → ``DEMO_SYMBOLS`` →
``config/paper_universe.json`` (includes ES, CL, GC, NQ).

``live_trading`` is always false.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sniper_quant.config import Settings, get_settings
from sniper_quant.models import AssetClass, UniverseTop, normalize_symbol

log = logging.getLogger(__name__)

UNIVERSE_TOP_PATH = "/v1/universe/top"
UNIVERSE_TOP_LIMITS = frozenset({10, 20})
UNIVERSE_TOP_REFRESH_SEC = 900
UNIVERSE_TOP_NEG_CACHE_SEC = 15.0
REQUIRED_FUTURES = frozenset({"ES", "CL", "GC", "NQ"})

Fetcher = Callable[[Settings, int], list[tuple[str, AssetClass]] | None]

_DE_TOP_CACHE: dict[tuple[str, int], tuple[float, UniverseTop]] = {}
_DE_TOP_NEG: dict[tuple[str, int], float] = {}

DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "config" / "paper_universe.json"

# Asset-class inference for CSV tokens that are not already in the universe
# file (DE extras, SETUP_UNIVERSE). Not a ranking allow-list.
_FUTURES_ROOTS = frozenset({"ES", "NQ", "CL", "GC", "YM", "RTY", "6E", "6J", "6B"})


def default_universe_path() -> Path:
    return DEFAULT_UNIVERSE_PATH


def _pairs_from_rows(rows: list) -> list[tuple[str, AssetClass]]:
    out: list[tuple[str, AssetClass]] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, str):
            symbol = normalize_symbol(row)
            asset = _infer_asset(symbol)
        else:
            symbol = normalize_symbol(row["symbol"])
            asset = AssetClass(str(row.get("asset_class") or _infer_asset(symbol).value))
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append((symbol, asset))
    return out


def _infer_asset(symbol: str) -> AssetClass:
    if symbol.endswith(("USDT", "USDC", "BUSD")):
        return AssetClass.CRYPTO
    if symbol in _FUTURES_ROOTS:
        return AssetClass.FUTURES
    return AssetClass.EQUITY


def _load_json_file(path: Path) -> list[tuple[str, AssetClass]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("symbols") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(f"universe file must list symbols: {path}")
    return _pairs_from_rows(rows)


def load_universe_file(path: Path | None = None) -> list[tuple[str, AssetClass]]:
    """Load a universe JSON file. No hardcoded symbol fallback."""
    target = path or DEFAULT_UNIVERSE_PATH
    if not target.is_file():
        raise FileNotFoundError(
            f"paper universe file not found: {target} "
            "(no hardcoded fallback — restore config/paper_universe.json "
            "or set PAPER_UNIVERSE / DEMO_SYMBOLS / DE_UNIVERSE)"
        )
    return _load_json_file(target)


def _parse_csv(raw: str) -> list[tuple[str, AssetClass]]:
    rows: list = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if ":" in token:
            sym, ac = token.split(":", 1)
            rows.append({"symbol": sym, "asset_class": ac.strip().lower()})
        else:
            rows.append(token)
    return _pairs_from_rows(rows)


def _load_override(raw: str) -> list[tuple[str, AssetClass]]:
    path = Path(raw).expanduser()
    if path.is_file():
        return _load_json_file(path)
    return _parse_csv(raw)


def load_paper_universe(settings: Settings | None = None) -> list[tuple[str, AssetClass]]:
    """Quant paper book mix (``PAPER_UNIVERSE`` or the config file)."""
    settings = settings or get_settings()
    raw = (settings.paper_universe or "").strip()
    if raw:
        return _load_override(raw)
    return load_universe_file()


def parse_setup_universe(settings: Settings | None = None) -> set[str] | None:
    """Detector ``SETUP_UNIVERSE`` allow-list. Not applied to ranking."""
    settings = settings or get_settings()
    raw = (settings.setup_universe or "").strip()
    if not raw:
        return None
    return {sym for sym, _ in _load_override(raw)}


def setup_universe_allowlist(settings: Settings | None = None) -> set[str] | None:
    return parse_setup_universe(settings)


def load_demo_symbols(settings: Settings | None = None) -> list[tuple[str, AssetClass]]:
    """Fallback ranking book when DE is unreachable and ``DEMO_SYMBOLS`` is set."""
    settings = settings or get_settings()
    raw = (settings.demo_symbols or "").strip()
    if raw:
        return _load_override(raw)
    return load_universe_file()


def load_de_universe_feed(settings: Settings | None = None) -> list[tuple[str, AssetClass]] | None:
    """Offline DE dump. ``None`` until ``DE_UNIVERSE`` is set."""
    settings = settings or get_settings()
    raw = (settings.de_universe or "").strip()
    if not raw:
        return None
    return _load_override(raw)


def clear_de_top_cache() -> None:
    _DE_TOP_CACHE.clear()
    _DE_TOP_NEG.clear()


def parse_universe_top_model(payload: dict[str, Any], *, limit: int) -> UniverseTop:
    """Validate DE ``GET /v1/universe/top`` against the locked schema."""
    if limit not in UNIVERSE_TOP_LIMITS:
        raise ValueError("universe/top limit must be 10 or 20")
    if not isinstance(payload, dict):
        raise ValueError("universe/top must be an object")
    envelope = UniverseTop.model_validate(payload)
    if envelope.limit != limit:
        raise ValueError(f"universe/top.limit {envelope.limit} != requested {limit}")
    return envelope


def parse_universe_top(
    payload: dict[str, Any],
    *,
    limit: int,
) -> list[tuple[str, AssetClass]]:
    """Parse locked DE ``GET /v1/universe/top`` body into ``(symbol, asset_class)``."""
    envelope = parse_universe_top_model(payload, limit=limit)
    return [(row.symbol, row.asset_class) for row in envelope.symbols]


def cached_de_top(settings: Settings | None, limit: int) -> UniverseTop | None:
    settings = settings or get_settings()
    base = (settings.de_api_base or "").strip().rstrip("/")
    if not base:
        return None
    hit = _DE_TOP_CACHE.get((base, int(limit)))
    if not hit:
        return None
    return hit[1]


def fetch_de_universe_top(
    settings: Settings | None = None,
    limit: int = 20,
    *,
    timeout: float = 1.5,
) -> list[tuple[str, AssetClass]] | None:
    """GET DE ``/v1/universe/top?limit=``. ``None`` if unset or unreachable."""
    if limit not in UNIVERSE_TOP_LIMITS:
        raise ValueError("universe/top limit must be 10 or 20")
    settings = settings or get_settings()
    base = (settings.de_api_base or "").strip().rstrip("/")
    if not base:
        return None
    cache_key = (base, int(limit))
    now = time.time()
    hit = _DE_TOP_CACHE.get(cache_key)
    if hit and now - hit[0] < UNIVERSE_TOP_REFRESH_SEC:
        return [(row.symbol, row.asset_class) for row in hit[1].symbols]
    neg = _DE_TOP_NEG.get(cache_key)
    if neg and now - neg < UNIVERSE_TOP_NEG_CACHE_SEC:
        return None
    url = f"{base}{UNIVERSE_TOP_PATH}"
    try:
        import httpx

        resp = httpx.get(url, params={"limit": int(limit)}, timeout=timeout)
        resp.raise_for_status()
        envelope = parse_universe_top_model(resp.json(), limit=limit)
    except (ValidationError, ValueError, TypeError) as exc:
        log.info("DE %s rejected locked schema (%s); using fallback universe", url, exc)
        _DE_TOP_NEG[cache_key] = now
        return None
    except Exception as exc:  # noqa: BLE001
        log.info("DE %s unreachable (%s); using fallback universe", url, exc)
        _DE_TOP_NEG[cache_key] = now
        return None
    _DE_TOP_CACHE[cache_key] = (now, envelope)
    _DE_TOP_NEG.pop(cache_key, None)
    return [(row.symbol, row.asset_class) for row in envelope.symbols]


def _fallback_universe(settings: Settings) -> list[tuple[str, AssetClass]]:
    """Used only when DE ``/v1/universe/top`` is unreachable. No SETUP_UNIVERSE ∩."""
    de_file = load_de_universe_feed(settings)
    if de_file is not None:
        return de_file
    if (settings.demo_symbols or "").strip():
        return load_demo_symbols(settings)
    return load_paper_universe(settings)


def resolve_ranking_universe(
    settings: Settings | None = None,
    *,
    limit: int = 20,
    fetcher: Fetcher | None = None,
) -> list[tuple[str, AssetClass]]:
    """Ranking book for picks / history.

    ``limit=10`` = P0 ensemble. ``limit=20`` = categorized + history.
    Live DE ``GET /v1/universe/top`` is used as-is (no ``SETUP_UNIVERSE``
    intersection). Fallback only if DE is unreachable.
    """
    if limit not in UNIVERSE_TOP_LIMITS:
        raise ValueError("ranking universe limit must be 10 or 20")
    settings = settings or get_settings()
    fetch = fetcher if fetcher is not None else fetch_de_universe_top
    top = fetch(settings, limit)
    if top:
        return list(top)
    return _fallback_universe(settings)


def ranking_source(
    settings: Settings | None = None,
    *,
    limit: int = 20,
    fetcher: Fetcher | None = None,
) -> str:
    settings = settings or get_settings()
    fetch = fetcher if fetcher is not None else fetch_de_universe_top
    if fetch(settings, limit):
        return "de_top"
    if (settings.de_universe or "").strip():
        return "de_feed"
    if (settings.demo_symbols or "").strip():
        return "demo_symbols"
    return "paper_universe"


def universe_dump(
    settings: Settings | None = None,
    *,
    fetcher: Fetcher | None = None,
) -> dict:
    settings = settings or get_settings()
    paper = load_paper_universe(settings)
    demo = load_demo_symbols(settings)
    de = load_de_universe_feed(settings)
    ml = parse_setup_universe(settings)
    ensemble = resolve_ranking_universe(settings, limit=10, fetcher=fetcher)
    history = resolve_ranking_universe(settings, limit=20, fetcher=fetcher)
    source = ranking_source(settings, limit=20, fetcher=fetcher)
    base = (settings.de_api_base or "").strip().rstrip("/")
    handoff = "de_top" if source == "de_top" else "fallback"
    last_10 = cached_de_top(settings, 10)
    last_20 = cached_de_top(settings, 20)
    return {
        "live_trading": False,
        "refresh_sec": UNIVERSE_TOP_REFRESH_SEC,
        "handoff": handoff,
        "cutover": "de_universe_top",
        "ranking_source": source,
        "de_api_base": base or None,
        "de_universe_top": f"{base}{UNIVERSE_TOP_PATH}" if base else None,
        "de_top_10": last_10.model_dump(mode="json") if last_10 else None,
        "de_top_20": last_20.model_dump(mode="json") if last_20 else None,
        "de_universe": [{"symbol": s, "asset_class": a.value} for s, a in de] if de else None,
        "demo_symbols": [{"symbol": s, "asset_class": a.value} for s, a in demo],
        "setup_universe": sorted(ml) if ml is not None else None,
        "paper_universe": [{"symbol": s, "asset_class": a.value} for s, a in paper],
        "ensemble_universe": [{"symbol": s, "asset_class": a.value} for s, a in ensemble],
        "history_universe": [{"symbol": s, "asset_class": a.value} for s, a in history],
        "ranking_universe": [{"symbol": s, "asset_class": a.value} for s, a in ensemble],
        "paper_source": (settings.paper_universe or str(DEFAULT_UNIVERSE_PATH)),
        "intersection": False,
        "n_paper": len(paper),
        "n_ensemble": len(ensemble),
        "n_history": len(history),
        "n_ranking": len(ensemble),
        "required_futures": sorted(REQUIRED_FUTURES),
        "bar_feed": {
            "timeframes": ["1m", "5m"],
            "kafka": "ohlcv_bars",
            "http": "/v1/ohlcv/{symbol}?timeframe=1m|5m",
            "ws": "/v1/ws/ohlcv?timeframe=1m|5m",
            "not": ["/v1/universe/top", "/v1/dashboard/snapshot"],
            "universe_top_role": "15m_ranking_book_only",
            "live_trading": False,
        },
        "note": (
            "CUT OVER: GET {base}/v1/universe/top?limit=10 is the P0 ensemble "
            "book; limit=20 is categorized + history. Schema locked "
            "(as_of_ts_ms, limit, symbols[].{{symbol,asset_class,rank,score}}). "
            "SETUP_UNIVERSE / DEMO_SYMBOLS / DE_UNIVERSE / paper file are "
            "fallback only when DE is unreachable. SETUP_UNIVERSE does not "
            "narrow the ranking book (detector allow-list only). "
            "Bar consumption (backtest / lifecycle / paper marks) is "
            "continuous DE 1m/5m via Kafka ohlcv_bars, WS /v1/ws/ohlcv, or "
            "GET /v1/ohlcv/{{symbol}} — not 15m universe/top or dashboard "
            "snapshots. live_trading is always false. refresh_sec=900."
        ).format(base=base or "$DE_API_BASE"),
    }
