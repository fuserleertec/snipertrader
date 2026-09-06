import { DESK_SYMBOL_LIMIT, inferAssetClass, SESSION_TYPES } from "./constants";
import { isInactiveRow, readPublishExplain } from "./bind";
import type {
  SessionType,
  Signal,
  SignalSide,
  SignalStatus,
  SignalWsEvent,
  SetupType,
  Timeframe,
} from "./types";

function fmtPx(n: number): string {
  return n >= 1000 ? n.toFixed(1) : n.toFixed(2);
}

/** Display-only. zone_low / zone_high are derived from stop/entry — not wire fields. */
export function zoneLowHigh(signal: Signal): { zone_low: number; zone_high: number } {
  return {
    zone_low: Math.min(signal.stop, signal.entry),
    zone_high: Math.max(signal.stop, signal.entry),
  };
}

export function riskReward(signal: Signal): number {
  const risk = Math.abs(signal.entry - signal.stop);
  const reward = Math.abs(signal.target - signal.entry);
  return risk > 0 ? reward / risk : 0;
}

export function zoneLabel(signal: Signal): string {
  const { zone_low, zone_high } = zoneLowHigh(signal);
  return `${fmtPx(zone_low)}–${fmtPx(zone_high)}  E ${fmtPx(signal.entry)}  S ${fmtPx(signal.stop)}  T ${fmtPx(signal.target)}`;
}

/** Wire field only — never derived from entry/stop/target. */
export function realizedMultiple(signal: Signal): number | null {
  if (signal.status !== "TP_HIT" && signal.status !== "SL_HIT") return null;
  return typeof signal.realized_r === "number" && Number.isFinite(signal.realized_r) ? signal.realized_r : null;
}

export function outcomeLabel(signal: Signal): string {
  return signal.status;
}

function numOr(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function optionalNum(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readSessionType(value: unknown): SessionType | null | undefined {
  if (value == null) return value === null ? null : undefined;
  if (typeof value === "string" && (SESSION_TYPES as string[]).includes(value)) {
    return value as SessionType;
  }
  return undefined;
}

function statusClosed(status: unknown): boolean {
  return status === "TP_HIT" || status === "SL_HIT";
}

export function normalizeSignal(value: unknown): Signal | null {
  if (!value || typeof value !== "object") return null;
  const s = value as Record<string, unknown>;
  if (isInactiveRow(s)) return null;
  if (typeof s.id !== "string" || typeof s.symbol !== "string" || typeof s.setup_type !== "string") return null;
  if (s.side !== "long" && s.side !== "short") return null;
  const ts = typeof s.ts_ms === "number" ? s.ts_ms : Date.now();
  const explain = readPublishExplain(s);
  return {
    id: s.id,
    ts_ms: ts,
    symbol: s.symbol,
    asset_class: typeof s.asset_class === "string" ? (s.asset_class as Signal["asset_class"]) : inferAssetClass(s.symbol),
    setup_type: s.setup_type as SetupType,
    side: s.side as SignalSide,
    entry: numOr(s.entry, 0),
    stop: numOr(s.stop, 0),
    target: numOr(s.target, 0),
    status: (typeof s.status === "string" ? s.status : "ACTIVE") as SignalStatus,
    confidence: numOr(s.confidence, 0),
    timeframe: (typeof s.timeframe === "string" ? s.timeframe : "5m") as Timeframe,
    ref_session: (typeof s.ref_session === "string" ? s.ref_session : "ny_am") as Signal["ref_session"],
    ref_vwap: optionalNum(s.ref_vwap),
    trigger_event_ids: Array.isArray(s.trigger_event_ids)
      ? s.trigger_event_ids.filter((x): x is string => typeof x === "string")
      : [],
    session_type: readSessionType(s.session_type),
    position_size: optionalNum(s.position_size),
    contributing_factors: explain.contributing_factors,
    factor_breakdown: explain.factor_breakdown,
    ensemble_score: explain.ensemble_score,
    rank_components: explain.rank_components,
    category: explain.category,
    realized_r: statusClosed(s.status) ? optionalNum(s.realized_r) : null,
    exit_price: statusClosed(s.status) ? optionalNum(s.exit_price) : null,
    closed_ts_ms: statusClosed(s.status) ? optionalNum(s.closed_ts_ms) : null,
  };
}

export function isSignal(value: unknown): value is Signal {
  return normalizeSignal(value) != null;
}

export function isSignalWsEvent(value: unknown): value is SignalWsEvent {
  if (!value || typeof value !== "object") return false;
  const ev = value as SignalWsEvent;
  return (ev.type === "signal.upsert" || ev.type === "signal.status") && normalizeSignal(ev.signal) != null;
}

export function upsertSignal(prev: Signal[], signal: Signal): Signal[] {
  const next = [signal, ...prev.filter((row) => row.id !== signal.id)];
  next.sort((a, b) => b.ts_ms - a.ts_ms);
  return next.slice(0, DESK_SYMBOL_LIMIT * 12);
}
