import {
  ASSET_TABS,
  DESK_SYMBOL_LIMIT,
  ENSEMBLE_LIMIT,
  FUTURES_SYMBOLS,
  inferAssetClass,
  LIST_REFRESH_SEC,
  SETUP_FILTERS,
  SETUP_TYPES,
  wireAssetClass,
} from "./constants";
import type {
  AssetClass,
  AssetTab,
  CategorizedPickItem,
  EnsemblePickItem,
  SetupType,
  Signal,
  SignalStatus,
} from "./types";

export {
  ASSET_TABS,
  DESK_SYMBOL_LIMIT,
  ENSEMBLE_LIMIT,
  LIST_REFRESH_SEC,
  SETUP_FILTERS,
};

export function tabToAssetClass(tab: AssetTab): AssetClass {
  return ASSET_TABS.find((t) => t.id === tab)?.asset_class ?? "crypto";
}

/** Locked Active Setup query — GET /signals?status=ACTIVE&asset_class=&setup_type=&symbol=&limit= */
export function activeSetupQuery(
  tab: AssetTab,
  extras: { setup_type?: SetupType | "all"; symbol?: string; limit?: number } = {},
): {
  status: "ACTIVE";
  asset_class: AssetClass;
  setup_type?: SetupType;
  symbol?: string;
  limit: number;
} {
  const setup = extras.setup_type && extras.setup_type !== "all" ? extras.setup_type : undefined;
  return {
    status: "ACTIVE",
    asset_class: tabToAssetClass(tab),
    ...(setup ? { setup_type: setup } : {}),
    ...(extras.symbol ? { symbol: extras.symbol.toUpperCase() } : {}),
    limit: extras.limit ?? DESK_SYMBOL_LIMIT,
  };
}

export function assetClassToTab(asset: AssetClass): AssetTab {
  if (asset === "futures") return "futures";
  if (asset === "equity") return "stocks";
  return "cryptos";
}

export function isLockedSetup(setup: string): setup is SetupType {
  return (SETUP_TYPES as readonly string[]).includes(setup);
}

export function setupFilterType(value: string): SetupType | "all" {
  if (value === "all") return "all";
  const hit = SETUP_FILTERS.find((s) => s.setup_type === value || String(s.n) === value);
  return hit?.setup_type ?? "all";
}

/**
 * One ACTIVE card per locked setup 1–6 inside a tab, unless a setup
 * dropdown isolates a single type — then show matching ACTIVE rows
 * (newest first) so the tab can list several symbols of that setup.
 */
export function cardsForTab(
  signals: Signal[],
  tab: AssetTab,
  setupFilter: SetupType | "all",
  selectedId: string | null,
  pin: (rows: Signal[], selectedId: string | null) => Signal[],
): Signal[] {
  const asset = tabToAssetClass(tab);
  const scoped = signals.filter(
    (s) => s.status === "ACTIVE" && s.asset_class === asset && isLockedSetup(s.setup_type),
  );
  if (setupFilter === "all") return pin(scoped, selectedId);
  return scoped
    .filter((s) => s.setup_type === setupFilter)
    .sort((a, b) => b.ts_ms - a.ts_ms || a.id.localeCompare(b.id))
    .slice(0, 6);
}

export function uniqueSymbols(rows: Array<{ symbol: string }>, limit = DESK_SYMBOL_LIMIT): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const sym = row.symbol.toUpperCase();
    if (!sym || seen.has(sym)) continue;
    seen.add(sym);
    out.push(sym);
    if (out.length >= limit) break;
  }
  return out;
}

/**
 * Chart selector: DE `GET /v1/universe/top` (or mock of that envelope) first,
 * tab symbols sorted to the front. Never a locked BTCUSDT/ETH/AAPL/ES quartet.
 */
export function chartSymbolsForTab(
  tab: AssetTab,
  signals: Signal[],
  extras: Array<{ symbol: string; asset_class?: AssetClass }>,
  current?: string,
): string[] {
  const asset = tabToAssetClass(tab);
  const universe = uniqueSymbols(extras);
  const tabFirst = universe.filter((s) => inferAssetClass(s) === asset);
  const rest = universe.filter((s) => inferAssetClass(s) !== asset);
  const fromSignals = uniqueSymbols(signals);
  const focused = current ? [current.toUpperCase()] : [];
  /** Paper sim: Futures tab can always switch ES/CL/GC/NQ. Not a P0/P4 ranking list. */
  const paperFutures = tab === "futures" ? [...FUTURES_SYMBOLS] : [];
  return uniqueSymbols(
    [...tabFirst, ...paperFutures, ...rest, ...fromSignals, ...focused].map((symbol) => ({ symbol })),
  );
}

export function defaultSymbolForTab(tab: AssetTab, options: string[]): string {
  if (tab === "futures") {
    const hit = FUTURES_SYMBOLS.find((s) => options.includes(s));
    if (hit) return hit;
  }
  return options[0] ?? (tab === "futures" ? "ES" : tab === "stocks" ? "AAPL" : "BTCUSDT");
}

export function clampRefreshSec(raw: unknown): number {
  const n = typeof raw === "number" && Number.isFinite(raw) ? raw : LIST_REFRESH_SEC;
  return Math.max(LIST_REFRESH_SEC, Math.round(n));
}

export function parseAssetClassParam(raw: string | undefined | null): AssetClass | undefined {
  return wireAssetClass(raw ?? undefined);
}

/**
 * History status filter. `all` skips open ACTIVE and inactive CANCELLED
 * so the table is wins/losses (TP_HIT / SL_HIT). Explicit status still works.
 */
export function historyStatusMatches(status: SignalStatus, filter: SignalStatus | "all"): boolean {
  if (filter !== "all") return status === filter;
  return status === "TP_HIT" || status === "SL_HIT";
}

export function rankItems(items: EnsemblePickItem[]): EnsemblePickItem[] {
  return [...items]
    .sort((a, b) => a.rank - b.rank || b.score - a.score || a.symbol.localeCompare(b.symbol))
    .slice(0, ENSEMBLE_LIMIT)
    .map((row, i) => ({ ...row, rank: i + 1 }));
}

export function capCategorized(items: CategorizedPickItem[]): CategorizedPickItem[] {
  const seen = new Set<string>();
  const out: CategorizedPickItem[] = [];
  for (const row of items) {
    const sym = row.symbol.toUpperCase();
    if (seen.has(sym)) continue;
    seen.add(sym);
    out.push({ ...row, symbol: sym });
    if (out.length >= DESK_SYMBOL_LIMIT) break;
  }
  return out;
}

/** DE `GET /v1/universe/top` allowed set. Empty = not contracted; do not invent a universe. */
export function allowedSymbolSet(symbols: Array<{ symbol: string }> | undefined | null): Set<string> {
  return new Set(uniqueSymbols(symbols ?? []));
}

/**
 * Quant ranks P0 inside the DE allowed set when contracted.
 * Empty allowed → pass API items through (never substitute SETUP_UNIVERSE).
 */
export function rankWithinAllowed(items: EnsemblePickItem[], allowed: Set<string>): EnsemblePickItem[] {
  const scoped = allowed.size ? items.filter((i) => allowed.has(i.symbol.toUpperCase())) : items;
  return rankItems(scoped);
}

/** P4 display clip — API items only, optionally inside the DE top-20 set. */
export function capWithinAllowed(items: CategorizedPickItem[], allowed: Set<string>): CategorizedPickItem[] {
  const scoped = allowed.size ? items.filter((i) => allowed.has(i.symbol.toUpperCase())) : items;
  return capCategorized(scoped);
}
