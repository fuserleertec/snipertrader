import { normalizeSymbol } from "./constants";
import { PATTERN_WS, parseOverlayFrame } from "./overlays";
import type { ConnectionStatus, OverlayEvent, OverlayKind } from "./types";
import { openJsonWs } from "./ws";

export { PATTERN_WS };

/**
 * Four DE overlay sockets (PR #5). Same shape as VWAP: seed-then-pubsub.
 * Each frame is a raw `/schemas` 1.1 object; `hint` comes from the path.
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

  const stops = (Object.entries(PATTERN_WS) as Array<[OverlayKind, string]>).map(
    ([kind, path], index) =>
      openJsonWs(path, { symbol: wanted }, (data) => apply(kind, data), index === 0 ? onStatus : () => undefined),
  );

  return () => {
    for (const stop of stops) stop();
  };
}
