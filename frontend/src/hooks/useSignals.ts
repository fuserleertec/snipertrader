"use client";

import { useEffect, useState } from "react";
import { DESK_SYMBOL_LIMIT, seedPrice } from "@/lib/constants";
import { isMockMode, quantWsUrl } from "@/lib/env";
import { fetchSignalHistory, fetchSignals } from "@/lib/http";
import { mockListSignals, startMockSignalStream } from "@/lib/mocks/signals";
import { isSignalWsEvent, normalizeSignal, upsertSignal } from "@/lib/signals";
import type { Signal } from "@/lib/types";
import { openJsonWsAt } from "@/lib/ws";

function seedDesk(): Signal[] {
  return mockListSignals({ limit: 200 }, 0).items;
}

/**
 * Desk-wide setup_signals (up to 20 symbols). Chart focus only drives the
 * mock WS upsert stream — it does not wipe the list.
 */
export function useSignals(focusSymbol: string, lastPrice: () => number, refreshKey = 0): Signal[] {
  const mocks = isMockMode();
  const [rows, setRows] = useState<Signal[]>(() => (mocks ? seedDesk() : []));

  useEffect(() => {
    let alive = true;
    if (mocks) {
      setRows(seedDesk());
      return () => {
        alive = false;
      };
    }
    const query = { limit: 200 };
    Promise.all([fetchSignalHistory(query), fetchSignals(query)]).then(([history, list]) => {
      if (!alive) return;
      const items = history?.items?.length ? history.items : (list?.items ?? []);
      setRows(items);
    });
    return () => {
      alive = false;
    };
  }, [mocks, refreshKey]);

  useEffect(() => {
    const applyEvent = (data: unknown) => {
      try {
        if (!isSignalWsEvent(data)) return;
        const signal = normalizeSignal(data.signal);
        if (!signal) return;
        setRows((prev) => upsertSignal(prev, signal).slice(0, 80 + DESK_SYMBOL_LIMIT * 4));
      } catch {
        /* ignore malformed frames */
      }
    };

    if (mocks) {
      const seed = mockListSignals({ symbol: focusSymbol, limit: 24 }, seedPrice(focusSymbol)).items;
      return startMockSignalStream(focusSymbol, lastPrice, applyEvent, seed);
    }

    const stop = openJsonWsAt(quantWsUrl("/ws/signals"), applyEvent, () => undefined);
    return () => {
      stop();
    };
    // lastPrice is a stable () => ref.current from the dashboard
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusSymbol, mocks]);

  return rows;
}
