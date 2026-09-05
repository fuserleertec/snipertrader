import { ROLLING_VWAP_PERIODS } from "./constants";
import { mondayAnchorMs, windowContaining } from "./sessions";
import type { AnchorType, AssetClass, OHLCVBar, SessionType, VWAPValues } from "./types";

function typical(bar: OHLCVBar): number {
  return (bar.high + bar.low + bar.close) / 3;
}

export function computeVwap(
  bars: OHLCVBar[],
  opts: {
    symbol: string;
    asset_class: AssetClass;
    anchor_type: AnchorType;
    session_type: SessionType | null;
    now_ms: number;
  },
): VWAPValues | null {
  if (!bars.length) return null;

  let slice = bars;
  let anchor_start_ms = bars[0].open_ts_ms;
  let lookback_periods: number | null = null;
  let session_type = opts.session_type;

  if (opts.anchor_type === "session" && session_type) {
    const win = windowContaining(opts.asset_class, session_type, opts.now_ms);
    if (win) {
      slice = bars.filter((b) => b.open_ts_ms >= win.start_ms && b.open_ts_ms < win.end_ms);
      anchor_start_ms = win.start_ms;
    }
  } else if (opts.anchor_type === "weekly") {
    anchor_start_ms = mondayAnchorMs(opts.asset_class, opts.now_ms);
    slice = bars.filter((b) => b.open_ts_ms >= anchor_start_ms);
    session_type = null;
  } else if (opts.anchor_type === "rolling") {
    slice = bars.slice(-ROLLING_VWAP_PERIODS);
    lookback_periods = ROLLING_VWAP_PERIODS;
    anchor_start_ms = slice[0]?.open_ts_ms ?? opts.now_ms;
    session_type = null;
  }

  if (!slice.length) slice = bars.slice(-1);

  let sumPV = 0;
  let sumV = 0;
  for (const bar of slice) {
    sumPV += typical(bar) * bar.volume;
    sumV += bar.volume;
  }
  const vwap = sumV > 0 ? sumPV / sumV : typical(slice[slice.length - 1]);

  let varSum = 0;
  for (const bar of slice) {
    const d = typical(bar) - vwap;
    varSum += bar.volume * d * d;
  }
  const sigma = sumV > 0 ? Math.sqrt(varSum / sumV) : 0;

  return {
    schema_version: "1.1",
    symbol: opts.symbol,
    asset_class: opts.asset_class,
    anchor_type: opts.anchor_type,
    session_type,
    anchor_start_ms,
    lookback_periods,
    vwap,
    sigma,
    band_m3: vwap - 3 * sigma,
    band_m2: vwap - 2 * sigma,
    band_m1: vwap - 1 * sigma,
    band_p1: vwap + 1 * sigma,
    band_p2: vwap + 2 * sigma,
    band_p3: vwap + 3 * sigma,
    cum_volume: sumV,
    n_obs: slice.length,
    updated_ts_ms: opts.now_ms,
  };
}

export function computeSessionLevels(
  bars: OHLCVBar[],
  window: { session_type: SessionType; start_ms: number; end_ms: number },
  symbol: string,
  asset_class: AssetClass,
  now_ms: number,
): import("./types").SessionLevels | null {
  const slice = bars.filter((b) => b.open_ts_ms >= window.start_ms && b.open_ts_ms < window.end_ms);
  if (!slice.length) return null;
  let high = -Infinity;
  let low = Infinity;
  let volume = 0;
  for (const bar of slice) {
    high = Math.max(high, bar.high);
    low = Math.min(low, bar.low);
    volume += bar.volume;
  }
  return {
    schema_version: "1.1",
    symbol,
    asset_class,
    session_type: window.session_type,
    session_start_ms: window.start_ms,
    session_end_ms: window.end_ms,
    open: slice[0].open,
    high,
    low,
    close: slice[slice.length - 1].close,
    volume,
    updated_ts_ms: now_ms,
  };
}
