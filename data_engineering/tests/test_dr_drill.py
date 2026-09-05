from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sniper_data.dr_drill import _kafka_catchup, run_drill


@pytest.mark.asyncio
async def test_kafka_catchup_no_permanent_loss():
    result = await _kafka_catchup(50)
    assert result["published"] == 50
    assert result["live_consumed"] == 50
    assert result["replayed_after_bounce"] == 50
    assert result["no_permanent_loss"] is True


@pytest.mark.asyncio
async def test_redis_rdb_restart_restores_keys(tmp_path: Path):
    if not shutil.which("redis-server"):
        pytest.skip("redis-server not installed")
    obs = await run_drill(workdir=tmp_path / "rdb")
    assert obs["redis_rdb_ok"] is True
    assert obs["restore"]["vwap_restored"]["vwap"] == 67123.5
    assert obs["restore"]["outcomes_restored"][0]["setup"] == "1_liquidity_sweep_vwap_reclaim"
    assert obs["kafka_catchup"]["no_permanent_loss"] is True
    assert obs["pass"] is True
