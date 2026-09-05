"use client";

import { useEffect, useState } from "react";
import { seedPrice } from "@/lib/constants";
import { isLivePatternWs } from "@/lib/env";
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
 * Pattern overlays. Live DE PR #5 sockets when `NEXT_PUBLIC_USE_MOCKS=false`
 * and `NEXT_PUBLIC_WS_BASE` is set (`ws://localhost:8000/v1/ws/{sweep|fvg|mss|ob}?symbol=`).
 * Otherwise in-browser schema 1.1 seed+pubsub (same raw frames, no envelope).
 */
export function usePatterns(symbol: string): PatternBook {
  const live = isLivePatternWs();
  const [book, setBook] = useState<PatternBook>(() => (live ? emptyPatternBook() : seedBook(symbol)));
  const [active, setActive] = useState(symbol);

  if (symbol !== active) {
    if (!live) dropUniverse(active);
    setActive(symbol);
    setBook(live ? emptyPatternBook() : seedBook(symbol));
  }

  useEffect(() => {
    const applyFrame = (hint: OverlayKind, data: unknown) => {
      const event = parseOverlayFrame(data, hint);
      if (!event) return;
      setBook((prev) => ingest(prev, event));
    };

    if (!live) {
      return startMockPatternSockets(symbol, () => seedPrice(symbol), applyFrame);
    }

    return openPatternSockets(symbol, (event) => {
      setBook((prev) => ingest(prev, event));
    });
  }, [symbol, live]);

  return book;
}
