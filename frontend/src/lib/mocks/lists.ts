/**
 * Dynamic paper generators for Quant/DE list contracts.
 * SETUP_UNIVERSE is provisional and mock-only. When DE is contracted,
 * Quant ranks top-10 inside GET /v1/universe/top. The UI never imports
 * this array as a P0/P4 list — it only displays API `items`.
 */
import {
  DESK_SYMBOL_LIMIT,
  ENSEMBLE_LIMIT,
  inferAssetClass,
  LIST_REFRESH_SEC,
  seedPrice,
  SETUP_TYPES,
} from "../constants";
import type {
  AssetClass,
  CategorizedPickItem,
  CategorizedPicksResponse,
  EnsemblePickItem,
  EnsemblePicksResponse,
  PickCategory,
  RankComponents,
  SetupType,
  UniverseTopResponse,
} from "../types";
import { getUniverse, MOCK_NOW } from "./universe";

/**
 * Provisional paper scan set (DE-authoritative later). Not a P0/P4 UI array —
 * mock ranking shuffles and scores this set each cycle.
 */
export const SETUP_UNIVERSE: { symbol: string; asset_class: AssetClass; name: string }[] = [
  { symbol: "ES", asset_class: "futures", name: "E-mini S&P 500" },
  { symbol: "CL", asset_class: "futures", name: "WTI Crude" },
  { symbol: "GC", asset_class: "futures", name: "Gold" },
  { symbol: "NQ", asset_class: "futures", name: "Nasdaq 100" },
  { symbol: "NVDA", asset_class: "equity", name: "NVIDIA Corp" },
  { symbol: "AAPL", asset_class: "equity", name: "Apple Inc" },
  { symbol: "TSLA", asset_class: "equity", name: "Tesla Inc" },
  { symbol: "MSFT", asset_class: "equity", name: "Microsoft Corp" },
  { symbol: "META", asset_class: "equity", name: "Meta Platforms" },
  { symbol: "AMZN", asset_class: "equity", name: "Amazon.com" },
  { symbol: "AMD", asset_class: "equity", name: "Advanced Micro Devices" },
  { symbol: "AVGO", asset_class: "equity", name: "Broadcom Inc" },
  { symbol: "PLTR", asset_class: "equity", name: "Palantir Technologies" },
  { symbol: "CRWD", asset_class: "equity", name: "CrowdStrike" },
  { symbol: "BTCUSDT", asset_class: "crypto", name: "Bitcoin" },
  { symbol: "ETHUSDT", asset_class: "crypto", name: "Ethereum" },
  { symbol: "SOLUSDT", asset_class: "crypto", name: "Solana" },
  { symbol: "AVAXUSDT", asset_class: "crypto", name: "Avalanche" },
  { symbol: "LINKUSDT", asset_class: "crypto", name: "Chainlink" },
  { symbol: "DOGEUSDT", asset_class: "crypto", name: "Dogecoin" },
];

const CATEGORIES: PickCategory[] = ["momentum", "mean_reversion", "confluence", "other"];

function hash(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) h = Math.imul(h ^ input.charCodeAt(i), 16777619);
  return h >>> 0;
}

function unit(seed: string): number {
  return (hash(seed) % 10_000) / 10_000;
}

function pickSetup(seed: string): SetupType {
  return SETUP_TYPES[hash(seed) % SETUP_TYPES.length];
}

function components(seed: string): RankComponents {
  return {
    setup_quality: +unit(`${seed}:sq`).toFixed(3),
    risk_adjusted: +unit(`${seed}:ra`).toFixed(3),
    kill_zone: +unit(`${seed}:kz`).toFixed(3),
    volume: +unit(`${seed}:vol`).toFixed(3),
    freshness: +unit(`${seed}:fr`).toFixed(3),
  };
}

function scoreOf(parts: RankComponents): number {
  return +(
    parts.setup_quality * 0.28 +
    parts.risk_adjusted * 0.24 +
    parts.kill_zone * 0.16 +
    parts.volume * 0.16 +
    parts.freshness * 0.16
  ).toFixed(3);
}

export function universeName(symbol: string): string {
  return SETUP_UNIVERSE.find((s) => s.symbol === symbol)?.name ?? symbol;
}

export function mockQuote(symbol: string, cycle = 0): { last: number; chgPct: number; target: number } {
  const last = seedPrice(symbol) * (1 + (unit(`${symbol}:${cycle}:px`) - 0.5) * 0.012);
  const chgPct = (unit(`${symbol}:${cycle}:chg`) - 0.48) * 6;
  const target = last * (1 + Math.abs(chgPct) / 100 + 0.04);
  return { last, chgPct, target };
}

export function mockEnsemblePicks(
  cycle = 0,
  now = MOCK_NOW,
  allowed?: string[],
): EnsemblePicksResponse {
  const asOf = now + cycle * LIST_REFRESH_SEC * 1000;
  const allow = new Set((allowed ?? []).map((s) => s.toUpperCase()));
  const pool = allow.size ? SETUP_UNIVERSE.filter((row) => allow.has(row.symbol)) : SETUP_UNIVERSE;
  const source = allow.size ? ("DE" as const) : ("SETUP_UNIVERSE" as const);
  const ranked: EnsemblePickItem[] = pool.map((row) => {
    const seed = `${row.symbol}:${cycle}:ens`;
    const signals = getUniverse(row.symbol, seedPrice(row.symbol)).signals.filter((s) => s.status === "ACTIVE");
    const best = [...signals].sort(
      (a, b) => (b.ensemble_score ?? b.confidence) - (a.ensemble_score ?? a.confidence),
    )[0];
    const fromSignal = best?.rank_components ?? components(seed);
    const mix = unit(seed);
    const ensemble_score = +(
      (best?.ensemble_score ?? scoreOf(fromSignal)) * 0.62 +
      mix * 0.38
    ).toFixed(3);
    const setups = [...new Set(signals.map((s) => s.setup_type))].slice(0, 2);
    const best_confidence = best?.confidence ?? +Math.min(0.92, 0.55 + ensemble_score * 0.4).toFixed(3);
    return {
      rank: 0,
      symbol: row.symbol,
      asset_class: row.asset_class,
      score: ensemble_score,
      setup_types: setups.length ? setups : [pickSetup(`${seed}:st`)],
      confidence: best_confidence,
      ensemble_score,
      rank_components: fromSignal,
      contributing_factors: best?.contributing_factors?.length
        ? best.contributing_factors
        : [setups[0] ?? pickSetup(seed), "volume_confirm", "trend_align"].slice(0, 1 + (hash(seed) % 3)),
      best_confidence,
    };
  })
    .sort((a, b) => b.ensemble_score - a.ensemble_score || a.symbol.localeCompare(b.symbol))
    .slice(0, ENSEMBLE_LIMIT)
    .map((row, i) => ({ ...row, rank: i + 1 }));

  return {
    as_of_ts_ms: asOf,
    refresh_sec: LIST_REFRESH_SEC,
    universe_source: source,
    items: ranked,
  };
}

export function mockCategorizedPicks(
  cycle = 0,
  now?: number,
  assetClass?: AssetClass,
  limit = DESK_SYMBOL_LIMIT,
  allowed?: string[],
): CategorizedPicksResponse {
  const asOf = (now ?? MOCK_NOW) + cycle * LIST_REFRESH_SEC * 1000;
  const cap = Math.min(DESK_SYMBOL_LIMIT, Math.max(1, limit));
  const allow = new Set((allowed ?? []).map((s) => s.toUpperCase()));
  const base = allow.size ? SETUP_UNIVERSE.filter((s) => allow.has(s.symbol)) : SETUP_UNIVERSE;
  const pool = assetClass ? base.filter((s) => s.asset_class === assetClass) : base;
  const source = allow.size ? ("DE" as const) : ("SETUP_UNIVERSE" as const);
  const items: CategorizedPickItem[] = pool
    .map((row) => {
      const seed = `${row.symbol}:${cycle}:cat`;
      const px = seedPrice(row.symbol);
      const atr = Math.max(px * 0.018, 0.04);
      const score = +(55 + unit(seed) * 44).toFixed(1);
      const sideUp = unit(`${seed}:side`) > 0.35;
      const entry = px;
      const stop = sideUp ? px - atr : px + atr;
      const target = sideUp ? px + atr * 2.1 : px - atr * 2.1;
      return {
        symbol: row.symbol,
        asset_class: row.asset_class,
        category: CATEGORIES[hash(seed) % CATEGORIES.length],
        score,
        confidence: +(score / 100).toFixed(3),
        setup_types: [pickSetup(seed)],
        entry: +entry.toFixed(4),
        stop: +stop.toFixed(4),
        target: +target.toFixed(4),
        atr: +atr.toFixed(4),
        reward_risk: +(Math.abs(target - entry) / Math.max(Math.abs(entry - stop), 1e-9)).toFixed(2),
      };
    })
    .sort((a, b) => b.score - a.score || a.symbol.localeCompare(b.symbol))
    .slice(0, cap);

  return {
    as_of_ts_ms: asOf,
    refresh_sec: LIST_REFRESH_SEC,
    universe_source: source,
    items,
  };
}

export function mockDroppedPicks(cycle = 0, taken: Set<string> = new Set(), limit = 16): CategorizedPickItem[] {
  return SETUP_UNIVERSE.filter((s) => !taken.has(s.symbol))
    .map((row) => {
      const seed = `${row.symbol}:${cycle}:drop`;
      const px = seedPrice(row.symbol);
      return {
        symbol: row.symbol,
        asset_class: row.asset_class,
        category: "other" as const,
        score: +(28 + unit(seed) * 30).toFixed(1),
        confidence: 0.32,
        setup_types: [] as SetupType[],
        entry: px,
        stop: px * 0.97,
        target: px * 1.04,
        atr: px * 0.02,
        reward_risk: 1.2,
      };
    })
    .sort((a, b) => a.score - b.score)
    .slice(0, Math.min(16, Math.max(0, limit)));
}

/** Prepared `GET /v1/universe` mock — same known fields as `/top`, cap 20. */
export function mockUniverse(cycle = 0, now = MOCK_NOW): UniverseTopResponse {
  return mockUniverseTop(DESK_SYMBOL_LIMIT, cycle, now);
}

/** Locked DE envelope: `{ as_of_ts_ms, limit, symbols[] }` ordered by rank asc. */
export function mockUniverseTop(limit: number, cycle = 0, now = MOCK_NOW): UniverseTopResponse {
  const cap = Math.min(DESK_SYMBOL_LIMIT, Math.max(1, limit));
  const symbols = [...SETUP_UNIVERSE]
    .map((row) => ({
      symbol: row.symbol,
      asset_class: row.asset_class,
      rank: 0,
      score: +unit(`${row.symbol}:${cycle}:uni`).toFixed(3),
    }))
    .sort((a, b) => b.score - a.score || a.symbol.localeCompare(b.symbol))
    .slice(0, cap)
    .map((row, i) => ({ ...row, rank: i + 1 }));
  return { as_of_ts_ms: now + cycle * LIST_REFRESH_SEC * 1000, limit: cap, symbols };
}

export function deskSymbolList(): string[] {
  return SETUP_UNIVERSE.map((s) => s.symbol);
}

export function isDeskSymbol(symbol: string): boolean {
  return SETUP_UNIVERSE.some((s) => s.symbol === symbol);
}

export function resolveAssetClass(symbol: string, raw?: AssetClass): AssetClass {
  return raw ?? inferAssetClass(symbol);
}
