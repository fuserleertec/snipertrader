import { inferAssetClass, SETUP_TYPES, SIGNAL_STATUSES, sessionsForAsset } from "../constants";
import type {
  AssetClass,
  SessionType,
  Signal,
  SignalListQuery,
  SignalListResponse,
  SignalStatus,
  SignalWsEvent,
  Timeframe,
} from "../types";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h"];

function makeSignal(
  symbol: string,
  asset_class: AssetClass,
  lastClose: number,
  now_ms: number,
  seq: number,
  status: SignalStatus = "ACTIVE",
): Signal {
  const side = seq % 2 === 0 ? "long" : "short";
  const width = Math.max(lastClose * 0.0025, 0.05);
  const entry = lastClose;
  const stop = side === "long" ? entry - width : entry + width;
  const target = side === "long" ? entry + width * 2.2 : entry - width * 2.2;
  const sessions = sessionsForAsset(asset_class);
  const ref_session: SessionType = sessions[seq % sessions.length] ?? "ny_am";
  return {
    id: `sig_${symbol}_${seq}`,
    ts_ms: now_ms,
    symbol,
    asset_class,
    setup_type: SETUP_TYPES[seq % SETUP_TYPES.length],
    side,
    entry,
    stop,
    target,
    status,
    confidence: Number((0.55 + ((seq * 7) % 40) / 100).toFixed(2)),
    timeframe: TIMEFRAMES[seq % TIMEFRAMES.length],
    ref_session,
    trigger_event_ids: [`evt_${symbol}_${seq}`],
  };
}

function matches(signal: Signal, query: SignalListQuery): boolean {
  if (query.symbol && signal.symbol !== query.symbol) return false;
  if (query.status && signal.status !== query.status) return false;
  if (query.setup_type && signal.setup_type !== query.setup_type) return false;
  if (query.from_ts != null && signal.ts_ms < query.from_ts) return false;
  if (query.to_ts != null && signal.ts_ms > query.to_ts) return false;
  return true;
}

/** Mock `GET /signals` → `{ items, next_cursor }`. */
export function mockListSignals(query: SignalListQuery, lastPrice: number): SignalListResponse {
  const symbol = query.symbol ?? "BTCUSDT";
  const asset = inferAssetClass(symbol);
  const limit = query.limit ?? 20;
  const now = Date.now();
  const items: Signal[] = [];
  for (let seq = 1; seq <= limit + 4; seq++) {
    const status = SIGNAL_STATUSES[seq % 7 === 0 ? 1 : seq % 11 === 0 ? 2 : 0];
    const signal = makeSignal(symbol, asset, lastPrice, now - seq * 3500, seq, status);
    if (matches(signal, query)) items.push(signal);
    if (items.length >= limit) break;
  }
  return {
    items,
    next_cursor: items.length >= limit ? `cursor_${symbol}_${items[items.length - 1]?.id}` : null,
  };
}

/**
 * Mock planned `WS /ws/signals` envelopes:
 * `{ "type": "signal.upsert"|"signal.status", "signal": Signal }`
 */
export function startMockSignalStream(
  symbol: string,
  lastPrice: () => number,
  onEvent: (event: SignalWsEvent) => void,
  initial: Signal[] = [],
): () => void {
  const asset = inferAssetClass(symbol);
  let seq = 100;
  const live = new Map<string, Signal>(initial.map((s) => [s.id, s]));

  const upsert = () => {
    seq += 1;
    const signal = makeSignal(symbol, asset, lastPrice(), Date.now(), seq, "ACTIVE");
    live.set(signal.id, signal);
    onEvent({ type: "signal.upsert", signal });
  };

  const flipStatus = () => {
    const active = [...live.values()].filter((s) => s.status === "ACTIVE");
    if (!active.length) return;
    const signal = active[seq % active.length];
    const next: SignalStatus =
      seq % 3 === 0 ? "TP_HIT" : seq % 3 === 1 ? "SL_HIT" : "CANCELLED";
    const updated: Signal = { ...signal, status: next };
    live.set(updated.id, updated);
    onEvent({ type: "signal.status", signal: updated });
  };

  upsert();
  const upsertTimer = setInterval(upsert, 3200);
  const statusTimer = setInterval(flipStatus, 5100);
  return () => {
    clearInterval(upsertTimer);
    clearInterval(statusTimer);
  };
}
