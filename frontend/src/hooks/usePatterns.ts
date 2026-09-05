"use client";

import { useEffect, useState } from "react";
import { seedPrice } from "@/lib/constants";
import { dropUniverse, getUniverse } from "@/lib/mocks/universe";
import type { PatternBook } from "@/lib/types";

const EMPTY: PatternBook = { fvgs: [], obs: [], sweeps: [], mss: [] };

export function usePatterns(symbol: string): PatternBook {
  const [book, setBook] = useState<PatternBook>(EMPTY);
  const [active, setActive] = useState(symbol);

  if (symbol !== active) {
    dropUniverse(active);
    setActive(symbol);
    setBook(EMPTY);
  }

  useEffect(() => {
    const book = getUniverse(symbol, seedPrice(symbol)).book;
    queueMicrotask(() => setBook(book));
  }, [symbol]);

  return book;
}
