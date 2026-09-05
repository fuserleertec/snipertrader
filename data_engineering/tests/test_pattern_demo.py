from __future__ import annotations

import pytest

from sniper_data.cli import main
from sniper_data.pipeline import run_pattern_replay
from sniper_data.pattern_detection.validate import SCHEMA_FILES, validate_topic


@pytest.mark.asyncio
async def test_inmemory_replay_emits_validated_contracts():
    result = await run_pattern_replay()
    assert result["stats"]["sweeps"] >= 2
    assert result["stats"]["fvgs"] >= 1
    assert result["stats"]["mss"] >= 1
    assert result["stats"]["order_blocks"] >= 1
    assert any(k.startswith("sweep:BTCUSDT:") for k in result["redis_keys"])
    assert any(k.startswith("fvg:BTCUSDT:") for k in result["redis_keys"])
    assert any(k.startswith("mss:BTCUSDT:") for k in result["redis_keys"])
    assert any(k.startswith("ob:BTCUSDT:") for k in result["redis_keys"])
    for topic in ("sweep_events", "fvg_zones", "mss_events", "order_block_zones"):
        assert topic in SCHEMA_FILES
        for payload in result["topics"].get(topic, []):
            validate_topic(topic, payload)


def test_cli_patterns_replay():
    rc = main(["patterns", "--inmemory", "--replay"])
    assert rc == 0
