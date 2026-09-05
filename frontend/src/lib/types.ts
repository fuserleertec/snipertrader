/** Rev. 1.1 contracts — field names match /schemas/*.schema.json. Do not invent. */

export const SCHEMA_VERSION = "1.1" as const;

export type AssetClass = "crypto" | "equity" | "futures";
export type Timeframe = "1m" | "5m" | "15m" | "1h" | "4h";
export type SessionType =
  | "asia"
  | "london"
  | "ny_am"
  | "ny_pm"
  | "rth"
  | "eth"
  | "globex";
export type AnchorType = "session" | "weekly" | "rolling";

export interface VWAPValues {
  schema_version: "1.1";
  symbol: string;
  asset_class: AssetClass;
  anchor_type: AnchorType;
  session_type: SessionType | null;
  anchor_start_ms: number;
  lookback_periods: number | null;
  vwap: number;
  sigma: number;
  band_m3: number;
  band_m2: number;
  band_m1: number;
  band_p1: number;
  band_p2: number;
  band_p3: number;
  cum_volume: number;
  n_obs: number;
  updated_ts_ms: number;
}

export interface SessionLevels {
  schema_version: "1.1";
  symbol: string;
  asset_class: AssetClass;
  session_type: SessionType;
  session_start_ms: number;
  session_end_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  updated_ts_ms: number;
}

export interface OHLCVBar {
  schema_version: "1.1";
  symbol: string;
  asset_class: AssetClass;
  timeframe: Timeframe;
  open_ts_ms: number;
  close_ts_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  n_ticks: number;
  /** Planned on the draft WS frame; omitted by the current JSON Schema. */
  buy_volume?: number;
  sell_volume?: number;
  /** Assume closed unless this is explicitly false. */
  closed?: boolean;
}

export interface SetupSignal {
  schema_version: "1.1";
  id: string;
  symbol: string;
  asset_class: AssetClass;
  setup_type: string;
  side: "long" | "short";
  confidence: number | null;
  ref_vwap: number | null;
  ref_session: string | null;
  ts_ms: number;
}

export interface FVGZone {
  schema_version: "1.1";
  id: string;
  symbol: string;
  asset_class: AssetClass;
  direction: "bullish" | "bearish";
  high: number;
  low: number;
  mitigated?: boolean;
  created_ts_ms: number;
  ttl_seconds?: number;
}

export interface SweepEvent {
  schema_version: "1.1";
  id: string;
  symbol: string;
  asset_class: AssetClass;
  side: "buy" | "sell";
  swept_level: number;
  reclaim: boolean | null;
  ts_ms: number;
}

export type SignalFrame = SetupSignal | FVGZone | SweepEvent;

export type SignalKind = "setup" | "fvg" | "sweep";

/** UI row mapped from setup_signal / fvg_zone / sweep_event — not a wire contract. */
export interface SignalRow {
  id: string;
  ts_ms: number;
  symbol: string;
  pattern_type: string;
  direction: string;
  zone: string;
  status: string;
  kind: SignalKind;
}

export interface SessionListResponse {
  symbol: string;
  sessions: { key: string; value: SessionLevels }[];
}

export type ConnectionStatus = "mock" | "connecting" | "live" | "disconnected";
