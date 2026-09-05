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
}

SETUP_NAME_TO_INDEX: dict[str, int] = {v: k for k, v in SETUP_INDEX.items()}

# Conviction is reporting-only (not sent on POST /risk/validate).
CONVICTION_WEIGHTS: dict[str, int] = {
    "confluence_count": 40,
    "volume_confirm": 30,
    "kill_zone_align": 30,
}

HARD_RR_FLOOR = 1.2

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
    accumulation_session: str = "asia"
    kill_zone: str = "asset_map"
    displacement_min_body_atr: float = 1.2
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

    def resolved_kill_zone(self, asset_class: AssetClass | str) -> str:
        if self.kill_zone != "asset_map":
            return self.kill_zone
        ac = AssetClass(asset_class)
        if ac is AssetClass.CRYPTO:
            return "either"
        return "ny_am"


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
            raise ValueError(f"unknown setup id {n!r}; expected 1, 2, or 3")
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
    raise ValueError(f"no grid for {setup_type!r}")


# Backward-compatible name used by older walk-forward imports.
PARAM_GRID = sweep_reclaim_grid(mode="core")
