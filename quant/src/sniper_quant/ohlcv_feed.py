"""Continuous DE 1m/5m bar feed (paper only).

Sources, in preference order for live marks:

1. Kafka ``ohlcv_bars`` (same payload as ``ohlcv_bar.schema.json``)
2. ``WS {DE_API_BASE}/v1/ws/ohlcv?symbol=&timeframe=1m|5m``
3. ``GET {DE_API_BASE}/v1/ohlcv/{symbol}?timeframe=1m|5m``

``GET /v1/universe/top`` (15m) is the **ranking book only**.
``GET /v1/dashboard/snapshot`` is **not** an OHLC tape.

``live_trading`` stays false.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from sniper_quant.bus import OHLCV_BARS_TOPIC, InMemoryBus, consume_keyed_topic
from sniper_quant.config import Settings, get_settings
from sniper_quant.models import OHLCVBar
from sniper_quant.store.ohlcv import (
    BAR_FEED_TIMEFRAMES,
    OHLCV_HTTP_PATH,
    OHLCV_WS_PATH,
    CompositeBarFeed,
    InMemoryOHLCVLoader,
    OHLCVLoader,
    TimescaleOHLCVLoader,
    assert_bar_feed_timeframe,
)

log = logging.getLogger(__name__)

OnBar = Callable[[OHLCVBar], Awaitable[None]]


def reject_non_bar_envelope(payload: dict[str, Any]) -> None:
    """Universe top / dashboard snapshots are not a bar feed."""
    if not isinstance(payload, dict):
        return
    if "symbols" in payload and ("limit" in payload or "as_of_ts_ms" in payload):
        raise ValueError(
            "GET /v1/universe/top is the 15m ranking book, not an OHLC bar feed"
        )
    if payload.get("snapshot") or payload.get("kind") == "dashboard_snapshot":
        raise ValueError(
            "GET /v1/dashboard/snapshot is not an OHLC bar feed; use 1m/5m ohlcv"
        )
    if "bars" in payload and payload.get("timeframe") not in BAR_FEED_TIMEFRAMES | {None, ""}:
        tf = payload.get("timeframe")
        if tf not in BAR_FEED_TIMEFRAMES:
            raise ValueError(
                f"bar feed timeframe must be 1m or 5m; got {tf!r} "
                "(15m universe/dashboard is not a tape)"
            )


def parse_ohlcv_bar(payload: dict[str, Any]) -> OHLCVBar:
    reject_non_bar_envelope(payload)
    bar = OHLCVBar.model_validate(payload)
    assert_bar_feed_timeframe(bar.timeframe)
    return bar


def parse_de_ohlcv_response(payload: dict[str, Any] | list, *, timeframe: str) -> list[OHLCVBar]:
    """Parse DE ``GET /v1/ohlcv/{symbol}`` ``{symbol, timeframe, bars}``."""
    tf = assert_bar_feed_timeframe(timeframe)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        reject_non_bar_envelope(payload)
        rows = payload.get("bars")
        if rows is None and {"open", "high", "low", "close"} <= set(payload):
            rows = [payload]
        if payload.get("timeframe") and str(payload["timeframe"]) != tf:
            raise ValueError(
                f"DE /v1/ohlcv timeframe {payload.get('timeframe')!r} != requested {tf}"
            )
    else:
        raise ValueError("DE /v1/ohlcv must be an object or bar list")
    if not isinstance(rows, list):
        raise ValueError("DE /v1/ohlcv.bars must be a list")
    out: list[OHLCVBar] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("DE /v1/ohlcv bar must be an object")
        bar = parse_ohlcv_bar(raw)
        if bar.timeframe != tf:
            continue
        out.append(bar)
    out.sort(key=lambda b: b.open_ts_ms)
    return out


def de_ohlcv_http_url(settings: Settings, symbol: str) -> str | None:
    base = (settings.de_api_base or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}{OHLCV_HTTP_PATH}/{symbol}"


def de_ohlcv_ws_url(settings: Settings, symbol: str, timeframe: str = "1m") -> str | None:
    tf = assert_bar_feed_timeframe(timeframe)
    base = (settings.de_api_base or "").strip().rstrip("/")
    if not base:
        return None
    parsed = urlparse(base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    return f"{scheme}://{netloc}{OHLCV_WS_PATH}?symbol={symbol}&timeframe={tf}"


class DeHttpOHLCVLoader:
    """GET ``{DE_API_BASE}/v1/ohlcv/{symbol}?timeframe=1m|5m``."""

    def __init__(self, settings: Settings | None = None, *, timeout: float = 2.5) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    async def upsert(self, bar: OHLCVBar) -> None:
        return None

    async def fetch(
        self,
        symbol: str,
        timeframe: str = "5m",
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 10_000,
    ) -> list[OHLCVBar]:
        tf = assert_bar_feed_timeframe(timeframe)
        from sniper_quant.models import normalize_symbol

        symbol = normalize_symbol(symbol)
        url = de_ohlcv_http_url(self.settings, symbol)
        if not url:
            return []
        import httpx

        resp = httpx.get(
            url,
            params={"timeframe": tf, "limit": min(int(limit), 2000)},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        bars = parse_de_ohlcv_response(resp.json(), timeframe=tf)
        if from_ms is not None:
            bars = [b for b in bars if b.open_ts_ms >= from_ms]
        if to_ms is not None:
            bars = [b for b in bars if b.open_ts_ms <= to_ms]
        return bars[-limit:]

    async def close(self) -> None:
        return None


def build_bar_feed(settings: Settings | None = None, *, inmemory: bool | None = None) -> OHLCVLoader:
    """Paper bar feed: DE GET + Kafka/WS memory overlay; Timescale = persisted Kafka."""
    settings = settings or get_settings()
    use_mem = settings.use_inmemory if inmemory is None else inmemory
    if use_mem:
        return InMemoryOHLCVLoader()
    http = DeHttpOHLCVLoader(settings) if (settings.de_api_base or "").strip() else None
    persist = TimescaleOHLCVLoader(settings.database_url)
    return CompositeBarFeed(http=http, persist=persist)


class OhlcvBarService:
    """Apply continuous 1m/5m bars to the loader (and optional lifecycle)."""

    def __init__(
        self,
        loader: OHLCVLoader,
        *,
        on_bar: OnBar | None = None,
    ) -> None:
        self.loader = loader
        self.on_bar = on_bar

    async def handle(self, payload: dict[str, Any], *, key: str | None = None) -> OHLCVBar | None:
        try:
            bar = parse_ohlcv_bar(payload)
        except (ValueError, TypeError) as exc:
            log.info("skip non-bar-feed ohlcv payload (%s)", exc)
            return None
        except Exception as exc:  # pydantic ValidationError
            log.info("skip invalid ohlcv_bars payload (%s)", exc)
            return None
        await self.loader.upsert(bar)
        if self.on_bar is not None:
            await self.on_bar(bar)
        return bar


async def run_inmemory_ohlcv_consumer(
    bus: InMemoryBus,
    service: OhlcvBarService,
    *,
    topic: str = OHLCV_BARS_TOPIC,
) -> None:
    async def _on(payload: dict) -> None:
        await service.handle(payload)

    bus.subscribe(topic, _on)
    await bus.start()


async def run_ohlcv_kafka_consumer(
    service: OhlcvBarService,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    group = getattr(settings, "kafka_group_ohlcv", None) or "sniper-quant-ohlcv"
    log.info(
        "consuming %s at %s group=%s (1m/5m bar feed, paper only)",
        OHLCV_BARS_TOPIC,
        settings.kafka_bootstrap,
        group,
    )
    async for key, payload in consume_keyed_topic(
        settings.kafka_bootstrap,
        OHLCV_BARS_TOPIC,
        group,
    ):
        await service.handle(payload, key=key)


async def run_de_ohlcv_ws_consumer(
    service: OhlcvBarService,
    settings: Settings,
    *,
    symbol: str,
    timeframe: str = "1m",
) -> None:
    """Follow DE ``WS /v1/ws/ohlcv`` when Kafka is not the live path."""
    url = de_ohlcv_ws_url(settings, symbol, timeframe)
    if not url:
        return
    try:
        import websockets
    except ImportError:
        log.info("websockets extra missing; skip WS %s", url)
        return
    log.info("ohlcv ws %s (paper only)", url)
    async with websockets.connect(url) as ws:
        async for raw in ws:
            try:
                import json

                payload = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            except Exception:  # noqa: BLE001
                continue
            if isinstance(payload, dict):
                await service.handle(payload)
