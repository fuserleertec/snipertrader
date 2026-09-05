"""Stub alerting: Telegram / Discord / Email / webhook + 5/hour/user throttle.

No live network calls. Each dispatch is recorded for tests and the PM gate.
Confidence ≥ 0.80 is sent immediately; lower-confidence signals are still
logged but marked ``deferred``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sniper_quant.models import SignalView

Channel = Literal["telegram", "discord", "email", "webhook"]
CHANNELS: tuple[str, ...] = ("telegram", "discord", "email", "webhook")
MAX_ALERTS_PER_HOUR = 5
IMMEDIATE_CONFIDENCE = 0.80
HOUR_MS = 60 * 60 * 1000


@dataclass
class AlertSubscription:
    user_id: str
    channel: str
    target: str


@dataclass
class AlertRecord:
    user_id: str
    channel: str
    target: str
    signal_id: str
    ts_ms: int
    immediate: bool
    throttled: bool
    stub: str


@dataclass
class AlertService:
    max_per_hour: int = MAX_ALERTS_PER_HOUR
    immediate_confidence: float = IMMEDIATE_CONFIDENCE
    subscriptions: list[AlertSubscription] = field(default_factory=list)
    log: list[AlertRecord] = field(default_factory=list)

    def subscribe(self, user_id: str, channel: str, target: str) -> AlertSubscription:
        if channel not in CHANNELS:
            raise ValueError(f"unknown channel {channel!r}; expected {CHANNELS}")
        sub = AlertSubscription(user_id=user_id, channel=channel, target=target)
        self.subscriptions = [
            s for s in self.subscriptions if not (s.user_id == user_id and s.channel == channel)
        ]
        self.subscriptions.append(sub)
        return sub

    def unsubscribe(self, user_id: str, channel: str | None = None) -> int:
        before = len(self.subscriptions)
        self.subscriptions = [
            s
            for s in self.subscriptions
            if s.user_id != user_id or (channel is not None and s.channel != channel)
        ]
        return before - len(self.subscriptions)

    def _count_hour(self, user_id: str, now_ms: int) -> int:
        return sum(
            1
            for row in self.log
            if row.user_id == user_id and not row.throttled and now_ms - row.ts_ms < HOUR_MS
        )

    def _stub_line(self, channel: str, target: str, view: SignalView) -> str:
        side = view.side.value if hasattr(view.side, "value") else str(view.side)
        setup = view.setup_type.value if hasattr(view.setup_type, "value") else str(view.setup_type)
        return (
            f"[{channel}] → {target} | {view.symbol} {side} {setup} "
            f"entry={view.entry} stop={view.stop} target={view.target} "
            f"conf={view.confidence}"
        )

    def dispatch(self, view: SignalView, *, now_ms: int | None = None) -> list[AlertRecord]:
        ts = now_ms if now_ms is not None else int(view.ts_ms)
        conf = view.confidence if view.confidence is not None else 0.0
        immediate = conf + 1e-12 >= self.immediate_confidence
        sent: list[AlertRecord] = []
        for sub in list(self.subscriptions):
            used = self._count_hour(sub.user_id, ts)
            throttled = used >= self.max_per_hour
            rec = AlertRecord(
                user_id=sub.user_id,
                channel=sub.channel,
                target=sub.target,
                signal_id=view.id,
                ts_ms=ts,
                immediate=immediate,
                throttled=throttled,
                stub="" if throttled else self._stub_line(sub.channel, sub.target, view),
            )
            self.log.append(rec)
            sent.append(rec)
        return sent

    def dump(self) -> dict[str, Any]:
        return {
            "channels": list(CHANNELS),
            "max_per_hour": self.max_per_hour,
            "immediate_confidence": self.immediate_confidence,
            "subscriptions": [
                {"user_id": s.user_id, "channel": s.channel, "target": s.target}
                for s in self.subscriptions
            ],
            "sent": sum(1 for r in self.log if not r.throttled),
            "throttled": sum(1 for r in self.log if r.throttled),
            "log": [
                {
                    "user_id": r.user_id,
                    "channel": r.channel,
                    "target": r.target,
                    "signal_id": r.signal_id,
                    "ts_ms": r.ts_ms,
                    "immediate": r.immediate,
                    "throttled": r.throttled,
                    "stub": r.stub,
                }
                for r in self.log
            ],
        }
