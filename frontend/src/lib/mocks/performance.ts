import { PERFORMANCE_SETUP_KEYS } from "../constants";
import type { PerformanceMetrics, PerformanceSetupKey, PerformanceSetupStats, PerformanceSummary } from "../types";

const ZERO_OVERALL: PerformanceMetrics = {
  win_rate: 0,
  average_rr: 0,
  sharpe_ratio: 0,
  max_drawdown_pct: 0,
  signals_today: 0,
  signals_week: 0,
};

const ZERO_SETUP: PerformanceSetupStats = {
  win_rate: 0,
  average_rr: 0,
  signals: 0,
};

/** DE PR #8 envelope. Mock when GET /performance/summary is unreachable. */
export const MOCK_PERFORMANCE: PerformanceSummary = {
  timestamp: 1_725_458_400_000,
  overall: {
    win_rate: 0.54,
    average_rr: 1.82,
    sharpe_ratio: 0.91,
    max_drawdown_pct: 6.4,
    signals_today: 12,
    signals_week: 71,
  },
  by_setup: {
    "1_liquidity_sweep_vwap_reclaim": { win_rate: 0.58, average_rr: 2.1, signals: 28 },
    "2_fvg_mitigation_vwap": { win_rate: 0.51, average_rr: 1.7, signals: 22 },
    "3_po3_asia_range_sweep": { win_rate: 0.49, average_rr: 1.9, signals: 11 },
    "4_sd_extension_fade": { win_rate: 0.56, average_rr: 1.65, signals: 6 },
    "5_vwap_pullback_cont": { win_rate: 0.53, average_rr: 1.74, signals: 3 },
    "6_avwap_ob_confluence": { win_rate: 0.47, average_rr: 2.05, signals: 1 },
  },
};

export function emptyPerformance(now = Date.now()): PerformanceSummary {
  const by_setup = {} as PerformanceSummary["by_setup"];
  for (const key of PERFORMANCE_SETUP_KEYS) {
    by_setup[key] = { ...ZERO_SETUP };
  }
  return { timestamp: now, overall: { ...ZERO_OVERALL }, by_setup };
}

function asSetupStats(raw: unknown): PerformanceSetupStats {
  if (!raw || typeof raw !== "object") return { ...ZERO_SETUP };
  const row = raw as Record<string, unknown>;
  const signals =
    typeof row.signals === "number"
      ? row.signals
      : typeof row.signals_week === "number"
        ? row.signals_week
        : 0;
  return {
    win_rate: typeof row.win_rate === "number" ? row.win_rate : 0,
    average_rr: typeof row.average_rr === "number" ? row.average_rr : 0,
    signals,
  };
}

export function normalizePerformance(raw: unknown): PerformanceSummary {
  const base = emptyPerformance();
  if (!raw || typeof raw !== "object") return base;
  const src = raw as {
    timestamp?: number;
    overall?: Partial<PerformanceMetrics>;
    by_setup?: Partial<Record<PerformanceSetupKey, unknown>>;
  };
  const overall = { ...base.overall, ...(src.overall ?? {}) };
  const by_setup = { ...base.by_setup };
  for (const key of PERFORMANCE_SETUP_KEYS) {
    by_setup[key] = asSetupStats(src.by_setup?.[key]);
  }
  return {
    timestamp: typeof src.timestamp === "number" ? src.timestamp : base.timestamp,
    overall,
    by_setup,
  };
}
