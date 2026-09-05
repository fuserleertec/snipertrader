from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"

EXPECTED = {
    "raw_tick.schema.json",
    "ohlcv_bar.schema.json",
    "session_levels.schema.json",
    "vwap_values.schema.json",
    "sweep_event.schema.json",
    "fvg_zone.schema.json",
    "setup_signal.schema.json",
    "risk_validate_request.schema.json",
    "risk_validate_response.schema.json",
    "dashboard_signal.schema.json",
    "signal_ws_event.schema.json",
}


def test_schema_catalog_present():
    names = {p.name for p in SCHEMAS.glob("*.schema.json")}
    assert EXPECTED <= names
    for name in EXPECTED:
        doc = json.loads((SCHEMAS / name).read_text())
        assert doc["$schema"].startswith("https://json-schema.org/")
        assert doc["title"]
