"""Locked ML tunable ranges for Setups 1–3 (Phase 2 walk-forward).

Defaults are the bold values from ML Researchers. Grids list every allowed
value. ``session_vwap_anchor`` is **session** only (not weekly/rolling).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from itertools import product
from typing import Any, Iterator, Literal

from sniper_quant.models import AssetClass

SETUP_INDEX: dict[int, str] = {
    1: "sweep_reclaim",
    2: "fvg_entry",
    3: "po3_judas",
    4: "sd_extension_fade",
    5: "vwap_pullback_cont",
    6: "avwap_ob_confluence",
}

SETUP_NAME_TO_INDEX: dict[str, int] = {v: k for k, v in SETUP_INDEX.items()}

# Conviction is reporting-only (not sent on POST /risk/validate).
CONVICTION_WEIGHTS: dict[str, int] = {
    "confluence_count": 40,
    "volume_confirm": 30,
    "kill_zone_align": 30,
}

HARD_RR_FLOOR = 1.2

# Quant field → ML PR #7 SetupParams / SETUP_* env (https://github.com/fuserleertec/snipertrader/pull/7)
ML_PR7_FIELD_MAP: tuple[tuple[str, str, str], ...] = (
    ("stop_buffer_atr", "stop_buffer_atr", "SETUP_STOP_BUFFER_ATR"),
    ("min_rr", "s1_min_rr", "SETUP1_MIN_RR"),
    ("mss_swing_lookback", "s1_mss_swing_lookback", "SETUP1_MSS_SWING_LOOKBACK"),
    ("max_bars_sweep_to_mss", "s1_max_bars_sweep_to_mss", "SETUP1_MAX_BARS_SWEEP_TO_MSS"),
    ("require_confirmed_sweep", "s1_require_confirmed_sweep", "SETUP1_REQUIRE_CONFIRMED_SWEEP"),
    ("timeframe", "s1_timeframes", "SETUP1_TIMEFRAMES"),
    ("fvg_overlap_tol_atr", "s2_overlap_tol_atr", "SETUP2_OVERLAP_TOL_ATR"),
    ("pin_wick_ratio", "s2_pin_wick_ratio", "SETUP2_PIN_WICK_RATIO"),
    ("max_fvg_age_hours", "s2_max_fvg_age_hours", "SETUP2_MAX_FVG_AGE_HOURS"),
    ("target_rr_fallback", "s2_target_rr_fallback", "SETUP2_TARGET_RR_FALLBACK"),
    ("accumulation_session", "s3_accum_session", "SETUP3_ACCUM_SESSION"),
    ("kill_zone", "s3_kill_zone", "SETUP3_KILL_ZONE"),
    ("displacement_min_body_atr", "s3_displacement_min_body_atr", "SETUP3_DISPLACEMENT_MIN_BODY_ATR"),
    ("require_band_tag", "s3_require_band_tag", "SETUP3_REQUIRE_BAND_TAG"),
    ("max_bars_sweep_to_displace", "s3_max_bars_sweep_to_displace", "SETUP3_MAX_BARS_SWEEP_TO_DISPLACE"),
    ("dedupe_window_sec", "dedupe_window_sec", "SETUP_DEDUPE_WINDOW_SEC"),
    ("min_conviction", "min_conviction_to_validate", "SETUP_MIN_CONVICTION_TO_VALIDATE"),
    ("atr_period", "atr_period", "SETUP_ATR_PERIOD"),
)

VwapBand = Literal["1", "2", "auto"]
ConfluenceMode = Literal["vwap_touch", "hvn_overlap", "vwap_or_hvn", "vwap_and_hvn"]
Confirmation = Literal["engulfing", "pin_bar", "either"]
EntryMode = Literal["zone_boundary", "confirm_close"]
TargetMode = Literal["prior_swing", "1.5R", "2R"]
BandTag = Literal["1s", "2s", "either", "none"]
KillZone = Literal["ny_am", "london", "either", "asset_map"]
AccumSession = Literal["asia", "globex"]


@dataclass(frozen=True)
class DetectorParams:
    """One point in the locked ML grid. Defaults = ML bold values."""

    # --- Setup 1 sweep_reclaim ---
    stop_buffer_atr: float = 0.05
    stop_buffer_ticks: int = 1
    vwap_target_band: str = "auto"
    min_rr: float = 2.0
    mss_swing_lookback: int = 5
    max_bars_sweep_to_mss: int = 15
    require_confirmed_sweep: bool = True
    session_vwap_anchor: str = "session"
    timeframe: str = "5m"

    # --- Setup 2 fvg_entry ---
    confluence_mode: str = "vwap_or_hvn"
    fvg_overlap_tol_atr: float = 0.05
    confirmation: str = "either"
    pin_wick_ratio: float = 2.5
    entry_mode: str = "confirm_close"
    fvg_stop_buffer_atr: float = 0.05
    target_mode: str = "prior_swing"
    max_fvg_age_hours: int = 24

    # --- Setup 3 po3_judas ---
    # PR #7 SetupParams.s3_kill_zone default is ``ny_am``. On crypto their
    # detector also accepts London (same as our ``either``).
    accumulation_session: str = "asia"
    kill_zone: str = "ny_am"
    displacement_min_body_atr: float = 1.2
    # Walk-forward encoding of PR #7 bool ``s3_require_band_tag=True``.
    require_band_tag: str = "either"
    po3_stop_buffer_atr: float = 0.05
    partial_mid: bool = False
    max_bars_sweep_to_displace: int = 6

    # --- Orchestrator ---
    dedupe_window_sec: int = 300
    min_conviction: int = 60

    atr_period: int = 14
    std_window: int = 20
    tick_size: float = 0.25
    # PR #7 SETUP2_TARGET_RR_FALLBACK — used when target_mode is prior_swing.
    target_rr_fallback: float = 2.0

    # --- Setup 4 sd_extension_fade ---
    # band_trigger either = ≥2σ. Stop is always beyond the 3σ band.
    s4_band_trigger: str = "either"
    s4_vol_max_frac: float = 0.8
    s4_confirm: str = "either"
    s4_stop_buffer_atr: float = 0.05
    s4_min_rr: float = 1.5
    news_skip_minutes: int = 15

    # --- Setup 5 vwap_pullback_cont ---
    s5_trend_lookback_bars: int = 20
    s5_pullback_level: str = "either"
    s5_require_ob_or_fvg: bool = True
    s5_first_touch_window_bars: int = 5
    s5_stop_buffer_atr: float = 0.05
    s5_min_rr: float = 2.0

    # --- Setup 6 avwap_ob_confluence ---
    # HTF is synthesized from 5m (12≈1h, 48≈4h, calendar day≈1d).
    s6_ob_timeframe: str = "4h"
    s6_approach_tol_atr: float = 0.05
    s6_confirm: str = "rejection"
    s6_confirm_tf: str = "1h"
    s6_stop_buffer_atr: float = 0.05
    s6_min_rr: float = 2.0
    s6_min_conviction: int = 70

    def resolved_kill_zone(self, asset_class: AssetClass | str) -> str:
        """Match PR #7 ``manipulation_zones``: ``ny_am`` on crypto also allows London."""
        ac = AssetClass(asset_class)
        if self.kill_zone in {"asset_map", "ny_am"} and ac is AssetClass.CRYPTO:
            return "either"
        if self.kill_zone == "asset_map":
            return "ny_am"
        return self.kill_zone

    @property
    def min_conviction_to_validate(self) -> int:
        """PR #7 alias for ``min_conviction``."""
        return self.min_conviction

    @property
    def s3_require_band_tag(self) -> bool:
        """PR #7 bool: True unless walk-forward set ``require_band_tag='none'``."""
        return self.require_band_tag != "none"

    def to_ml_setup_params(self) -> dict[str, Any]:
        """Names as published on ML PR #7 ``SetupParams`` / ``SETUP_*`` env."""
        return {
            "atr_period": self.atr_period,
            "stop_buffer_atr": self.stop_buffer_atr,
            "s1_min_rr": self.min_rr,
            "s1_mss_swing_lookback": self.mss_swing_lookback,
            "s1_max_bars_sweep_to_mss": self.max_bars_sweep_to_mss,
            "s1_require_confirmed_sweep": self.require_confirmed_sweep,
            "s1_timeframes": ("5m", "15m"),
            "s2_overlap_tol_atr": self.fvg_overlap_tol_atr,
            "s2_pin_wick_ratio": self.pin_wick_ratio,
            "s2_max_fvg_age_hours": float(self.max_fvg_age_hours),
            "s2_target_rr_fallback": self.target_rr_fallback,
            "s3_accum_session": self.accumulation_session,
            "s3_kill_zone": "ny_am" if self.kill_zone == "asset_map" else self.kill_zone,
            "s3_displacement_min_body_atr": self.displacement_min_body_atr,
            "s3_require_band_tag": self.s3_require_band_tag,
            "s3_max_bars_sweep_to_displace": self.max_bars_sweep_to_displace,
            "dedupe_window_sec": self.dedupe_window_sec,
            "min_conviction_to_validate": self.min_conviction,
        }


DEFAULT_PARAMS = DetectorParams()

# Locked grids (exact ML lists).
GRID_STOP_BUFFER_ATR: tuple[float, ...] = (0.0, 0.05, 0.1)
GRID_STOP_BUFFER_TICKS: tuple[int, ...] = (0, 1, 2)
GRID_VWAP_TARGET_BAND: tuple[str, ...] = ("1", "2")
GRID_MIN_RR: tuple[float, ...] = (1.5, 2.0)
GRID_MSS_LOOKBACK: tuple[int, ...] = (3, 5, 8)
GRID_MAX_BARS_SWEEP_MSS: tuple[int, ...] = (5, 15, 30)
GRID_REQUIRE_CONFIRMED: tuple[bool, ...] = (True, False)
GRID_TIMEFRAMES_S1: tuple[str, ...] = ("5m", "15m")

GRID_CONFLUENCE: tuple[str, ...] = ("vwap_touch", "hvn_overlap", "vwap_or_hvn", "vwap_and_hvn")
GRID_FVG_OVERLAP_TOL: tuple[float, ...] = (0.0, 0.05, 0.1)
GRID_CONFIRMATION: tuple[str, ...] = ("engulfing", "pin_bar", "either")
GRID_PIN_WICK: tuple[float, ...] = (2.0, 2.5, 3.0)
GRID_ENTRY_MODE: tuple[str, ...] = ("zone_boundary", "confirm_close")
GRID_FVG_STOP_BUFFER: tuple[float, ...] = (0.0, 0.05)
GRID_TARGET_MODE: tuple[str, ...] = ("prior_swing", "1.5R", "2R")
GRID_FVG_AGE: tuple[int, ...] = (6, 24, 48)
GRID_TIMEFRAMES_S2: tuple[str, ...] = ("1m", "5m", "15m")

GRID_ACCUM: tuple[str, ...] = ("asia", "globex")
GRID_KILL: tuple[str, ...] = ("ny_am", "london", "either")
GRID_DISP_ATR: tuple[float, ...] = (0.8, 1.2, 1.5)
GRID_BAND_TAG: tuple[str, ...] = ("1s", "2s", "either", "none")
GRID_PO3_STOP: tuple[float, ...] = (0.0, 0.05)
GRID_PARTIAL_MID: tuple[bool, ...] = (False, True)
GRID_MAX_BARS_DISPLACE: tuple[int, ...] = (3, 6, 12)

GRID_DEDUPE: tuple[int, ...] = (180, 300, 600)
GRID_MIN_CONVICTION: tuple[int, ...] = (50, 60, 70)


def parse_setup_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if part in SETUP_NAME_TO_INDEX:
            ids.append(SETUP_NAME_TO_INDEX[part])
            continue
        n = int(part)
        if n not in SETUP_INDEX:
            raise ValueError(f"unknown setup id {n!r}; expected 1–6")
        ids.append(n)
    if not ids:
        raise ValueError("no setups specified")
    return ids


def with_params(base: DetectorParams | None = None, **overrides: Any) -> DetectorParams:
    return replace(base or DEFAULT_PARAMS, **overrides)


def params_as_dict(params: DetectorParams) -> dict[str, Any]:
    return asdict(params)


def setup_fields(setup_type: str) -> tuple[str, ...]:
    if setup_type == "sweep_reclaim":
        return (
            "stop_buffer_atr",
            "vwap_target_band",
            "min_rr",
            "mss_swing_lookback",
            "max_bars_sweep_to_mss",
            "require_confirmed_sweep",
        )
    if setup_type == "fvg_entry":
        return (
            "confluence_mode",
            "fvg_overlap_tol_atr",
            "confirmation",
            "pin_wick_ratio",
            "entry_mode",
            "fvg_stop_buffer_atr",
            "target_mode",
            "max_fvg_age_hours",
        )
    if setup_type == "po3_judas":
        return (
            "accumulation_session",
            "kill_zone",
            "displacement_min_body_atr",
            "require_band_tag",
            "po3_stop_buffer_atr",
            "partial_mid",
            "max_bars_sweep_to_displace",
        )
    if setup_type == "sd_extension_fade":
        return (
            "s4_band_trigger",
            "s4_vol_max_frac",
            "s4_confirm",
            "pin_wick_ratio",
            "s4_stop_buffer_atr",
            "s4_min_rr",
        )
    if setup_type == "vwap_pullback_cont":
        return (
            "s5_trend_lookback_bars",
            "s5_pullback_level",
            "s5_require_ob_or_fvg",
            "s5_first_touch_window_bars",
            "s5_stop_buffer_atr",
            "s5_min_rr",
        )
    if setup_type == "avwap_ob_confluence":
        return (
            "s6_ob_timeframe",
            "s6_approach_tol_atr",
            "s6_confirm",
            "s6_confirm_tf",
            "s6_stop_buffer_atr",
            "s6_min_rr",
        )
    return ()


def _iter_product(overrides: list[dict[str, Any]]) -> Iterator[DetectorParams]:
    for kw in overrides:
        yield with_params(**kw)


def sweep_reclaim_grid(*, mode: str = "full") -> tuple[DetectorParams, ...]:
    if mode == "baseline":
        return (DEFAULT_PARAMS,)
    if mode == "core":
        keys = product(GRID_STOP_BUFFER_ATR, GRID_VWAP_TARGET_BAND, GRID_MIN_RR, GRID_MSS_LOOKBACK)
        return tuple(
            with_params(
                stop_buffer_atr=sb,
                vwap_target_band=band,
                min_rr=rr,
                mss_swing_lookback=lb,
            )
            for sb, band, rr, lb in keys
        )
    rows = [
        dict(
            stop_buffer_atr=sb,
            vwap_target_band=band,
            min_rr=rr,
            mss_swing_lookback=lb,
            max_bars_sweep_to_mss=mx,
            require_confirmed_sweep=conf,
        )
        for sb, band, rr, lb, mx, conf in product(
            GRID_STOP_BUFFER_ATR,
            GRID_VWAP_TARGET_BAND,
            GRID_MIN_RR,
            GRID_MSS_LOOKBACK,
            GRID_MAX_BARS_SWEEP_MSS,
            GRID_REQUIRE_CONFIRMED,
        )
    ]
    return tuple(_iter_product(rows))


def fvg_entry_grid(*, mode: str = "full") -> tuple[DetectorParams, ...]:
    if mode == "baseline":
        return (DEFAULT_PARAMS,)
    if mode == "core":
        keys = product(GRID_CONFLUENCE, GRID_CONFIRMATION, GRID_ENTRY_MODE, GRID_TARGET_MODE)
        return tuple(
            with_params(
                confluence_mode=cm,
                confirmation=cf,
                entry_mode=em,
                target_mode=tm,
            )
            for cm, cf, em, tm in keys
        )
    # Full cartesian of Setup 2 knobs (pin_wick only varies with pin/either).
    rows = []
    for cm, tol, cf, em, sb, tm, age in product(
        GRID_CONFLUENCE,
        GRID_FVG_OVERLAP_TOL,
        GRID_CONFIRMATION,
        GRID_ENTRY_MODE,
        GRID_FVG_STOP_BUFFER,
        GRID_TARGET_MODE,
        GRID_FVG_AGE,
    ):
        wick_vals = GRID_PIN_WICK if cf in {"pin_bar", "either"} else (DEFAULT_PARAMS.pin_wick_ratio,)
        for wick in wick_vals:
            rows.append(
                dict(
                    confluence_mode=cm,
                    fvg_overlap_tol_atr=tol,
                    confirmation=cf,
                    pin_wick_ratio=wick,
                    entry_mode=em,
                    fvg_stop_buffer_atr=sb,
                    target_mode=tm,
                    max_fvg_age_hours=age,
                )
            )
    return tuple(_iter_product(rows))


def po3_judas_grid(*, mode: str = "full") -> tuple[DetectorParams, ...]:
    if mode == "baseline":
        return (DEFAULT_PARAMS,)
    if mode == "core":
        keys = product(GRID_ACCUM, GRID_DISP_ATR, GRID_BAND_TAG, GRID_MAX_BARS_DISPLACE)
        return tuple(
            with_params(
                accumulation_session=acc,
                displacement_min_body_atr=disp,
                require_band_tag=tag,
                max_bars_sweep_to_displace=mx,
            )
            for acc, disp, tag, mx in keys
        )
    rows = [
        dict(
            accumulation_session=acc,
            kill_zone=kz,
            displacement_min_body_atr=disp,
            require_band_tag=tag,
            po3_stop_buffer_atr=sb,
            partial_mid=partial,
            max_bars_sweep_to_displace=mx,
        )
        for acc, kz, disp, tag, sb, partial, mx in product(
            GRID_ACCUM,
            GRID_KILL,
            GRID_DISP_ATR,
            GRID_BAND_TAG,
            GRID_PO3_STOP,
            GRID_PARTIAL_MID,
            GRID_MAX_BARS_DISPLACE,
        )
    ]
    return tuple(_iter_product(rows))


GRID_S4_BAND: tuple[str, ...] = ("2s", "3s", "either")
GRID_S4_VOL: tuple[float, ...] = (0.7, 0.8, 0.9)
GRID_S4_CONFIRM: tuple[str, ...] = ("engulfing", "pin", "mss_1m5m", "either")
GRID_S4_STOP: tuple[float, ...] = (0.0, 0.05)
GRID_S4_MIN_RR: tuple[float, ...] = (1.5, 2.0)
GRID_S5_LOOKBACK: tuple[int, ...] = (10, 20, 30)
GRID_S5_PULLBACK: tuple[str, ...] = ("vwap", "band_1s", "either")
GRID_S5_TOUCH: tuple[int, ...] = (3, 5, 8)
GRID_S6_OB_TF: tuple[str, ...] = ("4h", "1d")
GRID_S6_APPROACH: tuple[float, ...] = (0.05, 0.1)
GRID_S6_CONFIRM: tuple[str, ...] = ("rejection", "mss")
GRID_S6_CONFIRM_TF: tuple[str, ...] = ("1h", "4h")


def sd_extension_fade_grid(*, mode: str = "full") -> tuple[DetectorParams, ...]:
    if mode == "baseline":
        return (DEFAULT_PARAMS,)
    bands = GRID_S4_BAND if mode == "full" else ("either", "2s")
    vols = GRID_S4_VOL if mode == "full" else (0.8, 0.9)
    confirms = GRID_S4_CONFIRM if mode == "full" else ("either", "engulfing")
    stops = GRID_S4_STOP
    rrs = GRID_S4_MIN_RR if mode == "full" else (1.5,)
    wicks = GRID_PIN_WICK if mode == "full" else (2.5,)
    return tuple(
        with_params(
            s4_band_trigger=band,
            s4_vol_max_frac=vol,
            s4_confirm=cf,
            pin_wick_ratio=wick,
            s4_stop_buffer_atr=sb,
            s4_min_rr=rr,
        )
        for band, vol, cf, wick, sb, rr in product(bands, vols, confirms, wicks, stops, rrs)
    )


def vwap_pullback_cont_grid(*, mode: str = "full") -> tuple[DetectorParams, ...]:
    if mode == "baseline":
        return (DEFAULT_PARAMS,)
    looks = GRID_S5_LOOKBACK if mode == "full" else (10, 20)
    levels = GRID_S5_PULLBACK if mode == "full" else ("either", "vwap")
    windows = GRID_S5_TOUCH if mode == "full" else (5,)
    return tuple(
        with_params(
            s5_trend_lookback_bars=lb,
            s5_pullback_level=lvl,
            s5_first_touch_window_bars=win,
            s5_require_ob_or_fvg=True,
            s5_stop_buffer_atr=0.05,
            s5_min_rr=2.0,
        )
        for lb, lvl, win in product(looks, levels, windows)
    )


def avwap_ob_confluence_grid(*, mode: str = "full") -> tuple[DetectorParams, ...]:
    if mode == "baseline":
        return (DEFAULT_PARAMS,)
    tfs = GRID_S6_OB_TF
    tols = GRID_S6_APPROACH if mode == "full" else (0.05, 0.1)
    confirms = GRID_S6_CONFIRM
    c_tfs = GRID_S6_CONFIRM_TF if mode == "full" else ("1h",)
    return tuple(
        with_params(
            s6_ob_timeframe=tf,
            s6_approach_tol_atr=tol,
            s6_confirm=cf,
            s6_confirm_tf=ctf,
            s6_stop_buffer_atr=0.05,
            s6_min_rr=2.0,
            s6_min_conviction=70,
        )
        for tf, tol, cf, ctf in product(tfs, tols, confirms, c_tfs)
    )


def orchestrator_grid() -> tuple[DetectorParams, ...]:
    return tuple(
        with_params(dedupe_window_sec=d, min_conviction=c)
        for d, c in product(GRID_DEDUPE, GRID_MIN_CONVICTION)
    )


def grid_for(setup_type: str, *, mode: str = "full") -> tuple[DetectorParams, ...]:
    if setup_type == "sweep_reclaim":
        return sweep_reclaim_grid(mode=mode)
    if setup_type == "fvg_entry":
        return fvg_entry_grid(mode=mode)
    if setup_type == "po3_judas":
        return po3_judas_grid(mode=mode)
    if setup_type == "sd_extension_fade":
        return sd_extension_fade_grid(mode=mode)
    if setup_type == "vwap_pullback_cont":
        return vwap_pullback_cont_grid(mode=mode)
    if setup_type == "avwap_ob_confluence":
        return avwap_ob_confluence_grid(mode=mode)
    raise ValueError(f"no grid for {setup_type!r}")


# Backward-compatible name used by older walk-forward imports.
PARAM_GRID = sweep_reclaim_grid(mode="core")
