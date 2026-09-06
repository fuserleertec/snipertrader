"use client";

import { useEffect, useState } from "react";
import { DESK_SYMBOL_LIMIT, ENSEMBLE_LIMIT, LIST_REFRESH_SEC, RECON_AUDIT_LIMIT } from "@/lib/constants";
import { allowedSymbolSet, capWithinAllowed, rankWithinAllowed, universeSourceFromAllowed } from "@/lib/desk";
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
  universe_source: "SETUP_UNIVERSE",
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
  const universeTop10 = mockUniverseTop(ENSEMBLE_LIMIT, cycle);
  const universeTop20 = mockUniverseTop(DESK_SYMBOL_LIMIT, cycle);
  const allowed10 = universeTop10.symbols.map((s) => s.symbol);
  const allowed20 = universeTop20.symbols.map((s) => s.symbol);
  const ensemble = mockEnsemblePicks(cycle, undefined, allowed10);
  const categorized = mockCategorizedPicks(cycle, undefined, undefined, DESK_SYMBOL_LIMIT, allowed20);
  const taken = new Set(categorized.items.map((i) => i.symbol));
  return {
    ensemble,
    categorized,
    dropped: mockDroppedPicks(cycle, taken, RECON_AUDIT_LIMIT),
    universeTop10,
    universeTop20,
    source: "mock",
  };
}

/**
 * P0/P4/universe lists.
 * DE `GET /v1/universe/top` is the allowed set when contracted; Quant ranks
 * top-10 / ≤20 inside it. Mocks only when NEXT_PUBLIC_USE_MOCKS=true
 * (provisional SETUP_UNIVERSE). Live never invents a hard-coded P0/P4 list.
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
      const ens = ensemble ?? EMPTY_ENSEMBLE;
      const uni10 = top10 ?? EMPTY_UNI(ENSEMBLE_LIMIT);
      const uni20 = top20 ?? EMPTY_UNI(DESK_SYMBOL_LIMIT);
      const allowed10 = allowedSymbolSet(uni10.symbols);
      const allowed20 = allowedSymbolSet(uni20.symbols);
      setData({
        ensemble: {
          ...ens,
          universe_source: universeSourceFromAllowed(allowed10, ens.universe_source),
          items: rankWithinAllowed(ens.items, allowed10),
        },
        categorized: {
          ...cats,
          universe_source: universeSourceFromAllowed(allowed20, cats.universe_source),
          items: capWithinAllowed(cats.items, allowed20),
        },
        dropped: [],
        universeTop10: uni10,
        universeTop20: uni20,
        source: "live",
      });
    });
    return () => {
      alive = false;
    };
  }, [mocks, refreshKey]);

  return data;
}
