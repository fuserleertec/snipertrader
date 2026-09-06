"use client";

import { useEffect, useState } from "react";
import { DESK_SYMBOL_LIMIT, ENSEMBLE_LIMIT, RECON_AUDIT_LIMIT } from "@/lib/constants";
import { isMockMode } from "@/lib/env";
import { fetchCategorizedPicks, fetchEnsemblePicks, fetchUniverseTop } from "@/lib/http";
import { mockCategorizedPicks, mockDroppedPicks, mockEnsemblePicks, mockUniverseTop } from "@/lib/mocks/lists";
import type {
  CategorizedPickItem,
  CategorizedPicksResponse,
  EnsemblePicksResponse,
  UniverseTopResponse,
} from "@/lib/types";

export interface DeskLists {
  ensemble: EnsemblePicksResponse;
  categorized: CategorizedPicksResponse;
  dropped: CategorizedPickItem[];
  universeTop10: UniverseTopResponse;
  universeTop20: UniverseTopResponse;
  source: "mock" | "live";
}

function mockDesk(cycle: number): DeskLists {
  const ensemble = mockEnsemblePicks(cycle);
  const categorized = mockCategorizedPicks(cycle, undefined, undefined, DESK_SYMBOL_LIMIT);
  const taken = new Set(categorized.items.map((i) => i.symbol));
  return {
    ensemble,
    categorized,
    dropped: mockDroppedPicks(cycle, taken, RECON_AUDIT_LIMIT),
    universeTop10: mockUniverseTop(ENSEMBLE_LIMIT, cycle),
    universeTop20: mockUniverseTop(DESK_SYMBOL_LIMIT, cycle),
    source: "mock",
  };
}

export function useDeskLists(refreshKey = 0): DeskLists {
  const mocks = isMockMode();
  const [data, setData] = useState<DeskLists>(() => mockDesk(refreshKey));

  useEffect(() => {
    if (mocks) {
      setData(mockDesk(refreshKey));
      return;
    }
    let alive = true;
    Promise.all([
      fetchEnsemblePicks(),
      fetchCategorizedPicks({ limit: DESK_SYMBOL_LIMIT }),
      fetchUniverseTop(ENSEMBLE_LIMIT),
      fetchUniverseTop(DESK_SYMBOL_LIMIT),
    ]).then(([ensemble, categorized, top10, top20]) => {
      if (!alive) return;
      const fallback = mockDesk(refreshKey);
      const cats = categorized ?? fallback.categorized;
      const taken = new Set(cats.items.map((i) => i.symbol));
      setData({
        ensemble: ensemble ?? fallback.ensemble,
        categorized: cats,
        dropped: mockDroppedPicks(refreshKey, taken, RECON_AUDIT_LIMIT),
        universeTop10: top10 ?? fallback.universeTop10,
        universeTop20: top20 ?? fallback.universeTop20,
        source: ensemble || categorized || top10 ? "live" : "mock",
      });
    });
    return () => {
      alive = false;
    };
  }, [mocks, refreshKey]);

  return data;
}
