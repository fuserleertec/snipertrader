"""Paper ranking universe (no live trading, no hardcoded symbol lists).

``GET /picks/ensemble`` and ``GET /picks/categorized`` rank **only**
inside ``resolve_ranking_universe``:

1. ``DE_UNIVERSE`` when DE has published the feed.
2. Else ``DEMO_SYMBOLS`` when that override is set (CSV or JSON path).
3. Else the file-backed paper mix at ``config/paper_universe.json``
   (includes ES, NQ, CL, GC). Missing file raises — no Python fallback.
4. Intersect with ``SETUP_UNIVERSE`` when ML set one (narrow only).

Symbols outside that set are never ranked. ``PAPER_UNIVERSE`` overrides
the paper **book** mix only; it does not expand ranking.
"""

from __future__ import annotations

import json
from pathlib import Path

from sniper_quant.config import Settings, get_settings
from sniper_quant.models import AssetClass, normalize_symbol

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
    """Published DE universe. ``None`` until ``DE_UNIVERSE`` is set."""
    settings = settings or get_settings()
    raw = (settings.de_universe or "").strip()
    if not raw:
        return None
    return _load_override(raw)


def resolve_ranking_universe(
    settings: Settings | None = None,
) -> list[tuple[str, AssetClass]]:
    """Allow-list for ``GET /picks/ensemble`` / ``/picks/categorized``.

    1. ``DE_UNIVERSE`` when DE has published the feed.
    2. Else ``DEMO_SYMBOLS`` when set.
    3. Else ``config/paper_universe.json`` (includes ES, NQ, CL, GC).
    4. Intersect with ``SETUP_UNIVERSE`` when ML set one.

    Never includes symbols outside that set. Paper only.
    """
    settings = settings or get_settings()
    de = load_de_universe_feed(settings)
    allowed = de if de is not None else load_demo_symbols(settings)
    setup = parse_setup_universe(settings)
    if setup is not None:
        allowed = [(sym, ac) for sym, ac in allowed if sym in setup]
    return allowed


def ranking_source(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if (settings.de_universe or "").strip():
        return "de_feed"
    if (settings.demo_symbols or "").strip():
        return "demo_symbols"
    return "paper_universe"


def universe_dump(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    paper = load_paper_universe(settings)
    demo = load_demo_symbols(settings)
    de = load_de_universe_feed(settings)
    ml = parse_setup_universe(settings)
    ranking = resolve_ranking_universe(settings)
    source = ranking_source(settings)
    return {
        "live_trading": False,
        "refresh_sec": 900,
        "handoff": "de_feed" if source == "de_feed" else "provisional",
        "ranking_source": source,
        "de_universe": [{"symbol": s, "asset_class": a.value} for s, a in de] if de else None,
        "demo_symbols": [{"symbol": s, "asset_class": a.value} for s, a in demo],
        "setup_universe": sorted(ml) if ml is not None else None,
        "paper_universe": [{"symbol": s, "asset_class": a.value} for s, a in paper],
        "ranking_universe": [{"symbol": s, "asset_class": a.value} for s, a in ranking],
        "paper_source": (settings.paper_universe or str(DEFAULT_UNIVERSE_PATH)),
        "intersection": ml is not None,
        "n_paper": len(paper),
        "n_ranking": len(ranking),
        "note": (
            "GET /picks/ensemble ranks only ranking_universe. "
            "Default: config/paper_universe.json (includes ES, NQ, CL, GC). "
            "Overrides: DEMO_SYMBOLS, then DE_UNIVERSE when DE publishes. "
            "SETUP_UNIVERSE can only narrow. live_trading is always false."
        ),
    }
