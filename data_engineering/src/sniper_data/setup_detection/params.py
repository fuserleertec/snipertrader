"""Quant walk-forward defaults for setups 1–3. Env-tunable, no magic numbers."""

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

    # Orchestrator
    dedupe_window_sec: int = 300
    min_conviction_to_validate: int = 60

    @property
    def dedupe_window_ms(self) -> int:
        return int(self.dedupe_window_sec) * 1000


def load_setup_params(settings: Settings | None = None) -> SetupParams:
    s = settings or get_settings()
    tfs = tuple(x.strip() for x in s.setup1_timeframes.split(",") if x.strip())
    return SetupParams(
        atr_period=s.setup_atr_period,
        stop_buffer_atr=s.setup_stop_buffer_atr,
        s1_min_rr=s.setup1_min_rr,
        s1_mss_swing_lookback=s.setup1_mss_swing_lookback,
        s1_max_bars_sweep_to_mss=s.setup1_max_bars_sweep_to_mss,
        s1_require_confirmed_sweep=s.setup1_require_confirmed_sweep,
        s1_timeframes=tfs or ("5m", "15m"),
        s2_overlap_tol_atr=s.setup2_overlap_tol_atr,
        s2_pin_wick_ratio=s.setup2_pin_wick_ratio,
        s2_max_fvg_age_hours=s.setup2_max_fvg_age_hours,
        s2_target_rr_fallback=s.setup2_target_rr_fallback,
        s3_accum_session=s.setup3_accum_session,
        s3_kill_zone=s.setup3_kill_zone,
        s3_displacement_min_body_atr=s.setup3_displacement_min_body_atr,
        s3_require_band_tag=s.setup3_require_band_tag,
        s3_max_bars_sweep_to_displace=s.setup3_max_bars_sweep_to_displace,
        dedupe_window_sec=s.setup_dedupe_window_sec,
        min_conviction_to_validate=s.setup_min_conviction_to_validate,
    )
