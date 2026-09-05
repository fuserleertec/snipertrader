from __future__ import annotations

import pytest

from sniper_data.loadtest import DEFAULT_SYMBOLS, bench_under_load
from sniper_data.latency import P99_SLO_S


@pytest.mark.asyncio
async def test_under_load_p99_and_no_loss():
    report = await bench_under_load(n=800, symbols=list(DEFAULT_SYMBOLS))
    assert report["n"] == 800
    assert report["symbol_count"] == 8
    assert report["counts"]["ticks_in"] == 800
    assert report["counts"]["ticks_processed"] == 800
    assert report["counts"]["raw_ticks_published"] == 800
    assert report["counts"]["vwap_session_hits"] == 800
    assert report["no_data_loss"] is True
    assert report["p99_ms"] < P99_SLO_S * 1000
    assert report["pass"] is True
