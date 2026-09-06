"""Paper + ML symbol universes (no live trading).

Quant owns a default ~20-symbol paper mix (crypto / equity / futures) at
``quant/config/paper_universe.json``. ``PAPER_UNIVERSE`` overrides that
file (path or CSV). ``SETUP_UNIVERSE`` is the ML detector allow-list.
When both are present, ``GET /picks/ensemble`` / ``/picks/categorized``
rank the **intersection**.
"""

from __future__ import annotations

import json
from pathlib import Path

from sniper_quant.config import Settings, get_settings
from sniper_quant.models import AssetClass, normalize_symbol

DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parents[2] / "config" / "paper_universe.json"

# Builtin fallback if the JSON file is not on disk (editable install / tests).
_BUILTIN: tuple[tuple[str, str], ...] = (
    ("BTCUSDT", "crypto"),
    ("ETHUSDT", "crypto"),
    ("SOLUSDT", "crypto"),
    ("BNBUSDT", "crypto"),
    ("XRPUSDT", "crypto"),
    ("ADAUSDT", "crypto"),
    ("AVAXUSDT", "crypto"),
    ("LINKUSDT", "crypto"),
    ("AAPL", "equity"),
    ("MSFT", "equity"),
    ("NVDA", "equity"),
    ("AMZN", "equity"),
    ("META", "equity"),
    ("GOOGL", "equity"),
    ("TSLA", "equity"),
    ("SPY", "equity"),
    ("ES", "futures"),
    ("NQ", "futures"),
    ("CL", "futures"),
    ("GC", "futures"),
)


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
    if symbol in {"ES", "NQ", "CL", "GC", "YM", "RTY"}:
        return AssetClass.FUTURES
    return AssetClass.EQUITY


def _load_json_file(path: Path) -> list[tuple[str, AssetClass]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("symbols") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(f"paper universe file must list symbols: {path}")
    return _pairs_from_rows(rows)


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


def load_paper_universe(settings: Settings | None = None) -> list[tuple[str, AssetClass]]:
    """Quant paper universe. ``PAPER_UNIVERSE`` = path or ``SYM:class,...`` CSV."""
    settings = settings or get_settings()
    raw = (settings.paper_universe or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_file():
            return _load_json_file(path)
        return _parse_csv(raw)
    if DEFAULT_UNIVERSE_PATH.is_file():
        return _load_json_file(DEFAULT_UNIVERSE_PATH)
    return _pairs_from_rows([{"symbol": s, "asset_class": a} for s, a in _BUILTIN])


def parse_setup_universe(settings: Settings | None = None) -> set[str] | None:
    """ML ``SETUP_UNIVERSE`` allow-list (CSV). ``None`` = unset (no override)."""
    settings = settings or get_settings()
    raw = (settings.setup_universe or "").strip()
    if not raw:
        return None
    if Path(raw).expanduser().is_file():
        return {sym for sym, _ in _load_json_file(Path(raw).expanduser())}
    return {normalize_symbol(part) for part in raw.split(",") if part.strip()}


def setup_universe_allowlist(settings: Settings | None = None) -> set[str] | None:
    return parse_setup_universe(settings)


def resolve_ranking_universe(
    settings: Settings | None = None,
) -> list[tuple[str, AssetClass]]:
    """Paper universe, intersected with ``SETUP_UNIVERSE`` when ML set one."""
    paper = load_paper_universe(settings)
    ml = parse_setup_universe(settings)
    if ml is None:
        return paper
    return [(sym, ac) for sym, ac in paper if sym in ml]


def universe_dump(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    paper = load_paper_universe(settings)
    ml = parse_setup_universe(settings)
    ranking = resolve_ranking_universe(settings)
    return {
        "live_trading": False,
        "refresh_sec": 900,
        "paper_universe": [{"symbol": s, "asset_class": a.value} for s, a in paper],
        "setup_universe": sorted(ml) if ml is not None else None,
        "ranking_universe": [{"symbol": s, "asset_class": a.value} for s, a in ranking],
        "paper_source": (settings.paper_universe or str(DEFAULT_UNIVERSE_PATH)),
        "intersection": ml is not None,
        "n_paper": len(paper),
        "n_ranking": len(ranking),
    }
