"use client";

import { useEffect, useState } from "react";
import { fetchPerformanceSummary } from "@/lib/http";
import { MOCK_PERFORMANCE, normalizePerformance } from "@/lib/mocks/performance";
import type { PerformanceSummary } from "@/lib/types";

export function usePerformance(refreshKey = 0): PerformanceSummary {
  const [data, setData] = useState<PerformanceSummary>(MOCK_PERFORMANCE);

  useEffect(() => {
    let alive = true;
    fetchPerformanceSummary().then((raw) => {
      if (!alive) return;
      setData(raw ? normalizePerformance(raw, "live") : MOCK_PERFORMANCE);
    });
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  return data;
}
