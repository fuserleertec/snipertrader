"""Setup-signal history store — DE-owned multi-symbol listing.

Quant may keep richer P2 history; this module is the paper pipeline's
Redis + Kafka availability so FE/Quant can list setups for up to 20
symbols. Payload is the existing ``SetupSignal`` wire shape plus optional
``trigger_event_ids``.
"""

from __future__ import annotations

import time
from typing import Any

from sniper_data.models import SetupSignal
from sniper_data.symbols import normalize_symbol
from sniper_data.universe import MAX_UNIVERSE_SYMBOLS
from sniper_data.zones import clamp_ttl

SIGNAL_INDEX_PREFIX = "setup:index:"
SIGNAL_KEY_PREFIX = "setup:"


def setup_key(symbol: str, signal_id: str) -> str:
    return f"{SIGNAL_KEY_PREFIX}{symbol}:{signal_id}"


def setup_index_key(symbol: str) -> str:
    return f"{SIGNAL_INDEX_PREFIX}{symbol}"


def setup_channel(symbol: str) -> str:
    return f"setup:{symbol}"


async def store_setup(
    store,
    signal: SetupSignal,
    ttl_seconds: int | None = None,
) -> str:
    symbol = normalize_symbol(signal.symbol)
    payload = signal.model_copy(update={"symbol": symbol})
    key = setup_key(symbol, payload.id)
    await store.set(key, payload, ttl=clamp_ttl(ttl_seconds))
    ids = await index_ids(store, symbol)
    if payload.id not in ids:
        ids.append(payload.id)
    await store.set(setup_index_key(symbol), ids)
    await store.publish(setup_channel(symbol), payload)
    return key


async def index_ids(store, symbol: str) -> list[str]:
    raw = await store.get(setup_index_key(normalize_symbol(symbol)))
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


async def load_symbol_signals(store, symbol: str) -> list[dict[str, Any]]:
    symbol = normalize_symbol(symbol)
    out: list[dict[str, Any]] = []
    for sid in await index_ids(store, symbol):
        raw = await store.get(setup_key(symbol, sid))
        if isinstance(raw, dict):
            out.append(raw)
    out.sort(key=lambda r: int(r.get("ts_ms") or 0), reverse=True)
    return out


def _parse_symbol_filter(symbol: str | None, symbols: str | None) -> list[str] | None:
    tokens: list[str] = []
    if symbol:
        tokens.append(symbol)
    if symbols:
        tokens.extend(symbols.split(","))
    if not tokens:
        return None
    seen: list[str] = []
    for token in tokens:
        if not token.strip():
            continue
        try:
            item = normalize_symbol(token)
        except ValueError:
            continue
        if item not in seen:
            seen.append(item)
        if len(seen) >= MAX_UNIVERSE_SYMBOLS:
            break
    return seen


async def list_signals(
    store,
    *,
    symbol: str | None = None,
    symbols: str | None = None,
    configured: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    wanted = _parse_symbol_filter(symbol, symbols)
    if wanted is None:
        wanted = list(configured or [])
        if not wanted:
            keys = await store.scan("setup:index:*")
            wanted = [k.split(":", 2)[-1] for k in keys if k.startswith(SIGNAL_INDEX_PREFIX)]
        wanted = wanted[:MAX_UNIVERSE_SYMBOLS]
    rows: list[dict[str, Any]] = []
    for sym in wanted:
        rows.extend(await load_symbol_signals(store, sym))
    rows.sort(key=lambda r: int(r.get("ts_ms") or 0), reverse=True)
    cap = max(1, min(int(limit), 200))
    start = max(0, int(offset))
    page = rows[start : start + cap]
    return {
        "as_of_ts_ms": int(time.time() * 1000),
        "limit": cap,
        "offset": start,
        "count": len(page),
        "total": len(rows),
        "symbols": wanted,
        "live_trading": False,
        "signals": page,
    }
