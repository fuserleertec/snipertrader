import { PERFORMANCE_SETUP_KEYS } from "../constants";
import type { PerformanceMetrics, PerformanceSetupKey, PerformanceSummary } from "../types";

const ZERO: PerformanceMetrics = {
  win_rate: 0,
  average_rr: 0,
  sharpe_ratio: 0,
  max_drawdown_pct: 0,
  signals_today: 0,
  signals_week: 0,
};

/** Mock until Quant confirms the live path (likely :8001). Shape is locked. */
export const MOCK_PERFORMANCE: PerformanceSummary = {
  overall: {
    win_rate: 0.54,
    average_rr: 1.82,
    sharpe_ratio: 0.91,
    max_drawdown_pct: 6.4,
    signals_today: 12,
    signals_week: 71,
  },
  by_setup: {
    "1_liquidity_sweep_vwap_reclaim": {
      win_rate: 0.58,
      average_rr: 2.1,
      sharpe_ratio: 1.05,
      max_drawdown_pct: 4.8,
      signals_today: 5,
      signals_week: 28,
    },
    "2_fvg_mitigation_vwap": {
      win_rate: 0.51,
      average_rr: 1.7,
      sharpe_ratio: 0.74,
      max_drawdown_pct: 7.2,
      signals_today: 4,
      signals_week: 22,
    },
    "3": { ...ZERO },
    "4": { ...ZERO },
    "5": { ...ZERO },
    "6": { ...ZERO },
  },
};

export function emptyPerformance(): PerformanceSummary {
  const by_setup = {} as PerformanceSummary["by_setup"];
  for (const key of PERFORMANCE_SETUP_KEYS) {
    by_setup[key] = { ...ZERO };
  }
  return { overall: { ...ZERO }, by_setup };
}

export function normalizePerformance(raw: PerformanceSummary | null | undefined): PerformanceSummary {
  const base = emptyPerformance();
  if (!raw || typeof raw !== "object") return base;
  const overall = { ...base.overall, ...(raw.overall ?? {}) };
  const by_setup = { ...base.by_setup };
  for (const key of PERFORMANCE_SETUP_KEYS) {
    const row = raw.by_setup?.[key as PerformanceSetupKey];
    by_setup[key] = { ...ZERO, ...(row ?? {}) };
  }
  return { overall, by_setup };
}
