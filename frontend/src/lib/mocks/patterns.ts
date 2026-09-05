import type { OverlayEvent, PatternBook, SweepEvent } from "../types";
import { overlayEventsFromBook } from "../overlays";
import { getUniverse, MOCK_NOW } from "./universe";

/** In-browser overlay stream typed to `/schemas/*` 1.1. DE has no pattern WS yet. */
export function startMockPatternStream(
  symbol: string,
  lastPrice: () => number,
  onEvent: (event: OverlayEvent) => void,
): () => void {
  const { book } = getUniverse(symbol, lastPrice());
  const seed = overlayEventsFromBook(book);
  let seq = 0;
  let i = 0;

  const pushSeed = () => {
    const ev = seed[i % seed.length];
    i += 1;
    if (!ev) return;
    if (ev.kind === "fvg") {
      onEvent({ kind: "fvg", payload: { ...ev.payload, mitigated: seq % 5 === 0 ? !ev.payload.mitigated : ev.payload.mitigated } });
      return;
    }
    if (ev.kind === "sweep") {
      const next: SweepEvent = {
        ...ev.payload,
        id: `${ev.payload.id}_live_${seq}`,
        ts_ms: MOCK_NOW - (seq % 8) * 60_000,
        confirmed: true,
      };
      onEvent({ kind: "sweep", payload: next });
      return;
    }
    onEvent(ev);
  };

  const first = setTimeout(() => {
    seq += 1;
    pushSeed();
  }, 3200);
  const timer = setInterval(() => {
    seq += 1;
    pushSeed();
  }, 5200);

  return () => {
    clearTimeout(first);
    clearInterval(timer);
  };
}

export function seedPatternBook(symbol: string, price: number): PatternBook {
  return getUniverse(symbol, price).book;
}
