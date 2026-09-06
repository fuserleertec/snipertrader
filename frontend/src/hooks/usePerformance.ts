"use client";

import { useEffect, useState } from "react";
import { DESK_SYMBOL_LIMIT } from "@/lib/constants";
import { isMockMode } from "@/lib/env";
import { fetchPerformanceSummary } from "@/lib/http";
import { emptyPerformance, MOCK_PERFORMANCE, normalizePerformance } from "@/lib/mocks/performance";
import type { PerformanceSummary } from "@/lib/types";

const EMPTY_LIVE: PerformanceSummary = { ...emptyPerformance(), source: "live" };

/**
 * GET /performance/summary. Optional `symbols=` (≤20) for the desk universe.
 * Live mode never substitutes MOCK_PERFORMANCE — empty envelope if Quant misses.
 */
export function usePerformance(refreshKey = 0, deskSymbols: string[] = []): PerformanceSummary {
  const mocks = isMockMode();
  const [data, setData] = useState<PerformanceSummary>(() => (mocks ? MOCK_PERFORMANCE : EMPTY_LIVE));
  const symbolKey = deskSymbols.join(",");

  useEffect(() => {
    if (mocks) {
      setData(MOCK_PERFORMANCE);
      return;
    }
    let alive = true;
    const symbols = deskSymbols.length ? deskSymbols.slice(0, DESK_SYMBOL_LIMIT) : undefined;
    fetchPerformanceSummary(symbols).then((raw) => {
      if (!alive) return;
      setData(raw ? normalizePerformance(raw, "live") : EMPTY_LIVE);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey, mocks, symbolKey]);

  return data;
}
