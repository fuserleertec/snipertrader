"""Paper pattern fixtures for **every** configured symbol.

Sweep / FVG / MSS / order-block / pullback / setup-signal generators used
to be demo-only and effectively BTCUSDT-shaped. The same pipeline now
emits per-symbol fixtures for ES, CL, GC, NQ, equities, and crypto using
existing ``asset_class`` + session rules.

``trigger_event_ids`` on ``SetupSignal`` links a setup to the sweep / FVG
/ MSS / OB that produced it. ``live_trading=false``.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Iterable

from sniper_data.history import seed_price
from sniper_data.models import (
    AssetClass,
    FVGZone,
    MssEvent,
    OrderBlock,
    SessionType,
    SetupSignal,
    SweepEvent,
    Timeframe,
)
from sniper_data.sessions import dt_from_ms, primary_session
from sniper_data.setups import SETUP_KEYS
from sniper_data.symbols import infer_asset_class, normalize_symbol
from sniper_data.zones import store_fvg, store_mss, store_ob, store_sweep

log = logging.getLogger(__name__)

SETUP_TOPIC = "setup_signals"
SWEEP_TOPIC = "sweep_events"
FVG_TOPIC = "fvg_zones"
MSS_TOPIC = "mss_events"
OB_TOPIC = "order_block_zones"


def _stable_int(symbol: str, salt: str, modulo: int) -> int:
    digest = hashlib.sha1(f"{symbol}:{salt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % modulo


def _session_type(symbol: str, now_ms: int, klass: AssetClass) -> SessionType:
    window = primary_session(klass, dt_from_ms(now_ms))
    if window is not None:
        return window.session_type
    return SessionType.RTH if klass is not AssetClass.CRYPTO else SessionType.LONDON


def fixtures_for(symbol: str, *, now_ms: int | None = None) -> dict[str, Any]:
    """Deterministic sweep / FVG / pullback / setup bundle for one symbol."""
    symbol = normalize_symbol(symbol)
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    klass = infer_asset_class(symbol)
    px, _ = seed_price(symbol)
    session = _session_type(symbol, now, klass)
    side_sweep = "sell" if _stable_int(symbol, "sweep", 2) == 0 else "buy"
    fvg_dir = "bearish" if side_sweep == "sell" else "bullish"
    mss_dir = "bearish" if side_sweep == "sell" else "bullish"
    setup_side = "short" if side_sweep == "sell" else "long"
    swept = round(px * (1.004 if side_sweep == "sell" else 0.996), 6)
    fvg_high = round(px * 1.002, 6)
    fvg_low = round(px * 0.998, 6)
    sweep_id = f"sw-{symbol}-1"
    fvg_id = f"fvg-{symbol}-1"
    mss_id = f"mss-{symbol}-1"
    ob_id = f"ob-{symbol}-1"
    pullback_id = f"sig-{symbol}-pullback"
    sweep_setup_id = f"sig-{symbol}-sweep"
    fvg_setup_id = f"sig-{symbol}-fvg"

    sweep = SweepEvent(
        id=sweep_id,
        symbol=symbol,
        asset_class=klass,
        side=side_sweep,
        swept_level=swept,
        reclaim=True,
        ts_ms=now - 90_000,
        volume_profile="aggressive",
        confirmed=True,
    )
    fvg = FVGZone(
        id=fvg_id,
        symbol=symbol,
        asset_class=klass,
        direction=fvg_dir,
        high=fvg_high,
        low=fvg_low,
        mitigated=False,
        created_ts_ms=now - 80_000,
    )
    mss = MssEvent(
        id=mss_id,
        symbol=symbol,
        asset_class=klass,
        ts_ms=now - 70_000,
        direction=mss_dir,
        broken_level=swept,
        swing_high=round(px * 1.006, 6),
        swing_low=round(px * 0.994, 6),
        trigger_sweep_id=sweep_id,
        trigger_sweep_side=side_sweep,
        timeframe="5m",
        confirmed=True,
    )
    ob = OrderBlock(
        id=ob_id,
        symbol=symbol,
        asset_class=klass,
        direction=fvg_dir,
        high=fvg_high,
        low=fvg_low,
        created_ts_ms=now - 60_000,
        timeframe=Timeframe.M5,
        origin_open=round(px, 6),
        origin_close=round(px * (0.999 if fvg_dir == "bearish" else 1.001), 6),
    )
    sweep_setup = SetupSignal(
        id=sweep_setup_id,
        symbol=symbol,
        asset_class=klass,
        setup_type=SETUP_KEYS[0],
        side=setup_side,
        confidence=0.72,
        ref_vwap=round(px, 6),
        ref_session=session.value,
        ts_ms=now - 50_000,
        trigger_event_ids=[sweep_id, mss_id],
    )
    fvg_setup = SetupSignal(
        id=fvg_setup_id,
        symbol=symbol,
        asset_class=klass,
        setup_type=SETUP_KEYS[1],
        side=setup_side,
        confidence=0.64,
        ref_vwap=round(px, 6),
        ref_session=session.value,
        ts_ms=now - 40_000,
        trigger_event_ids=[fvg_id, sweep_id],
    )
    pullback = SetupSignal(
        id=pullback_id,
        symbol=symbol,
        asset_class=klass,
        setup_type=SETUP_KEYS[4],  # 5_vwap_pullback_cont
        side=setup_side,
        confidence=0.58,
        ref_vwap=round(px, 6),
        ref_session=session.value,
        ts_ms=now - 30_000,
        trigger_event_ids=[sweep_id, fvg_id, ob_id],
    )
    return {
        "symbol": symbol,
        "asset_class": klass,
        "sweep": sweep,
        "fvg": fvg,
        "mss": mss,
        "ob": ob,
        "signals": [sweep_setup, fvg_setup, pullback],
    }


async def persist_fixtures(
    store,
    bundle: dict[str, Any],
    *,
    bus=None,
) -> dict[str, str]:
    from sniper_data.signals import store_setup

    keys = {
        "sweep": await store_sweep(store, bundle["sweep"]),
        "fvg": await store_fvg(store, bundle["fvg"]),
        "mss": await store_mss(store, bundle["mss"]),
        "ob": await store_ob(store, bundle["ob"]),
    }
    signal_keys = []
    for signal in bundle["signals"]:
        signal_keys.append(await store_setup(store, signal))
        if bus is not None:
            await bus.publish(SETUP_TOPIC, signal, key=signal.symbol)
    if bus is not None:
        await bus.publish(SWEEP_TOPIC, bundle["sweep"], key=bundle["symbol"])
        await bus.publish(FVG_TOPIC, bundle["fvg"], key=bundle["symbol"])
        await bus.publish(MSS_TOPIC, bundle["mss"], key=bundle["symbol"])
        await bus.publish(OB_TOPIC, bundle["ob"], key=bundle["symbol"])
    keys["signals"] = ",".join(signal_keys)
    return keys


async def seed_patterns(
    store,
    symbols: Iterable[str],
    *,
    bus=None,
    now_ms: int | None = None,
) -> dict[str, int]:
    symbols = [normalize_symbol(s) for s in symbols]
    n_signals = 0
    for symbol in symbols:
        bundle = fixtures_for(symbol, now_ms=now_ms)
        await persist_fixtures(store, bundle, bus=bus)
        n_signals += len(bundle["signals"])
    log.info(
        "seeded pattern fixtures for %s symbols (%s setup signals, paper)",
        len(symbols),
        n_signals,
    )
    return {"symbols": len(symbols), "signals": n_signals}
