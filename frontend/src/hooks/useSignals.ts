"use client";

import { useEffect, useState } from "react";
import { seedPrice } from "@/lib/constants";
import { isMockMode, quantWsUrl } from "@/lib/env";
import { fetchSignals } from "@/lib/http";
import { mockListSignals, startMockSignalStream } from "@/lib/mocks/signals";
import { isSignalWsEvent, upsertSignal } from "@/lib/signals";
import type { Signal } from "@/lib/types";
import { openJsonWsAt } from "@/lib/ws";

export function useSignals(symbol: string, lastPrice: () => number): Signal[] {
  const mocks = isMockMode();
  const [rows, setRows] = useState<Signal[]>([]);
  const [activeSymbol, setActiveSymbol] = useState(symbol);

  if (symbol !== activeSymbol) {
    setActiveSymbol(symbol);
    setRows([]);
  }

  useEffect(() => {
    let alive = true;

    const applyEvent = (data: unknown) => {
      if (!isSignalWsEvent(data)) return;
      if (data.signal.symbol !== symbol) return;
      setRows((prev) => upsertSignal(prev, data.signal));
    };

    if (mocks) {
      const seed = mockListSignals({ symbol, limit: 24 }, seedPrice(symbol)).items;
      setRows(seed);
      return startMockSignalStream(symbol, lastPrice, applyEvent, seed);
    }

    fetchSignals({ symbol, limit: 40 }).then((list) => {
      if (!alive || !list) return;
      setRows(list.items);
    });

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
