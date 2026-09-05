import { inferAssetClass } from "./constants";
import type {
  AnchoredVwap,
  FVGZone,
  MssEvent,
  OrderBlock,
  OverlayEvent,
  PatternBook,
  SweepEvent,
  VWAPValues,
} from "./types";

const EMPTY: PatternBook = { fvgs: [], obs: [], sweeps: [], mss: [] };

function upsertById<T extends { id: string }>(rows: T[], next: T): T[] {
  return [next, ...rows.filter((row) => row.id !== next.id)];
}

/** Chart adapter: typed overlay events → PatternBook (primitives + setMarkers). */
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

export function parseOverlayFrame(value: unknown): OverlayEvent | null {
  if (!isObj(value)) return null;
  if (typeof value.high === "number" && typeof value.low === "number" && typeof value.created_ts_ms === "number") {
    if (value.direction === "bullish" || value.direction === "bearish") {
      const zone = value as unknown as FVGZone | OrderBlock;
      if (typeof value.origin_open === "number" || typeof value.displacement_ts_ms === "number") {
        return { kind: "order_block", payload: zone as OrderBlock };
      }
      if (typeof value.id === "string") {
        const looksOb = typeof (value as { origin_close?: unknown }).origin_close === "number";
        return looksOb
          ? { kind: "order_block", payload: zone as OrderBlock }
          : { kind: "fvg", payload: zone as FVGZone };
      }
    }
  }
  if (typeof value.swept_level === "number" && (value.side === "buy" || value.side === "sell")) {
    return { kind: "sweep", payload: value as unknown as SweepEvent };
  }
  if (typeof value.broken_level === "number" && (value.direction === "bullish" || value.direction === "bearish")) {
    return { kind: "mss", payload: value as unknown as MssEvent };
  }
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

export { EMPTY as EMPTY_PATTERN_BOOK };
