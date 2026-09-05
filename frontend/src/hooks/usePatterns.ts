"use client";

import { useEffect, useState } from "react";
import { seedPrice } from "@/lib/constants";
import { startMockPatternStream } from "@/lib/mocks/patterns";
import { dropUniverse, getUniverse } from "@/lib/mocks/universe";
import { applyOverlayEvent } from "@/lib/overlays";
import type { PatternBook } from "@/lib/types";

function seedBook(symbol: string): PatternBook {
  return getUniverse(symbol, seedPrice(symbol)).book;
}

/**
 * Pattern overlays. Data Eng has **no** pattern WS yet — mock schema 1.1
 * streams only. `parseOverlayFrame` + `FUTURE_PATTERN_WS` are ready for a
 * later `WS /v1/ws/fvg|ob|sweep|mss?symbol=` seed+pubsub.
 */
export function usePatterns(symbol: string): PatternBook {
  const [book, setBook] = useState<PatternBook>(() => seedBook(symbol));
  const [active, setActive] = useState(symbol);

  if (symbol !== active) {
    dropUniverse(active);
    setActive(symbol);
    setBook(seedBook(symbol));
  }

  useEffect(() => {
    const seeded = seedBook(symbol);
    queueMicrotask(() => setBook(seeded));
    return startMockPatternStream(symbol, () => seedPrice(symbol), (event) => {
      setBook((prev) => applyOverlayEvent({ ...prev }, event));
    });
  }, [symbol]);

  return book;
}
