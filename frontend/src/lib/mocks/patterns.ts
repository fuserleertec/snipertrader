import type { OverlayEvent, OverlayKind, PatternBook, SweepEvent } from "../types";
import { overlayEventsFromBook, parseOverlayFrame } from "../overlays";
import { getUniverse, MOCK_NOW } from "./universe";

export type PatternFrameHandler = (hint: OverlayKind, frame: unknown) => void;

/**
 * In-browser stand-in for DE PR #5 overlay sockets.
 * Same contract as VWAP: emit seed frames immediately, then pub/sub updates.
 * Frames are exact `/schemas` 1.1 JSON (not wrapped).
 */
export function startMockPatternSockets(
  symbol: string,
  lastPrice: () => number,
  onFrame: PatternFrameHandler,
): () => void {
  const { book } = getUniverse(symbol, lastPrice());
  const seed = overlayEventsFromBook(book);

  for (const ev of seed) {
    onFrame(ev.kind, ev.payload);
  }

  let seq = 0;
  let i = 0;

  const pushLive = () => {
    const ev = seed[i % seed.length];
    i += 1;
    if (!ev) return;
    seq += 1;
    if (ev.kind === "fvg") {
      onFrame("fvg", {
        ...ev.payload,
        mitigated: seq % 5 === 0 ? !ev.payload.mitigated : ev.payload.mitigated,
      });
      return;
    }
    if (ev.kind === "sweep") {
      const next: SweepEvent = {
        ...ev.payload,
        id: `${ev.payload.id}_live_${seq}`,
        ts_ms: MOCK_NOW - (seq % 8) * 60_000,
        confirmed: true,
      };
      onFrame("sweep", next);
      return;
    }
    onFrame(ev.kind, ev.payload);
  };

  const timer = setInterval(pushLive, 5200);
  return () => clearInterval(timer);
}

/** Typed OverlayEvent wrapper around the schema-frame mock sockets. */
export function startMockPatternStream(
  symbol: string,
  lastPrice: () => number,
  onEvent: (event: OverlayEvent) => void,
): () => void {
  return startMockPatternSockets(symbol, lastPrice, (hint, frame) => {
    const event = parseOverlayFrame(frame, hint);
    if (event) onEvent(event);
  });
}

export function seedPatternBook(symbol: string, price: number): PatternBook {
  return getUniverse(symbol, price).book;
}
