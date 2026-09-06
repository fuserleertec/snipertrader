import type {
  AnchorType,
  AssetClass,
  AssetTab,
  OverlayPreset,
  OverlaySetupType,
  SessionType,
  PerformanceSetupKey,
  SetupType,
  SignalStatus,
  Timeframe,
} from "./types";

export const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h", "4h"];

export const ANCHORS: AnchorType[] = ["session", "weekly", "rolling"];

export const SESSION_TYPES: SessionType[] = [
  "asia",
  "london",
  "ny_am",
  "ny_pm",
  "rth",
  "eth",
  "globex",
];

export const CRYPTO_SESSIONS: SessionType[] = ["asia", "london", "ny_am", "ny_pm"];
export const EQUITY_SESSIONS: SessionType[] = ["rth", "eth"];
export const FUTURES_SESSIONS: SessionType[] = ["rth", "globex"];

/** Preference order when a futures symbol is already in the dynamic options. Not a UI list. */
export const FUTURES_SYMBOLS = ["ES", "CL", "GC", "NQ"] as const;

/** Locked setup 1–6. `ob_fvg` is not a setup_type. */
export const SETUP_FILTERS: { n: 1 | 2 | 3 | 4 | 5 | 6; setup_type: SetupType; label: string }[] = [
  { n: 1, setup_type: "sweep_reclaim", label: "1 · sweep_reclaim" },
  { n: 2, setup_type: "fvg_entry", label: "2 · fvg_entry" },
  { n: 3, setup_type: "po3_judas", label: "3 · po3_judas" },
  { n: 4, setup_type: "sd_extension_fade", label: "4 · sd_extension_fade" },
  { n: 5, setup_type: "vwap_pullback_cont", label: "5 · vwap_pullback_cont" },
  { n: 6, setup_type: "avwap_ob_confluence", label: "6 · avwap_ob_confluence" },
];

export const ASSET_TABS: { id: AssetTab; label: string; asset_class: AssetClass }[] = [
  { id: "futures", label: "Active Setup for Futures", asset_class: "futures" },
  { id: "stocks", label: "Active Setup for Stocks", asset_class: "equity" },
  { id: "cryptos", label: "Active Setup for Cryptos", asset_class: "crypto" },
];

/** P0 Quantum Ensemble Picks — Quant ranks at most 10. */
export const ENSEMBLE_LIMIT = 10;
/** P4 categorized picks + P2 history desk — at most 20 symbols. */
export const DESK_SYMBOL_LIMIT = 20;
/** Client list poll. Matches Quant `refresh_sec` (900 = 15m). Do not poll faster. */
export const LIST_REFRESH_SEC = 900;
export const LIST_REFRESH_MS = LIST_REFRESH_SEC * 1000;
/** Section 07 Recon Audit — hard cap. */
export const RECON_AUDIT_LIMIT = 16;

export const TF_MS: Record<Timeframe, number> = {
  "1m": 60_000,
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
};

export const SETUP_TYPES: SetupType[] = [
  "sweep_reclaim",
  "fvg_entry",
  "po3_judas",
  "sd_extension_fade",
  "vwap_pullback_cont",
  "avwap_ob_confluence",
];

/** ML PR #7 overlay-focus setups (chart views 1–3). */
export const OVERLAY_SETUP_TYPES: OverlaySetupType[] = [
  "sweep_reclaim",
  "fvg_entry",
  "po3_judas",
];

/** Locked GET /performance/summary keys. Display the key itself. */
export const PERFORMANCE_SETUP_KEYS: PerformanceSetupKey[] = [
  "1_liquidity_sweep_vwap_reclaim",
  "2_fvg_mitigation_vwap",
  "3_po3_asia_range_sweep",
  "4_sd_extension_fade",
  "5_vwap_pullback_cont",
  "6_avwap_ob_confluence",
];

export const OVERLAY_PRESETS: { id: OverlayPreset; label: string }[] = [
  { id: "all", label: "all overlays" },
  { id: "sweep_reclaim", label: "1_liquidity_sweep_vwap_reclaim" },
  { id: "fvg_ob", label: "2_fvg_mitigation_vwap" },
  { id: "po3_judas", label: "3_po3_asia_range_sweep" },
  { id: "sd_extension_fade", label: "4_sd_extension_fade" },
  { id: "vwap_pullback_cont", label: "5_vwap_pullback_cont" },
  { id: "avwap_ob_confluence", label: "6_avwap_ob_confluence" },
];

export const SIGNAL_STATUSES: SignalStatus[] = ["ACTIVE", "TP_HIT", "SL_HIT", "CANCELLED"];

export const ROLLING_VWAP_PERIODS = 20;

export const HISTORY_LIMIT = 200;

export function sessionsForAsset(asset: AssetClass): SessionType[] {
  if (asset === "crypto") return CRYPTO_SESSIONS;
  if (asset === "equity") return EQUITY_SESSIONS;
  return FUTURES_SESSIONS;
}

const FUTURES = new Set<string>(["ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "NG", "ZB", "ZN"]);
const CRYPTO_SPOT = new Set<string>(["BTC", "ETH", "SOL", "XRP", "DOGE", "AVAX", "LINK", "ADA"]);

export function inferAssetClass(symbol: string): AssetClass {
  const u = symbol.toUpperCase();
  if (FUTURES.has(u)) return "futures";
  if (u.endsWith("USDT") || u.endsWith("USD") || CRYPTO_SPOT.has(u)) return "crypto";
  return "equity";
}

/** Quant accepts `stocks` as an alias of `equity`. */
export function wireAssetClass(raw: string | undefined | null): AssetClass | undefined {
  if (!raw) return undefined;
  if (raw === "stocks" || raw === "equity") return "equity";
  if (raw === "futures" || raw === "crypto") return raw;
  return undefined;
}

export function normalizeSymbol(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function seedPrice(symbol: string): number {
  const u = symbol.toUpperCase();
  if (u.startsWith("BTC")) return 67250;
  if (u.startsWith("ETH")) return 3480;
  if (u.startsWith("SOL")) return 148.2;
  if (u.startsWith("AVAX")) return 36.4;
  if (u.startsWith("LINK")) return 14.8;
  if (u.startsWith("DOGE")) return 0.162;
  if (u.startsWith("XRP")) return 0.62;
  if (u.startsWith("ADA")) return 0.45;
  if (u === "ES") return 5812.25;
  if (u === "NQ") return 20904;
  if (u === "CL") return 76.4;
  if (u === "GC") return 2486.1;
  if (u === "YM") return 41200;
  if (u === "AAPL") return 221.4;
  if (u === "NVDA") return 132.18;
  if (u === "TSLA") return 214.6;
  if (u === "MSFT") return 438.2;
  if (u === "META") return 512.4;
  if (u === "AMZN") return 186.4;
  if (u === "AMD") return 158.2;
  if (u === "AVGO") return 172.5;
  if (u === "PLTR") return 41.15;
  if (u === "CRWD") return 318.4;
  if (u === "GOOGL") return 168.2;
  if (u === "NFLX") return 702.1;
  return 100;
}
