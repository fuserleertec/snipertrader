"use client";

import { useEffect, useState } from "react";
import { seedPrice } from "@/lib/constants";
import { isMockMode } from "@/lib/env";
import { startMockPatternSockets } from "@/lib/mocks/patterns";
import { dropUniverse, getUniverse } from "@/lib/mocks/universe";
import { applyOverlayEvent, emptyPatternBook, parseOverlayFrame } from "@/lib/overlays";
import { openPatternSockets } from "@/lib/patternWs";
import type { OverlayEvent, OverlayKind, PatternBook } from "@/lib/types";

function seedBook(symbol: string): PatternBook {
  return getUniverse(symbol, seedPrice(symbol)).book;
}

function ingest(book: PatternBook, event: OverlayEvent): PatternBook {
  return applyOverlayEvent({ ...book }, event);
}

/**
 * Pattern overlays. `NEXT_PUBLIC_USE_MOCKS=true` (default) uses in-browser
 * schema 1.1 seed+pubsub. `false` opens DE PR #5 sockets:
 * `WS /v1/ws/sweep|fvg|mss|ob?symbol=` on `NEXT_PUBLIC_WS_BASE`
 * (default `ws://localhost:8000`).
 */
export function usePatterns(symbol: string): PatternBook {
  const mocks = isMockMode();
  const [book, setBook] = useState<PatternBook>(() => (mocks ? seedBook(symbol) : emptyPatternBook()));
  const [active, setActive] = useState(symbol);

  if (symbol !== active) {
    if (mocks) dropUniverse(active);
    setActive(symbol);
    setBook(mocks ? seedBook(symbol) : emptyPatternBook());
  }

  useEffect(() => {
    const applyFrame = (hint: OverlayKind, data: unknown) => {
      const event = parseOverlayFrame(data, hint);
      if (!event) return;
      setBook((prev) => ingest(prev, event));
    };

    if (mocks) {
      return startMockPatternSockets(symbol, () => seedPrice(symbol), applyFrame);
    }

    return openPatternSockets(symbol, (event) => {
      setBook((prev) => ingest(prev, event));
    });
  }, [symbol, mocks]);

  return book;
}
