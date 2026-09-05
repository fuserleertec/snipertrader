import { inferAssetClass } from "../constants";
import { sessionWindows } from "../sessions";
import { explain, factorsForSetup } from "../factors";
import type { FVGZone, MssEvent, OrderBlock, PatternBook, SetupType, Signal, SweepEvent } from "../types";

const cache = new Map<string, { book: PatternBook; signals: Signal[]; price: number }>();

function id(kind: string, symbol: string, tag: string): string {
  return `${kind}_${symbol}_${tag}`;
}

export function buildPatternBook(symbol: string, price: number, now: number): PatternBook {
  const asset_class = inferAssetClass(symbol);
  const bar = 60_000;

  const fvgBull: FVGZone = {
    schema_version: "1.1",
    id: id("fvg", symbol, "bull"),
    symbol,
    asset_class,
    direction: "bullish",
    high: price * 0.9992,
    low: price * 0.9968,
    mitigated: false,
    created_ts_ms: now - 48 * bar,
    ttl_seconds: 172800,
  };
  const fvgBear: FVGZone = {
    schema_version: "1.1",
    id: id("fvg", symbol, "bear"),
    symbol,
    asset_class,
    direction: "bearish",
    high: price * 1.0038,
    low: price * 1.0012,
    mitigated: false,
    created_ts_ms: now - 72 * bar,
    ttl_seconds: 172800,
  };
  const fvgMit: FVGZone = {
    schema_version: "1.1",
    id: id("fvg", symbol, "mit"),
    symbol,
    asset_class,
    direction: "bullish",
    high: price * 0.9955,
    low: price * 0.9938,
    mitigated: true,
    created_ts_ms: now - 110 * bar,
    ttl_seconds: 86400,
  };

  const obBull: OrderBlock = {
    schema_version: "1.1",
    id: id("ob", symbol, "bull"),
    symbol,
    asset_class,
    direction: "bullish",
    high: price * 0.9984,
    low: price * 0.995,
    created_ts_ms: now - 90 * bar,
    mitigated: false,
    ttl_seconds: 172800,
    timeframe: "5m",
    displacement_ts_ms: now - 86 * bar,
    origin_open: price * 0.9954,
    origin_close: price * 0.998,
  };
  const obBear: OrderBlock = {
    schema_version: "1.1",
    id: id("ob", symbol, "bear"),
    symbol,
    asset_class,
    direction: "bearish",
    high: price * 1.0062,
    low: price * 1.003,
    created_ts_ms: now - 64 * bar,
    mitigated: false,
    ttl_seconds: 172800,
    timeframe: "5m",
    displacement_ts_ms: now - 60 * bar,
    origin_open: price * 1.0058,
    origin_close: price * 1.0034,
  };

  const sweepSell: SweepEvent = {
    schema_version: "1.1",
    id: id("sweep", symbol, "sell"),
    symbol,
    asset_class,
    side: "sell",
    swept_level: price * 1.0046,
    reclaim: true,
    ts_ms: now - 40 * bar,
  };
  const sweepBuy: SweepEvent = {
    schema_version: "1.1",
    id: id("sweep", symbol, "buy"),
    symbol,
    asset_class,
    side: "buy",
    swept_level: price * 0.9952,
    reclaim: true,
    ts_ms: now - 36 * bar,
  };

  const mssBull: MssEvent = {
    schema_version: "1.1",
    id: id("mss", symbol, "bull"),
    symbol,
    asset_class,
    ts_ms: now - 28 * bar,
    direction: "bullish",
    broken_level: price * 1.001,
    swing_high: price * 1.001,
    swing_low: price * 0.9952,
    trigger_sweep_id: sweepSell.id,
    trigger_sweep_side: "sell",
    timeframe: "5m",
    confirmed: true,
  };
  const mssBear: MssEvent = {
    schema_version: "1.1",
    id: id("mss", symbol, "bear"),
    symbol,
    asset_class,
    ts_ms: now - 22 * bar,
    direction: "bearish",
    broken_level: price * 0.998,
    swing_high: price * 1.0046,
    swing_low: price * 0.998,
    trigger_sweep_id: sweepBuy.id,
    trigger_sweep_side: "buy",
    timeframe: "5m",
    confirmed: true,
  };

  return {
    fvgs: [fvgBull, fvgBear, fvgMit],
    obs: [obBull, obBear],
    sweeps: [sweepSell, sweepBuy],
    mss: [mssBull, mssBear],
  };
}

function signalOf(
  symbol: string,
  price: number,
  now: number,
  setup_type: SetupType,
  side: "long" | "short",
  seq: number,
  trigger_event_ids: string[],
  confidence: number,
): Signal {
  const width = Math.max(price * 0.0024, 0.04);
  const entry = price;
  const stop = side === "long" ? entry - width : entry + width;
  const target = side === "long" ? entry + width * 2.15 : entry - width * 2.15;
  return {
    id: `sig_${symbol}_${setup_type}_${seq}`,
    ts_ms: now - seq * 4000,
    symbol,
    asset_class: inferAssetClass(symbol),
    setup_type,
    side,
    entry,
    stop,
    target,
    status: "ACTIVE",
    confidence,
    timeframe: "5m",
    ref_session: inferAssetClass(symbol) === "crypto" ? "ny_am" : "rth",
    trigger_event_ids,
    ...explain(factorsForSetup(setup_type), Math.round(confidence * 100)),
  };
}

export function signalsFromBook(symbol: string, price: number, book: PatternBook, now: number): Signal[] {
  const fvgBull = book.fvgs.find((z) => z.id.endsWith("_bull"));
  const fvgBear = book.fvgs.find((z) => z.id.endsWith("_bear"));
  const obBull = book.obs.find((z) => z.id.endsWith("_bull"));
  const sweepBuy = book.sweeps.find((z) => z.side === "buy");
  const sweepSell = book.sweeps.find((z) => z.side === "sell");
  const mssBull = book.mss.find((z) => z.direction === "bullish");

  return [
    signalOf(symbol, price, now, "sweep_reclaim", "long", 1, [sweepBuy?.id, mssBull?.id].filter(Boolean) as string[], 0.86),
    signalOf(symbol, price, now, "fvg_entry", "long", 2, [fvgBull?.id].filter(Boolean) as string[], 0.74),
    signalOf(symbol, price, now, "po3_judas", "long", 3, [sweepSell?.id, mssBull?.id].filter(Boolean) as string[], 0.69),
    signalOf(symbol, price, now, "sd_extension_fade", "short", 4, [fvgBear?.id].filter(Boolean) as string[], 0.73),
    signalOf(symbol, price, now, "vwap_pullback_cont", "long", 5, [obBull?.id, fvgBull?.id].filter(Boolean) as string[], 0.7),
    signalOf(symbol, price, now, "avwap_ob_confluence", "long", 6, [obBull?.id].filter(Boolean) as string[], 0.68),
  ];
}

export function getUniverse(symbol: string, price: number): { book: PatternBook; signals: Signal[] } {
  const hit = cache.get(symbol);
  if (hit) return hit;
  const now = Date.now();
  const book = buildPatternBook(symbol, price, now);
  const signals = signalsFromBook(symbol, price, book, now);
  const next = { book, signals, price };
  cache.set(symbol, next);
  return next;
}

export function dropUniverse(symbol: string): void {
  cache.delete(symbol);
}

export function asiaWindow(now: number): { start_ms: number; end_ms: number } | null {
  const wins = sessionWindows("crypto", now).filter((w) => w.session_type === "asia");
  const active = wins.find((w) => now >= w.start_ms && now < w.end_ms);
  if (active) return { start_ms: active.start_ms, end_ms: active.end_ms };
  const last = wins.filter((w) => w.end_ms <= now).sort((a, b) => b.end_ms - a.end_ms)[0];
  return last ? { start_ms: last.start_ms, end_ms: last.end_ms } : null;
}
