"""Phase 2 surface: Kafka gate, lifecycle close fields, Grafana, po3_judas."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sniper_quant.api import create_app
from sniper_quant.bus import SETUP_SIGNALS_TOPIC, InMemoryBus
from sniper_quant.models import SIGNAL_VIEW_FIELDS, SetupType
from sniper_quant.risk.engine import RiskEngine, RiskState
from sniper_quant.setups import SETUP_TYPES
from sniper_quant.store.signals import InMemorySignalStore
from tests.conftest import make_settings


def test_po3_judas_in_locked_enum():
    assert "po3_judas" in SETUP_TYPES
    assert SetupType.PO3_JUDAS.value == "po3_judas"


def test_kafka_topic_and_inmemory_gate():
    assert SETUP_SIGNALS_TOPIC == "setup_signals"
    from sniper_quant.validate_service import SignalValidationService, run_kafka_consumer

    assert callable(run_kafka_consumer)
    assert SignalValidationService is not None
    bus = InMemoryBus()
    assert bus.history(SETUP_SIGNALS_TOPIC) == []


def test_lifecycle_close_fields_on_openapi():
    settings = make_settings()
    app = create_app(
        settings=settings,
        signals=InMemorySignalStore(),
        engine=RiskEngine(settings=settings, state=RiskState(equity=100_000)),
    )
    http = TestClient(app)
    spec = http.get("/openapi.json").json()
    assert "/signals/history" in spec["paths"]
    props = spec["components"]["schemas"]["SignalView"]["properties"]
    for key in ("realized_r", "exit_price", "closed_ts_ms", "contributing_factors", "factor_breakdown"):
        assert key in props
    assert set(SIGNAL_VIEW_FIELDS) >= {
        "realized_r",
        "exit_price",
        "closed_ts_ms",
        "contributing_factors",
        "factor_breakdown",
    }


def test_grafana_provisioning_complete():
    root = Path(__file__).resolve().parents[1] / "grafana/provisioning"
    dash = json.loads(
        (root / "dashboards/json/setup-performance.json").read_text(encoding="utf-8")
    )
    titles = {p["title"] for p in dash["panels"]}
    assert "Average realized_r (R:R) by day" in titles
    assert (root / "datasources/timescale.yml").is_file()
    assert (root / "alerting/signal-quality.yml").is_file()
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
    assert "3002:3000" in compose
    assert "signal-validate" in compose or "validate" in compose.lower()
