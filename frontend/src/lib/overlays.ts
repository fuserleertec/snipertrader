import { inferAssetClass } from "./constants";
import type {
  AnchoredVwap,
  FVGZone,
  KillZoneEvent,
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
 * Data Eng PR #5 overlay sockets. On connect: SCAN `{prefix}:{symbol}:*`
 * seed frames, then pub/sub `{prefix}:{symbol}`. Frames are exact
 * `/schemas` 1.1 JSON (not wrapped). Kafka: sweep_events, fvg_zones,
 * mss_events, order_block_zones. Redis: sweep|fvg|mss|ob:{symbol}:{id}
 */
export const PATTERN_WS: Record<OverlayKind, string> = {
  fvg: "/v1/ws/fvg",
  order_block: "/v1/ws/ob",
  sweep: "/v1/ws/sweep",
  mss: "/v1/ws/mss",
};

/** @deprecated Use PATTERN_WS — same paths. */
export const FUTURE_PATTERN_WS = PATTERN_WS;

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
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** DE list/WS sometimes wraps the frame as `{ value: { ... } }`. */
function unwrapValue(value: unknown): unknown {
  if (isObj(value) && isObj(value.value)) return value.value;
  return value;
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
 * Adapter for `WS /v1/ws/{fvg|ob|sweep|mss}?symbol=` frames.
 * Input is the raw `/schemas` 1.1 object (no wrapper envelope).
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

/** DE Phase 2 AVWAP → Phase 1 VWAPValues chart shape. Copies only contract fields. */
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

function readBands(value: unknown): AnchoredVwap["bands"] | null {
  if (!isObj(value)) return null;
  const plus_1_sigma = num(value.plus_1_sigma);
  const plus_2_sigma = num(value.plus_2_sigma);
  const plus_3_sigma = num(value.plus_3_sigma);
  const minus_1_sigma = num(value.minus_1_sigma);
  const minus_2_sigma = num(value.minus_2_sigma);
  const minus_3_sigma = num(value.minus_3_sigma);
  if (
    plus_1_sigma == null ||
    plus_2_sigma == null ||
    plus_3_sigma == null ||
    minus_1_sigma == null ||
    minus_2_sigma == null ||
    minus_3_sigma == null
  ) {
    return null;
  }
  return { plus_1_sigma, plus_2_sigma, plus_3_sigma, minus_1_sigma, minus_2_sigma, minus_3_sigma };
}

/** DE Phase 2: `anchor_id`, `symbol`, `anchor_time`, `anchor_price`, `vwap_value`, `bands`, `asset_class`. */
export function normalizeAvwap(value: unknown): AnchoredVwap | null {
  value = unwrapValue(value);
  if (!isObj(value)) return null;
  const anchor_id = str(value.anchor_id);
  const symbol = str(value.symbol);
  const anchor_time = num(value.anchor_time);
  const anchor_price = num(value.anchor_price);
  const vwap_value = num(value.vwap_value);
  const bands = readBands(value.bands);
  if (!anchor_id || !symbol || anchor_time == null || anchor_price == null || vwap_value == null || !bands) {
    return null;
  }
  return {
    anchor_id,
    symbol,
    anchor_time,
    anchor_price,
    vwap_value,
    bands,
    asset_class: asset(value.asset_class, symbol),
  };
}

export function isAnchoredVwap(value: unknown): value is AnchoredVwap {
  return normalizeAvwap(value) != null;
}

/** DE Phase 2: `symbol`, `kill_zone`, `start_time`, `end_time`, `active`, `asset_class`. */
export function normalizeKillZone(value: unknown): KillZoneEvent | null {
  value = unwrapValue(value);
  if (!isObj(value)) return null;
  const symbol = str(value.symbol);
  const kill_zone = str(value.kill_zone);
  const start_time = num(value.start_time);
  const end_time = num(value.end_time);
  if (!symbol || !kill_zone || start_time == null || end_time == null || typeof value.active !== "boolean") {
    return null;
  }
  if (
    kill_zone !== "asia" &&
    kill_zone !== "london" &&
    kill_zone !== "ny_am" &&
    kill_zone !== "ny_pm" &&
    kill_zone !== "rth" &&
    kill_zone !== "eth" &&
    kill_zone !== "globex"
  ) {
    return null;
  }
  return {
    symbol,
    kill_zone,
    start_time,
    end_time,
    active: value.active,
    asset_class: asset(value.asset_class, symbol),
  };
}

export function isKillZone(value: unknown): boolean {
  return normalizeKillZone(value) != null;
}

function readNodes(value: unknown): VolumeProfile["high_volume_nodes"] {
  if (!Array.isArray(value)) return [];
  const out: VolumeProfile["high_volume_nodes"] = [];
  for (const item of value) {
    if (!isObj(item)) continue;
    const price = num(item.price);
    const volume = num(item.volume);
    if (price == null || volume == null) continue;
    out.push({ price, volume });
  }
  return out;
}

/** DE Phase 2: `symbol`, `session_type`, `high_volume_nodes`, `low_volume_nodes`, `poc`, `timestamp`. */
export function normalizeVolumeProfile(value: unknown): VolumeProfile | null {
  value = unwrapValue(value);
  if (!isObj(value)) return null;
  if (Array.isArray(value.profiles)) {
    for (const row of value.profiles) {
      const inner = isObj(row) ? normalizeVolumeProfile(row.value ?? row) : null;
      if (inner) return inner;
    }
    return null;
  }
  const symbol = str(value.symbol);
  const poc = num(value.poc);
  const timestamp = num(value.timestamp);
  const session_type = str(value.session_type);
  if (!symbol || poc == null || timestamp == null || !session_type) return null;
  if (
    session_type !== "asia" &&
    session_type !== "london" &&
    session_type !== "ny_am" &&
    session_type !== "ny_pm" &&
    session_type !== "rth" &&
    session_type !== "eth" &&
    session_type !== "globex"
  ) {
    return null;
  }
  return {
    symbol,
    session_type,
    high_volume_nodes: readNodes(value.high_volume_nodes),
    low_volume_nodes: readNodes(value.low_volume_nodes),
    poc,
    timestamp,
  };
}

export function isVolumeProfile(value: unknown): value is VolumeProfile {
  return normalizeVolumeProfile(value) != null;
}

export { EMPTY as EMPTY_PATTERN_BOOK };
