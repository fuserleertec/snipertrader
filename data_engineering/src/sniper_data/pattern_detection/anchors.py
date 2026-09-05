"""Register swing / MSS pivots on the locked DE Phase 2 anchor contract.

Kafka topic: ``anchor_events`` (key = symbol). Same JSON as
``POST /v1/anchors``. Field names are locked — do not invent extras.

Required: ``symbol``, ``anchor_time``, ``anchor_price``, ``source``
Optional: ``anchor_id``, ``asset_class``
``source`` ∈ ``manual`` · ``swing_high`` · ``swing_low`` · ``earnings`` · ``news``
"""

from __future__ import annotations

from typing import Any

from sniper_data.bus.kafka import EventBus
from sniper_data.models import AnchorRegistration, AnchorSource, AssetClass
from sniper_data.pattern_detection.ids import make_id
from sniper_data.pattern_detection.mss import SwingPoint
from sniper_data.symbols import infer_asset_class, normalize_symbol

ANCHOR_TOPIC = "anchor_events"
ANCHOR_SOURCES = frozenset(s.value for s in AnchorSource)
ANCHOR_REQUIRED = ("symbol", "anchor_time", "anchor_price", "source")
ANCHOR_OPTIONAL = ("anchor_id", "asset_class")
ANCHOR_FIELDS = ANCHOR_REQUIRED + ANCHOR_OPTIONAL


def swing_source(kind: str) -> AnchorSource:
    if kind == "high":
        return AnchorSource.SWING_HIGH
    if kind == "low":
        return AnchorSource.SWING_LOW
    raise ValueError(f"swing kind must be 'high' or 'low', got {kind!r}")


def swing_to_registration(
    symbol: str,
    swing: SwingPoint,
    asset_class: AssetClass | str | None = None,
    *,
    anchor_id: str | None = None,
) -> AnchorRegistration:
    symbol = normalize_symbol(symbol)
    klass = infer_asset_class(symbol, asset_class)
    source = swing_source(swing.kind)
    return AnchorRegistration(
        symbol=symbol,
        anchor_time=int(swing.ts_ms),
        anchor_price=float(swing.price),
        source=source,
        asset_class=klass,
        anchor_id=anchor_id or make_id("sw", symbol, source.value, swing.ts_ms),
    )


def to_anchor_payload(req: AnchorRegistration) -> dict[str, Any]:
    """Exact inbound JSON for Kafka ``anchor_events`` and ``POST /v1/anchors``."""
    source = req.source.value if isinstance(req.source, AnchorSource) else str(req.source)
    if source not in ANCHOR_SOURCES:
        raise ValueError(f"source must be one of {sorted(ANCHOR_SOURCES)}, got {source!r}")
    payload: dict[str, Any] = {
        "symbol": normalize_symbol(req.symbol),
        "anchor_time": int(req.anchor_time),
        "anchor_price": float(req.anchor_price),
        "source": source,
    }
    if req.anchor_id:
        payload["anchor_id"] = str(req.anchor_id)
    if req.asset_class is not None:
        klass = req.asset_class.value if isinstance(req.asset_class, AssetClass) else str(req.asset_class)
        payload["asset_class"] = klass
    extra = set(payload) - set(ANCHOR_FIELDS)
    if extra:
        raise ValueError(f"invented anchor fields: {sorted(extra)}")
    return payload


async def publish_anchor(bus: EventBus, req: AnchorRegistration) -> dict[str, Any]:
    """Realtime path: Kafka ``anchor_events``, key = symbol. Idempotent on ``anchor_id``."""
    payload = to_anchor_payload(req)
    await bus.publish(ANCHOR_TOPIC, payload, key=payload["symbol"])
    return payload


async def post_anchor(
    req: AnchorRegistration,
    *,
    base_url: str = "http://127.0.0.1:8000",
    client: Any | None = None,
) -> dict[str, Any]:
    """HTTP helper: ``POST /v1/anchors`` with the same JSON as Kafka.

    ``client`` may be an ``httpx.AsyncClient``, a FastAPI ``TestClient``, or
    any object with ``.post(url, json=...)``. When omitted, a one-shot
    ``httpx.AsyncClient`` is created against ``base_url``.
    """
    payload = to_anchor_payload(req)
    path = "/v1/anchors"
    if client is None:
        import httpx

        async with httpx.AsyncClient(base_url=base_url) as http:
            resp = await http.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()

    url = path if not getattr(client, "base_url", None) else path
    # TestClient / httpx: post("/v1/anchors", json=...)
    posted = client.post(url, json=payload)
    if hasattr(posted, "__await__"):
        posted = await posted
    if hasattr(posted, "raise_for_status"):
        posted.raise_for_status()
    if hasattr(posted, "json"):
        body = posted.json()
        return body() if callable(body) else body
    if isinstance(posted, dict):
        return posted
    raise TypeError(f"unsupported HTTP client response: {type(posted)}")
