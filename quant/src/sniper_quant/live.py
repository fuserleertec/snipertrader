"""In-process fan-out for ``WS /ws/signals``."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import WebSocket

from sniper_quant.models import SignalView, SignalWsEvent

log = logging.getLogger(__name__)

WsType = Literal["signal.upsert", "signal.status"]


class SignalHub:
    def __init__(self) -> None:
        self.clients: list[WebSocket] = []

    def subscribe(self, websocket: WebSocket) -> None:
        self.clients.append(websocket)

    def unsubscribe(self, websocket: WebSocket) -> None:
        if websocket in self.clients:
            self.clients.remove(websocket)

    async def publish(self, event_type: WsType, signal: SignalView) -> None:
        event = SignalWsEvent(type=event_type, signal=signal)
        payload = event.model_dump()
        stale: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.unsubscribe(ws)
        if stale:
            log.debug("dropped %s stale signal websocket(s)", len(stale))
