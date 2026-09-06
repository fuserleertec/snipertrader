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
    atr_warmup,
    bullish_fvg,
    bullish_mss_after_low,
    confirmed_buy_sweep,
    ny_am_kill_zone,
    pullback_ob,
    seed_avwap,
    seed_common,
    setup1_long_bars,
    setup2_retrace_bars,
    setup3_judas_bars,
    setup4_fade_long_bars,
    setup4_vol_warmup,
    setup5_pullback_bars,
    setup5_rising_vwaps,
    setup5_trend_bars,
    setup6_htf_warmup,
    setup6_rejection_bars,
)
from sniper_data.setup_detection.orchestrator import SetupOrchestrator
from sniper_data.setup_detection.params import SetupParams
from sniper_data.setup_detection.risk_client import StaticRiskClient
from sniper_data.volume_profile import redis_volume_profile_key
from sniper_data.vwap import redis_vwap_key
from sniper_data.zones import store_fvg, store_ob

log = logging.getLogger(__name__)


def _orch(store, bus, client, *, params: SetupParams | None = None) -> SetupOrchestrator:
    return SetupOrchestrator(store, bus, client, swing_lookback=2, params=params or SetupParams())


async def run_setup_replay(*, risk=None) -> dict[str, Any]:
    bus = InMemoryBus()
    client = risk if risk is not None else StaticRiskClient(approved=True, reason="replay")

    # Setup 1 — confirmed low sweep + bullish MSS + close above session VWAP.
    store1 = InMemoryStateStore()
    await seed_common(store1)
    orch1 = _orch(store1, bus, client)
    orch1.on_vwap(VWAP_SESSION)
    orch1.on_session(asia_session())
    orch1.on_kill_zone(ny_am_kill_zone())
    for b in atr_warmup():
        await orch1.on_bar(b)
    orch1.on_sweep(confirmed_buy_sweep())
    bars1 = setup1_long_bars(start=14)
    for b in bars1[:-1]:
        await orch1.on_bar(b)
    orch1.on_mss(bullish_mss_after_low(ts_ms=bars1[-1].close_ts_ms))
    await orch1.on_bar(bars1[-1])

    # Setup 2 — FVG at VWAP + retrace confirmation.
    store2 = InMemoryStateStore()
    await seed_common(store2, fvg=True, ob=True)
    orch2 = _orch(store2, bus, client)
    orch2.on_vwap(VWAP_SESSION)
    orch2.on_fvg(bullish_fvg())
    await store_fvg(store2, bullish_fvg())
    for b in setup2_retrace_bars():
        await orch2.on_bar(b)

    # Setup 3 — Asia sweep during NY AM + displacement toward VWAP.
    store3 = InMemoryStateStore()
    await seed_common(store3)
    orch3 = _orch(store3, bus, client)
    orch3.on_vwap(VWAP_SESSION)
    orch3.on_session(asia_session())
    orch3.on_kill_zone(ny_am_kill_zone())
    for b in atr_warmup():
        await orch3.on_bar(b)
    orch3.on_sweep(asia_high_sweep())
    for b in setup3_judas_bars(start=14):
        await orch3.on_bar(b)

    # Setup 4 — session VWAP ±2σ fade, low volume, rejection candle.
    store4 = InMemoryStateStore()
    await seed_common(store4)
    orch4 = _orch(store4, bus, client)
    orch4.on_vwap(VWAP_SESSION)
    for b in setup4_vol_warmup():
        await orch4.on_bar(b)
    for b in setup4_fade_long_bars():
        await orch4.on_bar(b)

    # Setup 5 — rising session VWAP trend + first VWAP touch + OB (not FVG, so Setup 2 stays quiet).
    store5 = InMemoryStateStore()
    await seed_common(store5)
    orch5 = _orch(store5, bus, client)
    await store_ob(store5, pullback_ob())
    trend = setup5_trend_bars()
    vwaps = setup5_rising_vwaps(len(trend))
    for snap, b in zip(vwaps, trend, strict=True):
        orch5.on_vwap(snap)
        await orch5.on_bar(b)
    orch5.on_vwap(VWAP_SESSION)
    for b in setup5_pullback_bars(start=len(trend)):
        await orch5.on_bar(b)

    # Setup 6 — Phase 2 AVWAP nested bands inside HTF OB + 4H rejection.
    store6 = InMemoryStateStore()
    await seed_common(store6)
    await seed_avwap(store6)
    orch6 = _orch(store6, bus, client)
    for b in setup6_htf_warmup():
        await orch6.on_bar(b)
    for b in setup6_rejection_bars():
        await orch6.on_bar(b)

    merged_stats = {
        "setup1": orch1.stats.as_dict(),
        "setup2": orch2.stats.as_dict(),
        "setup3": orch3.stats.as_dict(),
        "setup4": orch4.stats.as_dict(),
        "setup5": orch5.stats.as_dict(),
        "setup6": orch6.stats.as_dict(),
    }
    signals = [r["value"] for r in bus.topics.get("setup_signals", [])]
    raw = (
        orch1.raw_log
        + orch2.raw_log
        + orch3.raw_log
        + orch4.raw_log
        + orch5.raw_log
        + orch6.raw_log
    )
    return {
        "stats": merged_stats,
        "signals": signals,
        "raw": raw,
        "approved": (
            orch1.approved_log
            + orch2.approved_log
            + orch3.approved_log
            + orch4.approved_log
            + orch5.approved_log
            + orch6.approved_log
        ),
        "risk_calls": getattr(client, "calls", []),
        "pre_filter": (
            orch1.pre_filter_log
            + orch4.pre_filter_log
            + orch5.pre_filter_log
            + orch6.pre_filter_log
        ),
        "redis_keys": {
            "vwap": redis_vwap_key(SYM, "session"),
            "session_asia": redis_session_key(SYM, "asia"),
            "volume_profile": redis_volume_profile_key(SYM, "london"),
            "kill_zone": redis_kill_zone_key(SYM),
            "avwap": f"avwap:{SYM}:anc-swing-4h",
        },
    }
