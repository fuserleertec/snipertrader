"""Internal setup candidate + locked Quant wire adapters.

Conviction (0–100), risk_reward, setup_number, and kill_zone live in
structured logs only. The validate body is the Quant allow-list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sniper_data.models import (
    RISK_VALIDATE_FIELDS,
    SCHEMA_VERSION,
    AssetClass,
    RiskValidateRequest,
    SessionType,
    SetupSignal,
    SetupType,
)

Side = Literal["long", "short"]


@dataclass
class SetupCandidate:
    setup_number: int
    setup_type: SetupType
    symbol: str
    asset_class: AssetClass
    side: Side
    conviction: int
    entry: float
    stop: float
    target: float
    timeframe: Literal["1m", "5m", "15m"]
    trigger_event_ids: list[str]
    ts_ms: int
    ref_vwap: float | None = None
    ref_session: str | None = None
    session_type: str | None = None
    proposed_position_size: float | None = None
    risk_reward: float = 0.0
    kill_zone: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)

    @property
    def confidence(self) -> float:
        return max(0.0, min(1.0, self.conviction / 100.0))

    def log_fields(self) -> dict[str, Any]:
        return {
            "setup_number": self.setup_number,
            "setup_type": self.setup_type,
            "symbol": self.symbol,
            "side": self.side,
            "conviction": self.conviction,
            "risk_reward": round(self.risk_reward, 4),
            "confidence": self.confidence,
            "timeframe": self.timeframe,
            "kill_zone": self.kill_zone,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "trigger_event_ids": list(self.trigger_event_ids),
        }


def to_risk_request(candidate: SetupCandidate) -> dict[str, Any]:
    """Quant-locked validate body. ``id`` is never present."""
    session = candidate.session_type
    parsed_session: SessionType | None = None
    if session:
        parsed_session = SessionType(session) if not isinstance(session, SessionType) else session
    req = RiskValidateRequest(
        schema_version=SCHEMA_VERSION,
        symbol=candidate.symbol,
        asset_class=candidate.asset_class,
        setup_type=candidate.setup_type,
        side=candidate.side,
        ts_ms=candidate.ts_ms,
        entry=candidate.entry,
        stop=candidate.stop,
        target=candidate.target,
        timeframe=candidate.timeframe,
        trigger_event_ids=list(candidate.trigger_event_ids),
        confidence=candidate.confidence,
        ref_vwap=candidate.ref_vwap,
        ref_session=candidate.ref_session,
        session_type=parsed_session,
        proposed_position_size=candidate.proposed_position_size,
    )
    payload = req.model_dump(mode="json", exclude_none=True)
    extra = set(payload) - set(RISK_VALIDATE_FIELDS)
    if extra:
        raise ValueError(f"risk validate payload has non-locked fields: {sorted(extra)}")
    if "id" in payload:
        raise ValueError("risk validate must omit id")
    return payload


def to_setup_signal(
    candidate: SetupCandidate,
    signal_id: str,
    *,
    position_size: float | None,
) -> SetupSignal:
    session = None
    if candidate.session_type:
        session = SessionType(candidate.session_type)
    return SetupSignal(
        id=signal_id,
        symbol=candidate.symbol,
        asset_class=candidate.asset_class,
        setup_type=candidate.setup_type,
        side=candidate.side,
        confidence=candidate.confidence,
        ref_vwap=candidate.ref_vwap,
        ref_session=candidate.ref_session,
        ts_ms=candidate.ts_ms,
        entry=candidate.entry,
        stop=candidate.stop,
        target=candidate.target,
        timeframe=candidate.timeframe,
        trigger_event_ids=list(candidate.trigger_event_ids),
        session_type=session,
        position_size=position_size,
        status="ACTIVE",
    )


def risk_reward(side: Side, entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    reward = (target - entry) if side == "long" else (entry - target)
    if reward <= 0:
        return 0.0
    return reward / risk


def score_conviction(
    *,
    confluence: int = 0,
    volume_confirmed: bool = False,
    kill_zone_aligned: bool = False,
    confirmed_reclaim: bool = False,
    base: int = 40,
) -> int:
    score = base + 10 * max(0, confluence)
    if volume_confirmed:
        score += 15
    if kill_zone_aligned:
        score += 15
    if confirmed_reclaim:
        score += 10
    return max(0, min(100, score))
