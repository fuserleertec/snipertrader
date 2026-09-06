"""Paper ranking universe (no live trading, no hardcoded symbol lists).

Handoff (PM): DE ``GET /v1/universe/top?limit=10|20`` (15m refresh).

* ``limit=10`` → P0 ensemble ranking book
* ``limit=20`` → categorized picks + history consumers

Until DE is up (``DE_API_BASE`` empty or the call fails), Quant keeps the
provisional ``DEMO_SYMBOLS`` / paper-file mix ∩ ``SETUP_UNIVERSE``.
That set includes ES, CL, GC, NQ. ``SETUP_UNIVERSE`` can only narrow.

``PAPER_UNIVERSE`` overrides the paper book mix only.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sniper_quant.config import Settings, get_settings
from sniper_quant.models import AssetClass, normalize_symbol

log = logging.getLogger(__name__)

UNIVERSE_TOP_PATH = "/v1/universe/top"
UNIVERSE_TOP_LIMITS = frozenset({10, 20})
UNIVERSE_TOP_REFRESH_SEC = 900
REQUIRED_FUTURES = frozenset({"ES", "CL", "GC", "NQ"})

Fetcher = Callable[[Settings, int], list[tuple[str, AssetClass]] | None]

_DE_TOP_CACHE: dict[tuple[str, int], tuple[float, list[tuple[str, AssetClass]]]] = {}

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
    """ML ``SETUP_UNIVERSE`` allow-list (CSV or JSON path). ``None`` = unset."""
    settings = settings or get_settings()
    raw = (settings.setup_universe or "").strip()
    if not raw:
        return None
    return {sym for sym, _ in _load_override(raw)}


def setup_universe_allowlist(settings: Settings | None = None) -> set[str] | None:
    return parse_setup_universe(settings)


def load_demo_symbols(settings: Settings | None = None) -> list[tuple[str, AssetClass]]:
    """Ranking allow-list before DE handoff.

    ``DEMO_SYMBOLS`` when set; otherwise the file-backed paper universe.
    """
    settings = settings or get_settings()
    raw = (settings.demo_symbols or "").strip()
    if raw:
        return _load_override(raw)
    return load_universe_file()


def load_de_universe_feed(settings: Settings | None = None) -> list[tuple[str, AssetClass]] | None:
    """Offline DE universe file/CSV. ``None`` until ``DE_UNIVERSE`` is set."""
    settings = settings or get_settings()
    raw = (settings.de_universe or "").strip()
    if not raw:
        return None
    return _load_override(raw)


def clear_de_top_cache() -> None:
    _DE_TOP_CACHE.clear()


def parse_universe_top(
    payload: dict[str, Any],
    *,
    limit: int,
) -> list[tuple[str, AssetClass]]:
    """Parse DE ``GET /v1/universe/top`` body. Required: as_of_ts_ms, limit, symbols."""
    if not isinstance(payload, dict):
        raise ValueError("universe/top must be an object")
    rows = payload.get("symbols")
    if not isinstance(rows, list):
        raise ValueError("universe/top.symbols must be a list")
    want = min(int(payload.get("limit") or limit), int(limit))
    pairs = _pairs_from_rows(rows)
    return pairs[: max(0, want)]


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
        return list(hit[1])
    url = f"{base}{UNIVERSE_TOP_PATH}"
    try:
        import httpx

        resp = httpx.get(url, params={"limit": int(limit)}, timeout=timeout)
        resp.raise_for_status()
        pairs = parse_universe_top(resp.json(), limit=limit)
    except Exception as exc:  # noqa: BLE001
        log.info("DE %s failed (%s); using provisional universe", url, exc)
        return None
    _DE_TOP_CACHE[cache_key] = (now, list(pairs))
    return pairs


def _provisional_universe(settings: Settings) -> list[tuple[str, AssetClass]]:
    de_file = load_de_universe_feed(settings)
    if de_file is not None:
        return de_file
    return load_demo_symbols(settings)


def _narrow(allowed: list[tuple[str, AssetClass]], settings: Settings) -> list[tuple[str, AssetClass]]:
    setup = parse_setup_universe(settings)
    if setup is None:
        return allowed
    return [(sym, ac) for sym, ac in allowed if sym in setup]


def resolve_ranking_universe(
    settings: Settings | None = None,
    *,
    limit: int = 20,
    fetcher: Fetcher | None = None,
) -> list[tuple[str, AssetClass]]:
    """Allow-list for picks / history.

    ``limit=10`` = P0 ensemble book. ``limit=20`` = categorized + history.
    DE ``GET /v1/universe/top`` when ``DE_API_BASE`` works; otherwise the
    provisional mix (includes ES, CL, GC, NQ) ∩ ``SETUP_UNIVERSE``.
    Provisional is **not** sliced to ``limit`` so futures stay in the set.
    """
    if limit not in UNIVERSE_TOP_LIMITS:
        raise ValueError("ranking universe limit must be 10 or 20")
    settings = settings or get_settings()
    fetch = fetcher if fetcher is not None else fetch_de_universe_top
    top = fetch(settings, limit)
    if top:
        return _narrow(top, settings)
    return _narrow(_provisional_universe(settings), settings)


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
    handoff = "de_top" if source == "de_top" else ("de_feed" if source == "de_feed" else "provisional")
    return {
        "live_trading": False,
        "refresh_sec": UNIVERSE_TOP_REFRESH_SEC,
        "handoff": handoff,
        "ranking_source": source,
        "de_api_base": base or None,
        "de_universe_top": f"{base}{UNIVERSE_TOP_PATH}" if base else None,
        "de_universe": [{"symbol": s, "asset_class": a.value} for s, a in de] if de else None,
        "demo_symbols": [{"symbol": s, "asset_class": a.value} for s, a in demo],
        "setup_universe": sorted(ml) if ml is not None else None,
        "paper_universe": [{"symbol": s, "asset_class": a.value} for s, a in paper],
        "ensemble_universe": [{"symbol": s, "asset_class": a.value} for s, a in ensemble],
        "history_universe": [{"symbol": s, "asset_class": a.value} for s, a in history],
        "ranking_universe": [{"symbol": s, "asset_class": a.value} for s, a in ensemble],
        "paper_source": (settings.paper_universe or str(DEFAULT_UNIVERSE_PATH)),
        "intersection": ml is not None,
        "n_paper": len(paper),
        "n_ensemble": len(ensemble),
        "n_history": len(history),
        "n_ranking": len(ensemble),
        "required_futures": sorted(REQUIRED_FUTURES),
        "note": (
            "Handoff: GET {base}/v1/universe/top?limit=10 (P0 ensemble) and "
            "limit=20 (categorized + history). Until DE is up, provisional "
            "DEMO_SYMBOLS / paper file ∩ SETUP_UNIVERSE (includes ES, CL, GC, NQ). "
            "SETUP_UNIVERSE can only narrow. live_trading is always false."
        ).format(base=base or "$DE_API_BASE"),
    }
