import { SIGNAL_STATUSES } from "../constants";
import type { Signal, SignalListQuery, SignalListResponse, SignalStatus, SignalWsEvent } from "../types";
import { getUniverse } from "./universe";

function matches(signal: Signal, query: SignalListQuery): boolean {
  if (query.symbol && signal.symbol !== query.symbol) return false;
  if (query.status && signal.status !== query.status) return false;
  if (query.setup_type && signal.setup_type !== query.setup_type) return false;
  if (query.side && signal.side !== query.side) return false;
  if (query.from_ts != null && signal.ts_ms < query.from_ts) return false;
  if (query.to_ts != null && signal.ts_ms > query.to_ts) return false;
  return true;
}

export function mockGetSignal(id: string, lastPrice: number): Signal | null {
  const { signals } = getUniverse("BTCUSDT", lastPrice);
  const hit = signals.find((s) => s.id === id);
  return hit ?? null;
}

export function mockListSignals(query: SignalListQuery, lastPrice: number): SignalListResponse {
  const symbol = query.symbol ?? "BTCUSDT";
  const { signals } = getUniverse(symbol, lastPrice);
  const items = signals.filter((s) => matches(s, query)).sort((a, b) => b.ts_ms - a.ts_ms || a.id.localeCompare(b.id));
  let start = 0;
  if (query.cursor) {
    const idx = items.findIndex((s) => s.id === query.cursor);
    start = idx >= 0 ? idx + 1 : 0;
  }
  const window = items.slice(start);
  const limit = query.limit ?? window.length;
  const sliced = window.slice(0, limit);
  const last = sliced[sliced.length - 1];
  return {
    items: sliced,
    next_cursor: window.length > sliced.length && last ? last.id : null,
  };
}

export function startMockSignalStream(
  symbol: string,
  lastPrice: () => number,
  onEvent: (event: SignalWsEvent) => void,
  initial: Signal[] = [],
): () => void {
  const { book, signals } = getUniverse(symbol, lastPrice());
  let seq = 200;
  const live = new Map<string, Signal>([...initial, ...signals].map((s) => [s.id, s]));

  const upsert = () => {
    seq += 1;
    const template = signals[seq % signals.length];
    const price = lastPrice();
    const width = Math.max(price * 0.0024, 0.04);
    const side = template.side;
    const next: Signal = {
      ...template,
      id: `sig_${symbol}_live_${seq}`,
      ts_ms: Date.now(),
      entry: price,
      stop: side === "long" ? price - width : price + width,
      target: side === "long" ? price + width * 2.15 : price - width * 2.15,
      status: "ACTIVE",
      realized_r: null,
      exit_price: null,
      closed_ts_ms: null,
      confidence: seq % 4 === 0 ? 0.84 : template.confidence,
      trigger_event_ids: template.trigger_event_ids.length
        ? template.trigger_event_ids
        : book.fvgs[0]
          ? [book.fvgs[0].id]
          : [],
    };
    live.set(next.id, next);
    onEvent({ type: "signal.upsert", signal: next });
  };

  const flipStatus = () => {
    const active = [...live.values()].filter((s) => s.status === "ACTIVE");
    if (!active.length) return;
    const signal = active[seq % active.length];
    const status: SignalStatus = SIGNAL_STATUSES[(seq % 3) + 1] ?? "TP_HIT";
    const closed = status === "TP_HIT" || status === "SL_HIT";
    const updated: Signal = {
      ...signal,
      status,
      realized_r: status === "TP_HIT" ? 1.85 : status === "SL_HIT" ? -1.0 : null,
      exit_price: closed ? (status === "TP_HIT" ? signal.target : signal.stop) : null,
      closed_ts_ms: closed ? Date.now() : null,
    };
    live.set(updated.id, updated);
    onEvent({ type: "signal.status", signal: updated });
  };

  const first = setTimeout(upsert, 2800);
  const upsertTimer = setInterval(upsert, 3600);
  const statusTimer = setInterval(flipStatus, 5400);
  return () => {
    clearTimeout(first);
    clearInterval(upsertTimer);
    clearInterval(statusTimer);
  };
}
