import { inferAssetClass } from "./constants";
import type {
  AnchoredVwap,
  FVGZone,
  MssEvent,
  OrderBlock,
  OverlayEvent,
  OverlayKind,
  PatternBook,
  SweepEvent,
  VWAPValues,
  VolumeProfile,
} from "./types";

const EMPTY: PatternBook = { fvgs: [], obs: [], sweeps: [], mss: [] };

/**
 * Future Data Eng seed+pubsub (not live yet).
 * Kafka: sweep_events, fvg_zones, mss_events, order_block_zones.
 * Redis: sweep|fvg|mss|ob:{symbol}:{id}
 */
export const FUTURE_PATTERN_WS: Record<OverlayKind, string> = {
  fvg: "/v1/ws/fvg",
  order_block: "/v1/ws/ob",
  sweep: "/v1/ws/sweep",
  mss: "/v1/ws/mss",
};

function upsertById<T extends { id: string }>(rows: T[], next: T): T[] {
  return [next, ...rows.filter((row) => row.id !== next.id)];
}

export function bookFromOverlayEvents(events: OverlayEvent[]): PatternBook {
  const book: PatternBook = { fvgs: [], obs: [], sweeps: [], mss: [] };
  for (const event of events) applyOverlayEvent(book, event);
  return book;
}

export function overlayEventsFromBook(book: PatternBook): OverlayEvent[] {
  return [
    ...book.fvgs.map((payload) => ({ kind: "fvg" as const, payload })),
    ...book.obs.map((payload) => ({ kind: "order_block" as const, payload })),
    ...book.sweeps.map((payload) => ({ kind: "sweep" as const, payload })),
    ...book.mss.map((payload) => ({ kind: "mss" as const, payload })),
  ];
}

export function applyOverlayEvent(book: PatternBook, event: OverlayEvent): PatternBook {
  if (event.kind === "fvg") book.fvgs = upsertById(book.fvgs, event.payload);
  else if (event.kind === "order_block") book.obs = upsertById(book.obs, event.payload);
  else if (event.kind === "sweep") book.sweeps = upsertById(book.sweeps, event.payload);
  else book.mss = upsertById(book.mss, event.payload);
  return book;
}

export function emptyPatternBook(): PatternBook {
  return { fvgs: [], obs: [], sweeps: [], mss: [] };
}

function isObj(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object";
}

function str(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asset(value: unknown, symbol: string): FVGZone["asset_class"] {
  if (value === "crypto" || value === "equity" || value === "futures") return value;
  return inferAssetClass(symbol);
}

/** Copy only `/schemas/fvg_zone.schema.json` fields. */
export function normalizeFvg(value: unknown): FVGZone | null {
  if (!isObj(value)) return null;
  const id = str(value.id);
  const symbol = str(value.symbol);
  const high = num(value.high);
  const low = num(value.low);
  const created = num(value.created_ts_ms);
  if (!id || !symbol || high == null || low == null || created == null) return null;
  if (value.direction !== "bullish" && value.direction !== "bearish") return null;
  const row: FVGZone = {
    schema_version: "1.1",
    id,
    symbol,
    asset_class: asset(value.asset_class, symbol),
    direction: value.direction,
    high,
    low,
    created_ts_ms: created,
  };
  if (typeof value.mitigated === "boolean") row.mitigated = value.mitigated;
  if (typeof value.ttl_seconds === "number") row.ttl_seconds = value.ttl_seconds;
  return row;
}

/** Copy only `/schemas/order_block.schema.json` fields. */
export function normalizeOrderBlock(value: unknown): OrderBlock | null {
  if (!isObj(value)) return null;
  const id = str(value.id);
  const symbol = str(value.symbol);
  const high = num(value.high);
  const low = num(value.low);
  const created = num(value.created_ts_ms);
  if (!id || !symbol || high == null || low == null || created == null) return null;
  if (value.direction !== "bullish" && value.direction !== "bearish") return null;
  const row: OrderBlock = {
    schema_version: "1.1",
    id,
    symbol,
    asset_class: asset(value.asset_class, symbol),
    direction: value.direction,
    high,
    low,
    created_ts_ms: created,
  };
  if (typeof value.mitigated === "boolean") row.mitigated = value.mitigated;
  if (typeof value.ttl_seconds === "number") row.ttl_seconds = value.ttl_seconds;
  if (value.timeframe === "1m" || value.timeframe === "5m" || value.timeframe === "15m" || value.timeframe === "1h" || value.timeframe === "4h") {
    row.timeframe = value.timeframe;
  }
  if (typeof value.displacement_ts_ms === "number") row.displacement_ts_ms = value.displacement_ts_ms;
  if (typeof value.origin_open === "number") row.origin_open = value.origin_open;
  if (typeof value.origin_close === "number") row.origin_close = value.origin_close;
  return row;
}

/** Copy only `/schemas/sweep_event.schema.json` fields. */
export function normalizeSweep(value: unknown): SweepEvent | null {
  if (!isObj(value)) return null;
  const id = str(value.id);
  const symbol = str(value.symbol);
  const swept = num(value.swept_level);
  const ts = num(value.ts_ms);
  if (!id || !symbol || swept == null || ts == null) return null;
  if (value.side !== "buy" && value.side !== "sell") return null;
  const row: SweepEvent = {
    schema_version: "1.1",
    id,
    symbol,
    asset_class: asset(value.asset_class, symbol),
    side: value.side,
    swept_level: swept,
    ts_ms: ts,
  };
  if (value.reclaim === true || value.reclaim === false || value.reclaim === null) row.reclaim = value.reclaim;
  if (value.volume_profile === "aggressive" || value.volume_profile === "low_volume") {
    row.volume_profile = value.volume_profile;
  }
  if (typeof value.delta_divergence === "boolean") row.delta_divergence = value.delta_divergence;
  if (value.time_to_reclaim_ms === null || typeof value.time_to_reclaim_ms === "number") {
    row.time_to_reclaim_ms = value.time_to_reclaim_ms;
  }
  if (typeof value.confirmed === "boolean") row.confirmed = value.confirmed;
  return row;
}

/** Copy only `/schemas/mss_event.schema.json` fields. */
export function normalizeMss(value: unknown): MssEvent | null {
  if (!isObj(value)) return null;
  const id = str(value.id);
  const symbol = str(value.symbol);
  const ts = num(value.ts_ms);
  const broken = num(value.broken_level);
  const trigger = str(value.trigger_sweep_id);
  if (!id || !symbol || ts == null || broken == null || !trigger) return null;
  if (value.direction !== "bullish" && value.direction !== "bearish") return null;
  if (value.trigger_sweep_side !== "buy" && value.trigger_sweep_side !== "sell") return null;
  const row: MssEvent = {
    schema_version: "1.1",
    id,
    symbol,
    asset_class: asset(value.asset_class, symbol),
    ts_ms: ts,
    direction: value.direction,
    broken_level: broken,
    swing_high: value.swing_high === null ? null : num(value.swing_high),
    swing_low: value.swing_low === null ? null : num(value.swing_low),
    trigger_sweep_id: trigger,
    trigger_sweep_side: value.trigger_sweep_side,
  };
  if (value.timeframe === "1m" || value.timeframe === "5m" || value.timeframe === "15m") row.timeframe = value.timeframe;
  if (typeof value.confirmed === "boolean") row.confirmed = value.confirmed;
  return row;
}

/**
 * Adapter for a future `WS /v1/ws/{fvg|ob|sweep|mss}?symbol=` frame.
 * `hint` is the socket path kind so FVG vs OB (same high/low keys) stay exact.
 */
export function parseOverlayFrame(value: unknown, hint?: OverlayKind): OverlayEvent | null {
  if (hint === "fvg") {
    const payload = normalizeFvg(value);
    return payload ? { kind: "fvg", payload } : null;
  }
  if (hint === "order_block") {
    const payload = normalizeOrderBlock(value);
    return payload ? { kind: "order_block", payload } : null;
  }
  if (hint === "sweep") {
    const payload = normalizeSweep(value);
    return payload ? { kind: "sweep", payload } : null;
  }
  if (hint === "mss") {
    const payload = normalizeMss(value);
    return payload ? { kind: "mss", payload } : null;
  }

  const sweep = normalizeSweep(value);
  if (sweep) return { kind: "sweep", payload: sweep };
  const mss = normalizeMss(value);
  if (mss) return { kind: "mss", payload: mss };
  if (isObj(value) && (typeof value.origin_open === "number" || typeof value.displacement_ts_ms === "number")) {
    const ob = normalizeOrderBlock(value);
    if (ob) return { kind: "order_block", payload: ob };
  }
  const fvg = normalizeFvg(value);
  if (fvg) return { kind: "fvg", payload: fvg };
  const ob = normalizeOrderBlock(value);
  if (ob) return { kind: "order_block", payload: ob };
  return null;
}

/** Map DE PR #5 AVWAP (`vwap_value`) onto the Phase 1 VWAPValues chart shape. */
export function avwapToVwapValues(raw: AnchoredVwap): VWAPValues {
  const sigma = Math.abs(raw.bands.plus_1_sigma - raw.vwap_value);
  return {
    schema_version: "1.1",
    symbol: raw.symbol,
    asset_class: raw.asset_class || inferAssetClass(raw.symbol),
    anchor_type: "weekly",
    session_type: null,
    anchor_start_ms: raw.anchor_time,
    lookback_periods: null,
    vwap: raw.vwap_value,
    sigma,
    band_m3: raw.bands.minus_3_sigma,
    band_m2: raw.bands.minus_2_sigma,
    band_m1: raw.bands.minus_1_sigma,
    band_p1: raw.bands.plus_1_sigma,
    band_p2: raw.bands.plus_2_sigma,
    band_p3: raw.bands.plus_3_sigma,
    cum_volume: 0,
    n_obs: 0,
    updated_ts_ms: raw.anchor_time,
  };
}

export function isAnchoredVwap(value: unknown): value is AnchoredVwap {
  if (!isObj(value)) return false;
  return typeof value.vwap_value === "number" && typeof value.anchor_id === "string" && isObj(value.bands);
}

export function isKillZone(value: unknown): boolean {
  if (!isObj(value)) return false;
  return typeof value.kill_zone === "string" && typeof value.active === "boolean";
}

export function isVolumeProfile(value: unknown): value is VolumeProfile {
  if (!isObj(value)) return false;
  return (
    typeof value.symbol === "string" &&
    typeof value.poc === "number" &&
    Array.isArray(value.high_volume_nodes)
  );
}

export { EMPTY as EMPTY_PATTERN_BOOK };
