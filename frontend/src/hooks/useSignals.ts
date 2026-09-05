"use client";

import { useEffect, useState } from "react";
import { isMockMode } from "@/lib/env";
import { startMockSignals } from "@/lib/mocks/signals";
import { toSignalRow } from "@/lib/signals";
import type { SignalFrame, SignalRow } from "@/lib/types";
import { openJsonWs } from "@/lib/ws";

const MAX_ROWS = 80;

function ingest(prev: SignalRow[], frame: SignalFrame): SignalRow[] {
  const row = toSignalRow(frame);
  if (!row) return prev;
  const next = [row, ...prev.filter((r) => r.id !== row.id)];
  return next.slice(0, MAX_ROWS);
}

/**
 * TODO(quant): swap the mock stream for the Quant Risk Pre-Filter API
 * once that contract is live. With NEXT_PUBLIC_USE_MOCKS=false this
 * already opens `WS /v1/ws/signals?symbol=` — replace that path when
 * Quant publishes the real endpoint.
 */
export function useSignals(symbol: string, lastPrice: () => number): SignalRow[] {
  const mocks = isMockMode();
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [activeSymbol, setActiveSymbol] = useState(symbol);

  if (symbol !== activeSymbol) {
    setActiveSymbol(symbol);
    setRows([]);
  }

  useEffect(() => {
    if (mocks) {
      return startMockSignals(symbol, lastPrice, (frame) => {
        setRows((prev) => ingest(prev, frame));
      });
    }
    return openJsonWs(
      "/v1/ws/signals",
      { symbol },
      (data) => {
        setRows((prev) => ingest(prev, data as SignalFrame));
      },
      () => undefined,
    );
    // lastPrice is a stable () => ref.current from the dashboard
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, mocks]);

  return rows;
}
