"use client";

import { useState } from "react";
import { seedPrice } from "@/lib/constants";
import { dropUniverse, getUniverse } from "@/lib/mocks/universe";
import type { PatternBook } from "@/lib/types";

export function usePatterns(symbol: string): PatternBook {
  const [book, setBook] = useState<PatternBook>(() => getUniverse(symbol, seedPrice(symbol)).book);
  const [active, setActive] = useState(symbol);

  if (symbol !== active) {
    dropUniverse(active);
    setActive(symbol);
    setBook(getUniverse(symbol, seedPrice(symbol)).book);
  }

  return book;
}
