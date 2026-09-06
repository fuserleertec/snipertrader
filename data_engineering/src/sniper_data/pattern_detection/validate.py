"""Validate published payloads against landed /schemas (draft 2020-12)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

SCHEMA_FILES = {
    "raw_ticks": "raw_tick.schema.json",
    "ohlcv_bars": "ohlcv_bar.schema.json",
    "session_levels": "session_levels.schema.json",
    "vwap_values": "vwap_values.schema.json",
    "sweep_events": "sweep_event.schema.json",
    "fvg_zones": "fvg_zone.schema.json",
    "mss_events": "mss_event.schema.json",
    "order_block_zones": "order_block.schema.json",
    "setup_signals": "setup_signal.schema.json",
}


def schemas_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / "sweep_event.schema.json").is_file():
            return candidate
    raise FileNotFoundError("could not locate /schemas")


@lru_cache(maxsize=16)
def _validator(schema_name: str):
    from jsonschema import Draft202012Validator

    path = schemas_dir() / schema_name
    return Draft202012Validator(json.loads(path.read_text()))


def to_payload(value: Any) -> dict:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if v is not None}
    raise TypeError(f"cannot serialize {type(value)}")


def validate_topic(topic: str, value: Any) -> dict:
    payload = to_payload(value)
    name = SCHEMA_FILES.get(topic)
    if name is None:
        raise KeyError(f"no schema registered for topic {topic}")
    _validator(name).validate(payload)
    return payload
