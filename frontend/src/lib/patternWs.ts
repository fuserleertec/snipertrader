import { normalizeSymbol } from "./constants";
import { wsUrl } from "./env";
import { PATTERN_WS, parseOverlayFrame } from "./overlays";
import type { ConnectionStatus, OverlayEvent, OverlayKind } from "./types";
import { openJsonWsAt } from "./ws";

export { PATTERN_WS };

/** `ws://localhost:8000/v1/ws/sweep?symbol=BTCUSDT` (and fvg / mss / ob). */
export function patternWsUrl(kind: OverlayKind, symbol: string): string {
  return wsUrl(PATTERN_WS[kind], { symbol: normalizeSymbol(symbol) });
}

/**
 * Four DE PR #5 overlay sockets. Server seeds SCAN `{prefix}:{symbol}:*`
 * then pub/sub `{prefix}:{symbol}`. Each `onmessage` frame is raw
 * `/schemas` 1.1 JSON — no wrapper envelope.
 *
 * @example
 * const ws = new WebSocket("ws://localhost:8000/v1/ws/sweep?symbol=BTCUSDT");
 * ws.onmessage = (e) => JSON.parse(e.data);
 */
export function openPatternSockets(
  symbol: string,
  onEvent: (event: OverlayEvent) => void,
  onStatus: (status: ConnectionStatus) => void = () => undefined,
): () => void {
  const wanted = normalizeSymbol(symbol);
  const apply = (hint: OverlayKind, data: unknown) => {
    const event = parseOverlayFrame(data, hint);
    if (!event) return;
    if (normalizeSymbol(event.payload.symbol) !== wanted) return;
    onEvent(event);
  };

  const kinds = Object.keys(PATTERN_WS) as OverlayKind[];
  const stops = kinds.map((kind, index) =>
    openJsonWsAt(patternWsUrl(kind, wanted), (data) => apply(kind, data), index === 0 ? onStatus : () => undefined),
  );

  return () => {
    for (const stop of stops) stop();
  };
}
