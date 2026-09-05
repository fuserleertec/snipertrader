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

/** Quant Developers — post risk-approval setup/trade signal. Not a raw sweep/FVG stream. */
export type SetupType =
  | "sweep_reclaim"
  | "fvg_entry"
  | "mss_break"
  | "order_block"
  | "sweep_mss"
  | "ob_fvg";

export type SignalSide = "long" | "short";

export type SignalStatus = "ACTIVE" | "TP_HIT" | "SL_HIT" | "CANCELLED";

export interface Signal {
  id: string;
  ts_ms: number;
  symbol: string;
  asset_class: AssetClass;
  setup_type: SetupType;
  side: SignalSide;
  entry: number;
  stop: number;
  target: number;
  status: SignalStatus;
  confidence: number;
  timeframe: Timeframe;
  ref_session: SessionType;
  trigger_event_ids: string[];
}

export interface SignalListResponse {
  items: Signal[];
  next_cursor: string | null;
}

export interface SignalListQuery {
  symbol?: string;
  status?: SignalStatus;
  setup_type?: SetupType;
  from_ts?: number;
  to_ts?: number;
  limit?: number;
}

export type SignalWsType = "signal.upsert" | "signal.status";

export interface SignalWsEvent {
  type: SignalWsType;
  signal: Signal;
}

export interface SessionListResponse {
  symbol: string;
  sessions: { key: string; value: SessionLevels }[];
}

export type ConnectionStatus = "mock" | "connecting" | "live" | "disconnected";
