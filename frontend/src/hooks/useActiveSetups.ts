"use client";

import { useEffect, useState } from "react";
import { activeSetupQuery } from "@/lib/desk";
import { isMockMode } from "@/lib/env";
import { fetchActiveSetups } from "@/lib/http";
import { mockListSignals } from "@/lib/mocks/signals";
import type { AssetTab, SetupType, Signal } from "@/lib/types";

/**
 * Active Setup Cards — GET /signals?status=ACTIVE&asset_class=futures|equity|crypto
 * Stocks tab maps to equity. Mocks only when USE_MOCKS=true.
 */
export function useActiveSetups(
  tab: AssetTab,
  setupFilter: SetupType | "all" = "all",
  refreshKey = 0,
  symbol?: string,
): Signal[] {
  const mocks = isMockMode();
  const query = activeSetupQuery(tab, { setup_type: setupFilter, symbol });
  const [rows, setRows] = useState<Signal[]>(() => (mocks ? mockListSignals(query, 0).items : []));

  useEffect(() => {
    if (mocks) {
      setRows(mockListSignals(query, 0).items);
      return;
    }
    let alive = true;
    fetchActiveSetups(tab, { setup_type: setupFilter, symbol }).then((list) => {
      if (!alive) return;
      setRows(list?.items ?? []);
    });
    return () => {
      alive = false;
    };
  }, [mocks, refreshKey, tab, setupFilter, symbol, query.asset_class, query.setup_type, query.limit]);

  return rows;
}
