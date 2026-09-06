"use client";

import { useEffect, useState } from "react";
import { DESK_SYMBOL_LIMIT, ENSEMBLE_LIMIT, LIST_REFRESH_SEC, RECON_AUDIT_LIMIT } from "@/lib/constants";
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

const EMPTY_ENSEMBLE: EnsemblePicksResponse = {
  as_of_ts_ms: 0,
  refresh_sec: LIST_REFRESH_SEC,
  items: [],
};

const EMPTY_CATS: CategorizedPicksResponse = {
  as_of_ts_ms: 0,
  refresh_sec: LIST_REFRESH_SEC,
  items: [],
};

const EMPTY_UNI = (limit: number): UniverseTopResponse => ({
  as_of_ts_ms: 0,
  limit,
  symbols: [],
});

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

/**
 * P0/P4/universe lists.
 * Mocks only when NEXT_PUBLIC_USE_MOCKS=true.
 * Live mode never substitutes SMCI/TSM-style mock arrays — empty items if Quant/DE miss.
 */
export function useDeskLists(refreshKey = 0): DeskLists {
  const mocks = isMockMode();
  const [data, setData] = useState<DeskLists>(() =>
    mocks
      ? mockDesk(refreshKey)
      : {
          ensemble: EMPTY_ENSEMBLE,
          categorized: EMPTY_CATS,
          dropped: [],
          universeTop10: EMPTY_UNI(ENSEMBLE_LIMIT),
          universeTop20: EMPTY_UNI(DESK_SYMBOL_LIMIT),
          source: "live",
        },
  );

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
      const cats = categorized ?? EMPTY_CATS;
      setData({
        ensemble: ensemble ?? EMPTY_ENSEMBLE,
        categorized: cats,
        dropped: [],
        universeTop10: top10 ?? EMPTY_UNI(ENSEMBLE_LIMIT),
        universeTop20: top20 ?? EMPTY_UNI(DESK_SYMBOL_LIMIT),
        source: "live",
      });
    });
    return () => {
      alive = false;
    };
  }, [mocks, refreshKey]);

  return data;
}
