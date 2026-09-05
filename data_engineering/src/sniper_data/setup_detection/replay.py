"""In-memory setup replay (no brokers). Used by ``sniper-data setups --inmemory``."""

from __future__ import annotations

import logging
from typing import Any

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.kill_zones import redis_kill_zone_key
from sniper_data.sessions import redis_session_key
from sniper_data.setup_detection.fixtures import (
    SYM,
    VWAP_SESSION,
    asia_high_sweep,
    asia_session,
    bullish_fvg,
    bullish_mss_after_low,
    confirmed_buy_sweep,
    ny_am_kill_zone,
    seed_common,
    setup1_long_bars,
    setup2_retrace_bars,
    setup3_judas_bars,
)
from sniper_data.setup_detection.orchestrator import SetupOrchestrator
from sniper_data.setup_detection.risk_client import StaticRiskClient
from sniper_data.volume_profile import redis_volume_profile_key
from sniper_data.vwap import redis_vwap_key
from sniper_data.zones import store_fvg

log = logging.getLogger(__name__)


async def run_setup_replay(*, risk=None) -> dict[str, Any]:
    bus = InMemoryBus()
    store = InMemoryStateStore()
    client = risk if risk is not None else StaticRiskClient(approved=True, reason="replay")
    orch = SetupOrchestrator(store, bus, client, swing_lookback=2)
    await seed_common(store)

    orch.on_vwap(VWAP_SESSION)
    orch.on_session(asia_session())
    orch.on_kill_zone(ny_am_kill_zone())

    # Setup 1 — confirmed low sweep + bullish MSS + close above session VWAP.
    sweep = confirmed_buy_sweep()
    orch.on_sweep(sweep)
    bars1 = setup1_long_bars()
    for b in bars1[:-1]:
        await orch.on_bar(b)
    orch.on_mss(bullish_mss_after_low(ts_ms=bars1[-1].close_ts_ms))
    await orch.on_bar(bars1[-1])

    # Setup 2 — FVG at VWAP + retrace confirmation.
    orch2_bus = bus
    orch2 = SetupOrchestrator(store, orch2_bus, client, swing_lookback=2)
    orch2.on_vwap(VWAP_SESSION)
    orch2.on_fvg(bullish_fvg())
    await store_fvg(store, bullish_fvg())
    for b in setup2_retrace_bars():
        await orch2.on_bar(b)

    # Setup 3 — Asia sweep during NY AM + displacement toward VWAP.
    orch3 = SetupOrchestrator(store, bus, client, swing_lookback=2)
    orch3.on_vwap(VWAP_SESSION)
    orch3.on_session(asia_session())
    orch3.on_kill_zone(ny_am_kill_zone())
    orch3.on_sweep(asia_high_sweep())
    for b in setup3_judas_bars():
        await orch3.on_bar(b)

    merged_stats = {
        "setup1": orch.stats.as_dict(),
        "setup2": orch2.stats.as_dict(),
        "setup3": orch3.stats.as_dict(),
    }
    signals = [r["value"] for r in bus.topics.get("setup_signals", [])]
    return {
        "stats": merged_stats,
        "signals": signals,
        "raw": orch.raw_log + orch2.raw_log + orch3.raw_log,
        "approved": orch.approved_log + orch2.approved_log + orch3.approved_log,
        "risk_calls": getattr(client, "calls", []),
        "redis_keys": {
            "vwap": redis_vwap_key(SYM, "session"),
            "session_asia": redis_session_key(SYM, "asia"),
            "volume_profile": redis_volume_profile_key(SYM, "london"),
            "kill_zone": redis_kill_zone_key(SYM),
        },
    }
