"""Quant walk-forward defaults for setups 1–6. Env-tunable, no magic numbers."""

from __future__ import annotations

from dataclasses import dataclass

from sniper_data.config import Settings, get_settings


@dataclass(frozen=True)
class SetupParams:
    atr_period: int = 14
    stop_buffer_atr: float = 0.05

    # Setup 1 — sweep_reclaim
    s1_min_rr: float = 2.0
    s1_mss_swing_lookback: int = 5
    s1_max_bars_sweep_to_mss: int = 15
    s1_require_confirmed_sweep: bool = True
    s1_timeframes: tuple[str, ...] = ("5m", "15m")

    # Setup 2 — fvg_entry / ob_fvg
    s2_overlap_tol_atr: float = 0.05
    s2_pin_wick_ratio: float = 2.5
    s2_max_fvg_age_hours: float = 24.0
    s2_target_rr_fallback: float = 2.0

    # Setup 3 — po3_judas
    s3_accum_session: str = "asia"
    s3_kill_zone: str = "ny_am"
    s3_displacement_min_body_atr: float = 1.2
    s3_require_band_tag: bool = True
    s3_max_bars_sweep_to_displace: int = 6

    # Setup 4 — sd_extension_fade
    s4_vol_avg_period: int = 20
    s4_vol_frac: float = 0.8
    s4_min_rr: float = 1.5
    s4_min_rr_at_3s: float = 2.0
    s4_news_window_sec: int = 900
    s4_min_conviction: int = 60
    s4_timeframes: tuple[str, ...] = ("1m", "5m")
    s4_pin_wick_ratio: float = 2.5
    s4_band_tag_frac: float = 0.25

    # Setup 5 — vwap_pullback_cont
    s5_trend_bars: int = 20
    s5_timeframes: tuple[str, ...] = ("5m",)
    s5_first_touch_lookback_bars: int = 8
    s5_min_rr: float = 2.0
    s5_min_conviction: int = 60
    s5_pullback_tol_atr: float = 0.15
    s5_strong_body_frac: float = 0.5
    s5_pin_wick_ratio: float = 2.5
    s5_liquidity_lookback_bars: int = 24

    # Setup 6 — avwap_ob_confluence
    s6_min_rr: float = 2.0
    s6_min_conviction: int = 70
    s6_htf_timeframes: tuple[str, ...] = ("1h", "4h")
    s6_wire_timeframe: str = "15m"
    s6_swing_lookback: int = 2
    s6_daily_swing_lookback: int = 6
    s6_approach_tol_atr: float = 0.15
    s6_pin_wick_ratio: float = 2.5

    # Orchestrator
    dedupe_window_sec: int = 300
    min_conviction_to_validate: int = 60
    atr_regime_high_frac: float = 0.02
    conv_kill_zone_bonus: int = 10
    conv_volume_bonus: int = 10
    conv_multi_pattern_bonus: int = 10

    @property
    def dedupe_window_ms(self) -> int:
        return int(self.dedupe_window_sec) * 1000

    @property
    def s4_news_window_ms(self) -> int:
        return int(self.s4_news_window_sec) * 1000

    def min_conviction_for(self, setup_type: str) -> int:
        return {
            "sd_extension_fade": self.s4_min_conviction,
            "vwap_pullback_cont": self.s5_min_conviction,
            "avwap_ob_confluence": self.s6_min_conviction,
        }.get(setup_type, self.min_conviction_to_validate)


def _csv(value: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    items = tuple(x.strip() for x in value.split(",") if x.strip())
    return items or fallback


def load_setup_params(settings: Settings | None = None) -> SetupParams:
    s = settings or get_settings()
    return SetupParams(
        atr_period=s.setup_atr_period,
        stop_buffer_atr=s.setup_stop_buffer_atr,
        s1_min_rr=s.setup1_min_rr,
        s1_mss_swing_lookback=s.setup1_mss_swing_lookback,
        s1_max_bars_sweep_to_mss=s.setup1_max_bars_sweep_to_mss,
        s1_require_confirmed_sweep=s.setup1_require_confirmed_sweep,
        s1_timeframes=_csv(s.setup1_timeframes, ("5m", "15m")),
        s2_overlap_tol_atr=s.setup2_overlap_tol_atr,
        s2_pin_wick_ratio=s.setup2_pin_wick_ratio,
        s2_max_fvg_age_hours=s.setup2_max_fvg_age_hours,
        s2_target_rr_fallback=s.setup2_target_rr_fallback,
        s3_accum_session=s.setup3_accum_session,
        s3_kill_zone=s.setup3_kill_zone,
        s3_displacement_min_body_atr=s.setup3_displacement_min_body_atr,
        s3_require_band_tag=s.setup3_require_band_tag,
        s3_max_bars_sweep_to_displace=s.setup3_max_bars_sweep_to_displace,
        s4_vol_avg_period=s.setup4_vol_avg_period,
        s4_vol_frac=s.setup4_vol_frac,
        s4_min_rr=s.setup4_min_rr,
        s4_min_rr_at_3s=s.setup4_min_rr_at_3s,
        s4_news_window_sec=s.setup4_news_window_sec,
        s4_min_conviction=s.setup4_min_conviction,
        s4_timeframes=_csv(s.setup4_timeframes, ("1m", "5m")),
        s4_pin_wick_ratio=s.setup4_pin_wick_ratio,
        s4_band_tag_frac=s.setup4_band_tag_frac,
        s5_trend_bars=s.setup5_trend_bars,
        s5_timeframes=_csv(s.setup5_timeframes, ("5m",)),
        s5_first_touch_lookback_bars=s.setup5_first_touch_lookback_bars,
        s5_min_rr=s.setup5_min_rr,
        s5_min_conviction=s.setup5_min_conviction,
        s5_pullback_tol_atr=s.setup5_pullback_tol_atr,
        s5_strong_body_frac=s.setup5_strong_body_frac,
        s5_pin_wick_ratio=s.setup5_pin_wick_ratio,
        s5_liquidity_lookback_bars=s.setup5_liquidity_lookback_bars,
        s6_min_rr=s.setup6_min_rr,
        s6_min_conviction=s.setup6_min_conviction,
        s6_htf_timeframes=_csv(s.setup6_htf_timeframes, ("1h", "4h")),
        s6_wire_timeframe=s.setup6_wire_timeframe or "15m",
        s6_swing_lookback=s.setup6_swing_lookback,
        s6_daily_swing_lookback=s.setup6_daily_swing_lookback,
        s6_approach_tol_atr=s.setup6_approach_tol_atr,
        s6_pin_wick_ratio=s.setup6_pin_wick_ratio,
        dedupe_window_sec=s.setup_dedupe_window_sec,
        min_conviction_to_validate=s.setup_min_conviction_to_validate,
        atr_regime_high_frac=s.setup_atr_regime_high_frac,
        conv_kill_zone_bonus=s.setup_conv_kill_zone_bonus,
        conv_volume_bonus=s.setup_conv_volume_bonus,
        conv_multi_pattern_bonus=s.setup_conv_multi_pattern_bonus,
    )
