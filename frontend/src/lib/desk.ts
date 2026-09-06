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

/** Chart selector options: tab universe + any focused pick/card, never a single locked pair. */
export function chartSymbolsForTab(
  tab: AssetTab,
  signals: Signal[],
  extras: Array<{ symbol: string; asset_class?: AssetClass }>,
  current?: string,
): string[] {
  const asset = tabToAssetClass(tab);
  const seed =
    tab === "futures"
      ? [...FUTURES_SYMBOLS]
      : uniqueSymbols(
          [...signals, ...extras].filter((r) => (r.asset_class ?? inferAssetClass(r.symbol)) === asset),
        );
  const extra = extras
    .filter((r) => (r.asset_class ?? inferAssetClass(r.symbol)) === asset)
    .map((r) => r.symbol.toUpperCase());
  const focused = current ? [current.toUpperCase()] : [];
  const merged = uniqueSymbols(
    [...seed, ...extra, ...focused, ...signals.filter((s) => s.asset_class === asset).map((s) => s.symbol)].map(
      (symbol) => ({ symbol }),
    ),
  );
  return merged.length ? merged : seed.length ? [...seed] : focused;
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

export function rankItems(items: EnsemblePickItem[]): EnsemblePickItem[] {
  return [...items]
    .sort((a, b) => a.rank - b.rank || b.ensemble_score - a.ensemble_score || a.symbol.localeCompare(b.symbol))
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
