"""Deterministic worlds for setups 1–3 and the orchestrator."""

from __future__ import annotations

from sniper_data.models import (
    AnchorType,
    FVGZone,
    KillZoneEvent,
    MssEvent,
    OHLCVBar,
    OrderBlock,
    SessionLevels,
    SessionType,
    SweepEvent,
    Timeframe,
    VolumeNode,
    VolumeProfile,
    VWAPValues,
)
from sniper_data.pattern_detection.fixtures import SYM, T0, BAR_MS, KLASS, bar

S1_TF = Timeframe.M5
from sniper_data.zones import store_fvg, store_ob, store_sweep

VWAP_SESSION = VWAPValues(
    symbol=SYM,
    asset_class=KLASS,
    anchor_type=AnchorType.SESSION,
    session_type=SessionType.LONDON,
    anchor_start_ms=T0 - 3_600_000,
    vwap=100.0,
    sigma=2.0,
    band_m3=94.0,
    band_m2=96.0,
    band_m1=98.0,
    band_p1=102.0,
    band_p2=104.0,
    band_p3=106.0,
    cum_volume=10_000.0,
    n_obs=200,
    updated_ts_ms=T0,
)


def session_vwap(**overrides) -> VWAPValues:
    return VWAP_SESSION.model_copy(update=overrides)


def atr_warmup(n: int = 14, *, start: int = 0, timeframe: Timeframe = S1_TF) -> list[OHLCVBar]:
    """Quiet range so ATR(14) is defined before the setup sequence."""
    return [bar(start + i, 100.0, 100.8, 99.2, 100.1, 50.0, timeframe=timeframe) for i in range(n)]


def asia_session(*, high: float = 104.0, low: float = 90.0) -> SessionLevels:
    return SessionLevels(
        symbol=SYM,
        asset_class=KLASS,
        session_type=SessionType.ASIA,
        session_start_ms=T0 - 8 * 3_600_000,
        session_end_ms=T0 - 1 * 3_600_000,
        open=100.0,
        high=high,
        low=low,
        close=101.0,
        volume=5_000.0,
        updated_ts_ms=T0,
    )


def ny_am_kill_zone(*, active: bool = True) -> KillZoneEvent:
    return KillZoneEvent(
        symbol=SYM,
        kill_zone=SessionType.NY_AM,
        start_time=T0,
        end_time=T0 + 90 * 60_000,
        active=active,
        asset_class=KLASS,
    )


def volume_profile_at(poc: float = 100.0) -> VolumeProfile:
    return VolumeProfile(
        symbol=SYM,
        session_type=SessionType.LONDON,
        high_volume_nodes=[VolumeNode(price=poc, volume=800.0)],
        low_volume_nodes=[VolumeNode(price=poc - 4, volume=20.0)],
        poc=poc,
        timestamp=T0,
    )


def confirmed_buy_sweep(*, swept: float = 99.2, ts_ms: int = T0) -> SweepEvent:
    return SweepEvent(
        id="swp-buy-low",
        symbol=SYM,
        asset_class=KLASS,
        side="buy",
        swept_level=swept,
        reclaim=True,
        ts_ms=ts_ms,
        volume_profile="aggressive",
        delta_divergence=True,
        time_to_reclaim_ms=60_000,
        confirmed=True,
    )


def confirmed_sell_sweep(*, swept: float = 100.8, ts_ms: int = T0) -> SweepEvent:
    return SweepEvent(
        id="swp-sell-high",
        symbol=SYM,
        asset_class=KLASS,
        side="sell",
        swept_level=swept,
        reclaim=True,
        ts_ms=ts_ms,
        volume_profile="aggressive",
        delta_divergence=True,
        time_to_reclaim_ms=60_000,
        confirmed=True,
    )


def bullish_mss_after_low(*, ts_ms: int | None = None) -> MssEvent:
    return MssEvent(
        id="mss-reclaim-long",
        symbol=SYM,
        asset_class=KLASS,
        ts_ms=ts_ms if ts_ms is not None else T0 + 6 * BAR_MS,
        direction="bullish",
        broken_level=99.8,
        swing_high=100.6,
        swing_low=99.1,
        trigger_sweep_id="swp-buy-low",
        trigger_sweep_side="buy",
        timeframe="5m",
        confirmed=True,
    )


def setup1_long_bars(*, start: int = 0) -> list[OHLCVBar]:
    """Establish a LH near 99.8, then break it with a close above session VWAP."""
    seq = [
        (100.0, 100.2, 99.6, 99.7),
        (99.7, 99.85, 99.3, 99.4),
        (99.4, 99.8, 99.25, 99.55),  # LH candidate ~99.8
        (99.55, 99.7, 99.2, 99.35),
        (99.35, 99.6, 99.15, 99.4),
        (99.4, 100.7, 99.3, 100.5),  # break LH, close above VWAP 100
    ]
    return [bar(start + i, o, h, l, c, 80.0, timeframe=S1_TF) for i, (o, h, l, c) in enumerate(seq)]


def setup1_short_bars(*, start: int = 0) -> list[OHLCVBar]:
    seq = [
        (100.0, 100.4, 99.8, 100.3),
        (100.3, 100.7, 100.15, 100.6),
        (100.6, 100.75, 100.2, 100.4),  # HL candidate ~100.2
        (100.4, 100.65, 100.25, 100.5),
        (100.5, 100.7, 100.3, 100.55),
        (100.55, 100.7, 99.3, 99.5),  # break HL, close below VWAP
    ]
    return [bar(start + i, o, h, l, c, 80.0, timeframe=S1_TF) for i, (o, h, l, c) in enumerate(seq)]


def setup1_tight_rr_vwap() -> VWAPValues:
    """±1/2σ too close to satisfy 1:2 after a 1.3-point stop."""
    return session_vwap(sigma=0.2, band_m1=99.8, band_m2=99.6, band_p1=100.2, band_p2=100.4, band_m3=99.4, band_p3=100.6)


def bullish_fvg(*, low: float = 99.6, high: float = 100.4) -> FVGZone:
    return FVGZone(
        id="fvg-bull-vwap",
        symbol=SYM,
        asset_class=KLASS,
        direction="bullish",
        high=high,
        low=low,
        mitigated=False,
        created_ts_ms=T0,
        ttl_seconds=172800,
    )


def bearish_ob_overlap() -> OrderBlock:
    return OrderBlock(
        id="ob-bull-overlap",
        symbol=SYM,
        asset_class=KLASS,
        direction="bullish",
        high=100.5,
        low=99.5,
        created_ts_ms=T0,
        mitigated=False,
        timeframe=Timeframe.M1,
    )


def setup2_retrace_bars() -> list[OHLCVBar]:
    """Structure high, then retrace into FVG and print a bullish engulfing."""
    return [
        bar(0, 99.0, 103.5, 98.8, 103.0, 70.0),  # structure high
        bar(1, 103.0, 103.2, 101.0, 101.2, 40.0),
        bar(2, 101.2, 101.3, 100.1, 100.2, 35.0),
        bar(3, 100.2, 100.3, 99.7, 99.8, 30.0),  # into FVG, bearish
        bar(4, 99.75, 100.6, 99.65, 100.45, 55.0),  # bullish engulfing
    ]


def setup3_judas_bars(*, start: int = 0) -> list[OHLCVBar]:
    """Sweep Asia high at +2σ (104), then displace back toward VWAP 100."""
    return [
        bar(start + 0, 102.4, 103.2, 102.0, 102.8, 40.0, timeframe=S1_TF),
        bar(start + 1, 102.8, 104.4, 102.6, 104.1, 90.0, timeframe=S1_TF),  # tags +2σ
        bar(start + 2, 104.0, 104.1, 100.4, 100.8, 120.0, timeframe=S1_TF),  # displacement
    ]


def asia_high_sweep() -> SweepEvent:
    return SweepEvent(
        id="swp-asia-high",
        symbol=SYM,
        asset_class=KLASS,
        side="sell",
        swept_level=104.0,
        reclaim=True,
        ts_ms=T0 + BAR_MS,
        volume_profile="aggressive",
        confirmed=True,
    )


async def seed_common(
    store,
    *,
    vwap: VWAPValues | None = None,
    fvg: bool = False,
    ob: bool = False,
    sweep: bool = False,
) -> None:
    from sniper_data.kill_zones import redis_kill_zone_key
    from sniper_data.sessions import redis_session_key
    from sniper_data.volume_profile import redis_volume_profile_key
    from sniper_data.vwap import redis_vwap_key

    snap = vwap or VWAP_SESSION
    await store.set(redis_vwap_key(SYM, "session"), snap)
    asia = asia_session()
    await store.set(redis_session_key(SYM, "asia"), asia)
    await store.set(redis_volume_profile_key(SYM, "london"), volume_profile_at(100.0))
    await store.set(redis_kill_zone_key(SYM), ny_am_kill_zone())
    if sweep:
        await store_sweep(store, confirmed_buy_sweep())
    if fvg:
        await store_fvg(store, bullish_fvg())
    if ob:
        await store_ob(store, bearish_ob_overlap())
