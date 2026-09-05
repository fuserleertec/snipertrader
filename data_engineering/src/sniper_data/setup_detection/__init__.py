"""USME setup detection (Phase 3) — setups 1–6.

Consumes landed DE Kafka topics and Redis keys only. Candidates go to
Quant ``POST /risk/validate`` (no ``id``) and, if ``approved: true``,
to Kafka ``setup_signals`` with an assigned ``id``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sniper_data.setup_detection.candidate import SetupCandidate, to_risk_request
    from sniper_data.setup_detection.orchestrator import SetupOrchestrator, dedupe_candidates
    from sniper_data.setup_detection.risk_client import HttpRiskClient, StaticRiskClient

__all__ = [
    "HttpRiskClient",
    "SetupCandidate",
    "SetupOrchestrator",
    "StaticRiskClient",
    "dedupe_candidates",
    "to_risk_request",
]


def __getattr__(name: str) -> Any:
    if name in {"SetupCandidate", "to_risk_request"}:
        from sniper_data.setup_detection.candidate import SetupCandidate, to_risk_request

        return SetupCandidate if name == "SetupCandidate" else to_risk_request
    if name in {"SetupOrchestrator", "dedupe_candidates"}:
        from sniper_data.setup_detection.orchestrator import SetupOrchestrator, dedupe_candidates

        return SetupOrchestrator if name == "SetupOrchestrator" else dedupe_candidates
    if name in {"HttpRiskClient", "StaticRiskClient"}:
        from sniper_data.setup_detection.risk_client import HttpRiskClient, StaticRiskClient

        return HttpRiskClient if name == "HttpRiskClient" else StaticRiskClient
    raise AttributeError(name)
