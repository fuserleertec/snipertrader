"""Paper multi-symbol pattern + setups 1–6 scan (15-minute cadence).

Default universe includes **ES, CL, GC, NQ**. Each required future is
fed through sweep / FVG / pullback generators (setups 1–6 rematerialized
off the BTCUSDT fixtures). Symbols without active DE levels are skipped.

``live_trading`` stays false. Risk validate (locked fields, omit id)
runs before every ``setup_signals`` publish. Setup 2 wire type is
``fvg_entry`` only.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from sniper_data.bus.kafka import InMemoryBus
from sniper_data.bus.redis_store import InMemoryStateStore
from sniper_data.config import get_settings
from sniper_data.kill_zones import redis_kill_zone_key
from sniper_data.pattern_detection.engine import PatternEngine
from sniper_data.pattern_detection.fixtures import (
    buy_side_sweep_sequence,
    fvg_create_and_fill,
    london_session,
)
from sniper_data.sessions import redis_session_key
from sniper_data.setup_detection.activity import must_skip_symbol
from sniper_data.setup_detection.fixtures import (
    VWAP_SESSION,
    asia_high_sweep,
    asia_session,
    atr_warmup,
    bullish_fvg,
    bullish_mss_after_low,
    confirmed_buy_sweep,
    ny_am_kill_zone,
    pullback_ob,
    htf_bullish_ob,
    phase2_avwap,
    seed_avwap,
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
    volume_profile_at,
)
from sniper_data.setup_detection.history import StaticFillSource, history_summary, join_paper_history
from sniper_data.setup_detection.orchestrator import SetupOrchestrator
from sniper_data.setup_detection.params import SetupParams
from sniper_data.setup_detection.ranking import (
    DEFAULT_RANK_WINDOW_MS,
    ENSEMBLE_FEATURES_TOPIC,
    EnsembleBook,
    ensemble_features_snapshot,
)
from sniper_data.setup_detection.remap import remap_many, remap_model
from sniper_data.setup_detection.risk_client import StaticRiskClient
from sniper_data.universe import REQUIRED_FUTURES, UniverseProvider, build_universe_provider, resolve_scan_universe
from sniper_data.volume_profile import redis_volume_profile_key
from sniper_data.vwap import redis_vwap_key
from sniper_data.zones import store_fvg, store_ob

log = logging.getLogger(__name__)

Recipe = Literal["sweep", "fvg", "judas", "fade", "pullback", "avwap"]

# Required futures always get a generator. Extra universe names cycle these.
_FUTURES_RECIPES: dict[str, Recipe] = {
    "ES": "sweep",
    "CL": "fvg",
    "GC": "pullback",
    "NQ": "judas",
}

_CYCLE: tuple[Recipe, ...] = ("sweep", "fvg", "pullback", "fade", "judas", "avwap")


def recipe_for(symbol: str, index: int) -> Recipe:
    return _FUTURES_RECIPES.get(symbol, _CYCLE[index % len(_CYCLE)])


async def seed_symbol(store, symbol: str, *, fvg: bool = False, ob: bool = False) -> None:
    """Write DE-contract keys for ``symbol`` from the locked fixture geometry."""
    snap = remap_model(VWAP_SESSION, symbol)
    asia = remap_model(asia_session(), symbol)
    await store.set(redis_vwap_key(symbol, "session"), snap)
    await store.set(redis_session_key(symbol, "asia"), asia)
    await store.set(redis_volume_profile_key(symbol, "london"), remap_model(volume_profile_at(100.0), symbol))
    await store.set(redis_kill_zone_key(symbol), remap_model(ny_am_kill_zone(), symbol))
    if fvg:
        await store_fvg(store, remap_model(bullish_fvg(), symbol))
    if ob:
        await store_ob(store, remap_model(pullback_ob(), symbol))


async def _run_patterns(store, bus, symbol: str) -> dict[str, int]:
    engine = PatternEngine(store, bus, swing_lookback=2)
    engine.sweep.on_session(remap_model(london_session(), symbol))
    for b in remap_many(buy_side_sweep_sequence(sweep_volume=0.01), symbol):
        await engine.on_bar(b)
    for b in remap_many(fvg_create_and_fill(), symbol):
        await engine.on_bar(b)
    return engine.snapshot()


async def run_recipe(
    symbol: str,
    recipe: Recipe,
    *,
    bus,
    risk,
    params: SetupParams | None = None,
) -> dict[str, Any]:
    store = InMemoryStateStore()
    orch = SetupOrchestrator(store, bus, risk, swing_lookback=2, params=params or SetupParams())
    pattern_stats: dict[str, int] = {}

    if recipe == "sweep":
        await seed_symbol(store, symbol)
        pattern_stats = await _run_patterns(store, bus, symbol)
        orch.on_vwap(remap_model(VWAP_SESSION, symbol))
        orch.on_session(remap_model(asia_session(), symbol))
        orch.on_kill_zone(remap_model(ny_am_kill_zone(), symbol))
        for b in remap_many(atr_warmup(), symbol):
            await orch.on_bar(b)
        orch.on_sweep(remap_model(confirmed_buy_sweep(), symbol))
        bars = remap_many(setup1_long_bars(start=14), symbol)
        for b in bars[:-1]:
            await orch.on_bar(b)
        orch.on_mss(remap_model(bullish_mss_after_low(ts_ms=bars[-1].close_ts_ms), symbol))
        await orch.on_bar(bars[-1])
    elif recipe == "fvg":
        await seed_symbol(store, symbol, fvg=True, ob=True)
        pattern_stats = await _run_patterns(store, bus, symbol)
        orch.on_vwap(remap_model(VWAP_SESSION, symbol))
        orch.on_fvg(remap_model(bullish_fvg(), symbol))
        for b in remap_many(setup2_retrace_bars(), symbol):
            await orch.on_bar(b)
    elif recipe == "judas":
        await seed_symbol(store, symbol)
        orch.on_vwap(remap_model(VWAP_SESSION, symbol))
        orch.on_session(remap_model(asia_session(), symbol))
        orch.on_kill_zone(remap_model(ny_am_kill_zone(), symbol))
        for b in remap_many(atr_warmup(), symbol):
            await orch.on_bar(b)
        orch.on_sweep(remap_model(asia_high_sweep(), symbol))
        for b in remap_many(setup3_judas_bars(start=14), symbol):
            await orch.on_bar(b)
    elif recipe == "fade":
        await seed_symbol(store, symbol)
        orch.on_vwap(remap_model(VWAP_SESSION, symbol))
        for b in remap_many(setup4_vol_warmup(), symbol):
            await orch.on_bar(b)
        for b in remap_many(setup4_fade_long_bars(), symbol):
            await orch.on_bar(b)
    elif recipe == "pullback":
        await seed_symbol(store, symbol, ob=True)
        await store_ob(store, remap_model(pullback_ob(), symbol))
        trend = remap_many(setup5_trend_bars(), symbol)
        vwaps = remap_many(setup5_rising_vwaps(len(trend)), symbol)
        for snap, b in zip(vwaps, trend, strict=True):
            orch.on_vwap(snap)
            await orch.on_bar(b)
        orch.on_vwap(remap_model(VWAP_SESSION, symbol))
        for b in remap_many(setup5_pullback_bars(start=len(trend)), symbol):
            await orch.on_bar(b)
    elif recipe == "avwap":
        await seed_symbol(store, symbol)
        await seed_avwap(store, snap=remap_model(phase2_avwap(), symbol), ob=False)
        await store_ob(store, remap_model(htf_bullish_ob(), symbol))
        for b in remap_many(setup6_htf_warmup(), symbol):
            await orch.on_bar(b)
        for b in remap_many(setup6_rejection_bars(), symbol):
            await orch.on_bar(b)
    else:
        raise ValueError(f"unknown recipe {recipe}")

    return {
        "symbol": symbol,
        "recipe": recipe,
        "stats": orch.stats.as_dict(),
        "patterns": pattern_stats,
        "skipped_inactive": orch.stats.skipped_inactive,
    }


async def scan_universe(
    *,
    symbols: list[str] | None = None,
    provider: UniverseProvider | None = None,
    risk=None,
    params: SetupParams | None = None,
    include_inactive: list[str] | None = None,
) -> dict[str, Any]:
    """One paper cycle: pattern + setups 1–6 across the universe."""
    if symbols is None:
        provider = provider or build_universe_provider()
        snap = await resolve_scan_universe(provider, limit=20)
        symbols = list(snap.symbols)
        source = snap.source
        backend = snap.backend
    else:
        source = "override"
        backend = "env"
        snap = None

    bus = InMemoryBus()
    client = risk if risk is not None else StaticRiskClient(approved=True, reason="paper_scan")
    book = EnsembleBook(window_ms=DEFAULT_RANK_WINDOW_MS)
    skip_log: list[dict[str, Any]] = []
    per_symbol: list[dict[str, Any]] = []

    # Required futures first so ES/CL/GC/NQ always run when present.
    ordered: list[str] = []
    for req in REQUIRED_FUTURES:
        if req in symbols and req not in ordered:
            ordered.append(req)
    for sym in symbols:
        if sym not in ordered:
            ordered.append(sym)

    async def _one(idx: int, symbol: str) -> dict[str, Any]:
        probe = InMemoryStateStore()
        # Inactive extras (no seed) prove skip. Required recipes seed first.
        if include_inactive and symbol in include_inactive:
            skip, reason, levels = await must_skip_symbol(probe, symbol)
            skip_log.append({
                "symbol": symbol,
                "active_levels": False,
                "skip_reason": reason,
                "reason": reason,
                "levels": levels.as_dict(),
            })
            return {
                "symbol": symbol,
                "recipe": None,
                "skipped": True,
                "reason": reason,
                "skip_reason": reason,
                "active_levels": False,
            }
        recipe = recipe_for(symbol, idx)
        return await run_recipe(symbol, recipe, bus=bus, risk=client, params=params)

    results = await asyncio.gather(*[_one(i, sym) for i, sym in enumerate(ordered)])
    per_symbol.extend(results)

    signals = [r["value"] for r in bus.topics.get("setup_signals", [])]
    for payload in signals:
        book.record(payload)
    picks = book.top(limit=10, universe=symbols)
    features = ensemble_features_snapshot(
        picks,
        universe=symbols,
        window_ms=DEFAULT_RANK_WINDOW_MS,
        signals=signals,
        skipped=skip_log,
    )
    await bus.publish(ENSEMBLE_FEATURES_TOPIC, features, key="ensemble")
    book.record_features(features)

    # Paper history join point (unresolved until Quant fills arrive).
    history = join_paper_history(signals, fills=StaticFillSource())

    risk_calls = getattr(client, "calls", [])
    return {
        "live_trading": False,
        "universe": symbols,
        "universe_source": source,
        "universe_backend": backend,
        "refresh_minutes": 15,
        "per_symbol": per_symbol,
        "signals": signals,
        "picks": picks,
        "ensemble_features": features,
        "history": history,
        "history_summary": history_summary(history),
        "skip_log": skip_log,
        "risk_calls": risk_calls,
        "pattern_topics": {
            t: len(bus.topics.get(t, []))
            for t in ("sweep_events", "fvg_zones", "mss_events", "order_block_zones")
        },
        "stats": {
            "symbols": len(symbols),
            "published": len(signals),
            "distinct_symbols": sorted({s.get("symbol") for s in signals if s.get("symbol")}),
            "setup_types": sorted({s.get("setup_type") for s in signals if s.get("setup_type")}),
            "risk_calls": len(risk_calls),
            "skipped_inactive": sum(1 for row in per_symbol if row.get("skipped")),
            "live_trading": False,
        },
    }


async def run_paper_multi_scan(
    *,
    universe: list[str] | None = None,
    refresh_minutes: int = 15,
    cycles: int = 1,
    duration_s: float | None = None,
) -> dict[str, Any]:
    """CLI entry: 15-minute paper scan loop (default one cycle for tests)."""
    settings = get_settings()
    if settings.live_trading:
        raise RuntimeError("live_trading must stay false")
    provider = build_universe_provider(settings, override=universe)
    last: dict[str, Any] = {}
    n = max(1, int(cycles))
    for cycle in range(n):
        last = await scan_universe(provider=provider)
        last["cycle"] = cycle + 1
        last["refresh_minutes"] = refresh_minutes
        log.info(
            "paper scan cycle=%s published=%s symbols=%s live_trading=false",
            cycle + 1,
            last["stats"]["published"],
            last["stats"]["distinct_symbols"],
        )
        if duration_s is not None:
            break
        if cycle + 1 < n and refresh_minutes > 0:
            await asyncio.sleep(refresh_minutes * 60)
    return last
