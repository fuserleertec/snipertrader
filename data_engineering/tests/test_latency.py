from __future__ import annotations

import pytest

from sniper_data.latency import P99_SLO_S, bench_tick_to_vwap, percentile


def test_percentile_edges():
    assert percentile([], 99) == 0.0
    assert percentile([0.01], 99) == 0.01
    assert percentile([0.001, 0.002, 0.003, 0.004], 50) > 0


@pytest.mark.asyncio
async def test_tick_to_vwap_p99_under_slo():
    report = await bench_tick_to_vwap(n=240, symbols=["BTCUSDT"])
    assert report["n"] == 240
    assert report["p99_ms"] < P99_SLO_S * 1000
    assert report["pass"] is True


@pytest.mark.asyncio
async def test_tick_to_vwap_two_x_symbols():
    report = await bench_tick_to_vwap(n=180, symbols=["BTCUSDT", "ETHUSDT", "AAPL", "MSFT", "ES", "NQ"])
    assert report["n"] == 180
    assert report["pass"] is True
    assert report["p99_ms"] < 500
