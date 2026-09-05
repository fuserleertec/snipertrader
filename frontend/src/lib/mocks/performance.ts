import { PERFORMANCE_SETUP_KEYS } from "../constants";
import type { PerformanceMetrics, PerformanceSetupKey, PerformanceSetupStats, PerformanceSummary } from "../types";

const ZERO_OVERALL: PerformanceMetrics = {
  win_rate: 0,
  average_rr: 0,
  sharpe_ratio: 0,
  max_drawdown_pct: 0,
  signals_today: 0,
  signals_week: 0,
  n_signals: 0,
  n_closed: 0,
};

const ZERO_SETUP: PerformanceSetupStats = {
  win_rate: 0,
  average_rr: 0,
  signals: 0,
  n_signals: 0,
  n_closed: 0,
  signals_today: 0,
  signals_week: 0,
};

/** Offline fallback when Quant :8001 is unreachable. */
export const MOCK_PERFORMANCE: PerformanceSummary = {
  timestamp: 1_725_458_400_000,
  source: "mock",
  overall: {
    win_rate: 0.54,
    average_rr: 1.82,
    sharpe_ratio: 0.91,
    max_drawdown_pct: 6.4,
    signals_today: 12,
    signals_week: 71,
    n_signals: 71,
    n_closed: 40,
  },
  by_setup: {
    "1_liquidity_sweep_vwap_reclaim": { win_rate: 0.58, average_rr: 2.1, signals: 28, n_signals: 28 },
    "2_fvg_mitigation_vwap": { win_rate: 0.51, average_rr: 1.7, signals: 22, n_signals: 22 },
    "3_po3_asia_range_sweep": { win_rate: 0.49, average_rr: 1.9, signals: 11, n_signals: 11 },
    "4_sd_extension_fade": { win_rate: 0.56, average_rr: 1.65, signals: 6, n_signals: 6 },
    "5_vwap_pullback_cont": { win_rate: 0.53, average_rr: 1.74, signals: 3, n_signals: 3 },
    "6_avwap_ob_confluence": { win_rate: 0.47, average_rr: 2.05, signals: 1, n_signals: 1 },
  },
};

export function emptyPerformance(now = Date.now()): PerformanceSummary {
  const by_setup = {} as PerformanceSummary["by_setup"];
  for (const key of PERFORMANCE_SETUP_KEYS) {
    by_setup[key] = { ...ZERO_SETUP, product_key: key };
  }
  return { timestamp: now, source: "mock", overall: { ...ZERO_OVERALL }, by_setup };
}

function num(row: Record<string, unknown>, key: string): number | undefined {
  return typeof row[key] === "number" ? (row[key] as number) : undefined;
}

function asSetupStats(raw: unknown, key: PerformanceSetupKey): PerformanceSetupStats {
  if (!raw || typeof raw !== "object") return { ...ZERO_SETUP, product_key: key };
  const row = raw as Record<string, unknown>;
  const n =
    num(row, "n_signals") ??
    num(row, "signals") ??
    num(row, "signals_week") ??
    0;
  return {
    setup_type: typeof row.setup_type === "string" ? row.setup_type : undefined,
    product_key: key,
    win_rate: num(row, "win_rate") ?? 0,
    average_rr: num(row, "average_rr") ?? 0,
    sharpe_ratio: num(row, "sharpe_ratio"),
    max_drawdown_pct: num(row, "max_drawdown_pct"),
    signals: n,
    n_signals: n,
    n_closed: num(row, "n_closed"),
    signals_today: num(row, "signals_today"),
    signals_week: num(row, "signals_week"),
  };
}

function asOverall(raw: Record<string, unknown>): PerformanceMetrics {
  return {
    win_rate: num(raw, "win_rate") ?? 0,
    average_rr: num(raw, "average_rr") ?? 0,
    sharpe_ratio: num(raw, "sharpe_ratio") ?? 0,
    max_drawdown_pct: num(raw, "max_drawdown_pct") ?? 0,
    signals_today: num(raw, "signals_today") ?? 0,
    signals_week: num(raw, "signals_week") ?? 0,
    n_signals: num(raw, "n_signals"),
    n_closed: num(raw, "n_closed"),
  };
}

/** Accept Quant PR #2 flat envelope or DE #8 `{ timestamp, overall, by_setup }`. */
export function normalizePerformance(raw: unknown, source: "live" | "mock" = "live"): PerformanceSummary {
  const base = emptyPerformance();
  if (!raw || typeof raw !== "object") return { ...base, source };
  const src = raw as Record<string, unknown>;
  const overallSrc =
    src.overall && typeof src.overall === "object"
      ? (src.overall as Record<string, unknown>)
      : src;
  const byRaw = (src.by_setup && typeof src.by_setup === "object" ? src.by_setup : {}) as Record<
    string,
    unknown
  >;
  const by_setup = { ...base.by_setup };
  for (const key of PERFORMANCE_SETUP_KEYS) {
    by_setup[key] = asSetupStats(byRaw[key], key);
  }
  return {
    timestamp: typeof src.timestamp === "number" ? src.timestamp : base.timestamp,
    source,
    overall: asOverall(overallSrc),
    by_setup,
    rolling_win_rate_20: typeof src.rolling_win_rate_20 === "number" ? src.rolling_win_rate_20 : null,
    drift_warning: src.drift_warning === true,
  };
}
