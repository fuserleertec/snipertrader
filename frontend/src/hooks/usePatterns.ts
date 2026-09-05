"use client";

import { useEffect, useState } from "react";
import { seedPrice } from "@/lib/constants";
import { isMockMode } from "@/lib/env";
import { dropUniverse, getUniverse } from "@/lib/mocks/universe";
import { applyOverlayEvent, parseOverlayFrame } from "@/lib/overlays";
import type { PatternBook } from "@/lib/types";
import { openJsonWs } from "@/lib/ws";

function seedBook(symbol: string): PatternBook {
  return getUniverse(symbol, seedPrice(symbol)).book;
}

export function usePatterns(symbol: string): PatternBook {
  const mocks = isMockMode();
  const [book, setBook] = useState<PatternBook>(() => seedBook(symbol));
  const [active, setActive] = useState(symbol);

  if (symbol !== active) {
    dropUniverse(active);
    setActive(symbol);
    setBook(seedBook(symbol));
  }

  useEffect(() => {
    if (mocks) {
      const seeded = seedBook(symbol);
      queueMicrotask(() => setBook(seeded));
      return;
    }

    const stops: Array<() => void> = [];
    const apply = (data: unknown) => {
      const event = parseOverlayFrame(data);
      if (!event) return;
      setBook((prev) => applyOverlayEvent({ ...prev }, event));
    };

    // Data Eng PR #5 overlay sockets. Mock book stays until a live frame arrives.
    for (const path of ["/v1/ws/fvg", "/v1/ws/ob", "/v1/ws/sweep", "/v1/ws/mss"] as const) {
      stops.push(openJsonWs(path, { symbol }, apply, () => undefined));
    }

    return () => {
      for (const stop of stops) stop();
    };
  }, [symbol, mocks]);

  return book;
}
