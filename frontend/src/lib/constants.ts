import type { AnchorType, AssetClass, SessionType, SetupType, SignalStatus, Timeframe } from "./types";

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

export const SYMBOLS: { symbol: string; asset_class: AssetClass; label: string }[] = [
  { symbol: "BTCUSDT", asset_class: "crypto", label: "BTCUSDT" },
  { symbol: "ETHUSDT", asset_class: "crypto", label: "ETHUSDT" },
  { symbol: "AAPL", asset_class: "equity", label: "AAPL" },
  { symbol: "ES", asset_class: "futures", label: "ES" },
];

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
  "mss_break",
  "order_block",
  "sweep_mss",
  "ob_fvg",
];

export const SIGNAL_STATUSES: SignalStatus[] = ["ACTIVE", "TP_HIT", "SL_HIT", "CANCELLED"];

export const ROLLING_VWAP_PERIODS = 20;

export const HISTORY_LIMIT = 200;

export function sessionsForAsset(asset: AssetClass): SessionType[] {
  if (asset === "crypto") return CRYPTO_SESSIONS;
  if (asset === "equity") return EQUITY_SESSIONS;
  return FUTURES_SESSIONS;
}

export function inferAssetClass(symbol: string): AssetClass {
  if (symbol.endsWith("USDT") || symbol.endsWith("USD") || symbol.endsWith("BTC")) {
    return "crypto";
  }
  if (symbol === "ES" || symbol === "NQ" || symbol === "YM" || symbol === "RTY") {
    return "futures";
  }
  return "equity";
}

export function normalizeSymbol(raw: string): string {
  return raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function seedPrice(symbol: string): number {
  if (symbol.startsWith("BTC")) return 67250;
  if (symbol.startsWith("ETH")) return 3480;
  if (symbol === "ES") return 5620;
  if (symbol === "AAPL") return 228;
  return 100;
}
