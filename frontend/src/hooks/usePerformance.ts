"use client";

import { useEffect, useState } from "react";
import { isMockMode } from "@/lib/env";
import { fetchPerformanceSummary } from "@/lib/http";
import { MOCK_PERFORMANCE, normalizePerformance } from "@/lib/mocks/performance";
import type { PerformanceSummary } from "@/lib/types";

export function usePerformance(refreshKey = 0): PerformanceSummary {
  const mocks = isMockMode();
  const [data, setData] = useState<PerformanceSummary>(MOCK_PERFORMANCE);

  useEffect(() => {
    if (mocks) {
      queueMicrotask(() => setData(MOCK_PERFORMANCE));
      return;
    }
    let alive = true;
    fetchPerformanceSummary().then((raw) => {
      if (!alive) return;
      setData(normalizePerformance(raw));
    });
    return () => {
      alive = false;
    };
  }, [mocks, refreshKey]);

  return data;
}
