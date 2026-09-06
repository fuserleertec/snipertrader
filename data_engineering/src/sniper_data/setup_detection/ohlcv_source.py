"""Locked continuous OHLCV for Setup 4 / Setup 5 (paper only).

Authoritative DE PR #12 sources:

* Kafka ``ohlcv_bars``
* ``WS /v1/ws/ohlcv?symbol=&timeframe=1m|5m``
* ``GET /v1/ohlcv/{symbol}?timeframe=1m|5m``

Do **not** read 15m ``dashboard_snapshots`` or Redis ``dashboard:snapshot:*``.
The 15-minute refresh is the universe / ensemble scan cadence, not an S4/S5
bar timeframe. ``live_trading`` stays false.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from sniper_data.models import OHLCVBar
from sniper_data.symbols import normalize_symbol

log = logging.getLogger(__name__)

CONTINUOUS_TIMEFRAMES = ("1m", "5m")
KAFKA_OHLCV_TOPIC = "ohlcv_bars"
WS_OHLCV_PATH = "/v1/ws/ohlcv"
HTTP_OHLCV_PATH = "/v1/ohlcv"
FORBIDDEN_BAR_TOPICS = frozenset({"dashboard_snapshots"})
FORBIDDEN_REDIS_PREFIXES = ("dashboard:snapshot:",)


def bar_timeframe(bar: OHLCVBar | dict[str, Any]) -> str:
    raw = bar.timeframe if isinstance(bar, OHLCVBar) else bar.get("timeframe")
    if raw is None:
        return ""
    return raw.value if hasattr(raw, "value") else str(raw)


def is_continuous_bar(bar: OHLCVBar | dict[str, Any] | None) -> bool:
    """True only for a real 1m/5m ``OHLCVBar`` (or its wire dict)."""
    if bar is None:
        return False
    if isinstance(bar, dict) and is_dashboard_snapshot(bar):
        return False
    return bar_timeframe(bar) in CONTINUOUS_TIMEFRAMES


def is_dashboard_snapshot(payload: Any) -> bool:
    """True for Kafka ``dashboard_snapshots`` / Redis dashboard snapshot envelopes."""
    if not isinstance(payload, dict):
        return False
    topic = str(payload.get("topic") or "")
    if topic in FORBIDDEN_BAR_TOPICS:
        return True
    if payload.get("pointers") is not None and payload.get("available") is not None:
        return True
    if payload.get("ohlcv") is not None and payload.get("universe_member") is not None:
        return True
    if "dashboard_snapshot" in str(payload.get("schema") or payload.get("$id") or ""):
        return True
    key = str(payload.get("redis_key") or payload.get("key") or "")
    return any(key.startswith(p) for p in FORBIDDEN_REDIS_PREFIXES)


def clamp_continuous_timeframes(
    items: Iterable[str],
    *,
    fallback: tuple[str, ...] = CONTINUOUS_TIMEFRAMES,
) -> tuple[str, ...]:
    kept = tuple(tf for tf in items if tf in CONTINUOUS_TIMEFRAMES)
    return kept or tuple(fallback)


def assert_not_dashboard_source(source: str | None) -> None:
    name = (source or "").strip()
    if name in FORBIDDEN_BAR_TOPICS or name.startswith("dashboard:snapshot"):
        raise ValueError("S4/S5 must not use dashboard_snapshots as an OHLCV source")


async def fetch_continuous_ohlcv(
    bars_store,
    symbol: str,
    timeframe: str,
    *,
    limit: int = 200,
) -> list[OHLCVBar]:
    """Bootstrap from the DE OHLCV store (same rows as GET /v1/ohlcv)."""
    tf = str(timeframe)
    if tf not in CONTINUOUS_TIMEFRAMES:
        raise ValueError(f"S4/S5 OHLCV timeframe must be 1m or 5m, got {tf!r}")
    assert_not_dashboard_source(getattr(bars_store, "source", None))
    rows = await bars_store.fetch(normalize_symbol(symbol), tf, limit=limit)
    return [b for b in rows if is_continuous_bar(b)]


async def fetch_continuous_ohlcv_http(
    base_url: str,
    symbol: str,
    timeframe: str,
    *,
    limit: int = 200,
    timeout_s: float = 3.0,
    transport=None,
) -> list[OHLCVBar]:
    """``GET /v1/ohlcv/{symbol}?timeframe=1m|5m`` — never a dashboard route."""
    tf = str(timeframe)
    if tf not in CONTINUOUS_TIMEFRAMES:
        raise ValueError(f"S4/S5 OHLCV timeframe must be 1m or 5m, got {tf!r}")
    import httpx

    url = f"{base_url.rstrip('/')}{HTTP_OHLCV_PATH}/{normalize_symbol(symbol)}"
    kwargs: dict[str, Any] = {"timeout": timeout_s}
    if transport is not None:
        kwargs["transport"] = transport
    async with httpx.AsyncClient(**kwargs) as client:
        resp = await client.get(url, params={"timeframe": tf, "limit": int(limit)})
        resp.raise_for_status()
        body = resp.json()
    if is_dashboard_snapshot(body):
        raise ValueError("refusing dashboard snapshot payload as S4/S5 bars")
    out: list[OHLCVBar] = []
    for raw in body.get("bars") or []:
        if not is_continuous_bar(raw):
            continue
        out.append(OHLCVBar.model_validate(raw))
    return out
