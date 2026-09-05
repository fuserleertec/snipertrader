"use client";

import { useEffect, useState } from "react";
import { seedPrice } from "@/lib/constants";
import { isMockMode, quantWsUrl } from "@/lib/env";
import { fetchSignals } from "@/lib/http";
import { mockListSignals, startMockSignalStream } from "@/lib/mocks/signals";
import { isSignalWsEvent, normalizeSignal, upsertSignal } from "@/lib/signals";
import type { Signal } from "@/lib/types";
import { openJsonWsAt } from "@/lib/ws";

function seedSignals(symbol: string): Signal[] {
  return mockListSignals({ symbol, limit: 24 }, seedPrice(symbol)).items;
}

export function useSignals(symbol: string, lastPrice: () => number): Signal[] {
  const mocks = isMockMode();
  const [rows, setRows] = useState<Signal[]>(() => (mocks ? seedSignals(symbol) : []));
  const [activeSymbol, setActiveSymbol] = useState(symbol);

  if (symbol !== activeSymbol) {
    setActiveSymbol(symbol);
    setRows(mocks ? seedSignals(symbol) : []);
  }

  useEffect(() => {
    let alive = true;

    const applyEvent = (data: unknown) => {
      if (!isSignalWsEvent(data)) return;
      const signal = normalizeSignal(data.signal);
      if (!signal || signal.symbol !== symbol) return;
      setRows((prev) => upsertSignal(prev, signal));
    };

    if (mocks) {
      const seed = seedSignals(symbol);
      return startMockSignalStream(symbol, lastPrice, applyEvent, seed);
    }

    fetchSignals({ symbol, limit: 40 }).then((list) => {
      if (!alive || !list) return;
      setRows(list.items.map((row) => normalizeSignal(row)).filter((row): row is NonNullable<typeof row> => !!row));
    });

    // Quant PR #2: WS /ws/signals → { type: "signal.upsert"|"signal.status", signal }
    const stop = openJsonWsAt(quantWsUrl("/ws/signals"), applyEvent, () => undefined);
    return () => {
      alive = false;
      stop();
    };
    // lastPrice is a stable () => ref.current from the dashboard
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, mocks]);

  return rows;
}
