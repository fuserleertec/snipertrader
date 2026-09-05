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
  /** Optional on LIVE WS/HTTP frames (PR #1). Not required by ohlcv_bar.schema.json. */
  buy_volume?: number;
  sell_volume?: number;
  /** Assume closed unless this is explicitly false. */
  closed?: boolean;
}

/** Quant Developers — post risk-approval setup/trade signal. Locked 6-type map. */
export type SetupType =
  | "sweep_reclaim"
  | "fvg_entry"
  | "po3_judas"
  | "sd_extension_fade"
  | "vwap_pullback_cont"
  | "avwap_ob_confluence";

/** Exact `by_setup` keys from GET /performance/summary. Index by these strings. */
export type PerformanceSetupKey =
  | "1_liquidity_sweep_vwap_reclaim"
  | "2_fvg_mitigation_vwap"
  | "3_po3_asia_range_sweep"
  | "4_sd_extension_fade"
  | "5_vwap_pullback_cont"
  | "6_avwap_ob_confluence";

/** PR #9 publish-only factor ids. Not chart ids. */
export type FactorId =
  | "liquidity_sweep"
  | "mss"
  | "fvg"
  | "order_block"
  | "vwap_reclaim"
  | "vwap_band_extension"
  | "vwap_pullback"
  | "first_touch"
  | "low_volume"
  | "volume_confirm"
  | "rejection_candle"
  | "engulfing"
  | "avwap"
  | "htf_ob"
  | "kill_zone"
  | "multi_pattern"
  | "trend_align";

/** PR #9 / Quant `factor_breakdown[]`. `name` is a string (locked ids + extras). */
export interface FactorBreakdown {
  name: string;
  weight: number;
  score: number;
  note?: string | null;
}

/** Quant PR #2 overall (also DE #8 `overall`). */
export interface PerformanceMetrics {
  win_rate: number;
  average_rr: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  signals_today: number;
  signals_week: number;
  n_signals?: number;
  n_closed?: number;
}

/** Quant PR #2 `by_setup` bucket. `signals` is a UI alias of `n_signals`. */
export interface PerformanceSetupStats {
  setup_type?: string;
  product_key?: PerformanceSetupKey;
  win_rate: number;
  average_rr: number;
  sharpe_ratio?: number;
  max_drawdown_pct?: number;
  signals: number;
  n_signals?: number;
  n_closed?: number;
  signals_today?: number;
  signals_week?: number;
}

export interface PerformanceSummary {
  timestamp: number;
  overall: PerformanceMetrics;
  by_setup: Record<PerformanceSetupKey, PerformanceSetupStats>;
  source: "live" | "mock";
  rolling_win_rate_20?: number | null;
  drift_warning?: boolean;
}

export type OverlayPreset =
  | "all"
  | "sweep_reclaim"
  | "fvg_ob"
  | "po3_judas"
  | "sd_extension_fade"
  | "vwap_pullback_cont"
  | "avwap_ob_confluence";

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

export interface MssEvent {
  schema_version: "1.1";
  id: string;
  symbol: string;
  asset_class: AssetClass;
  ts_ms: number;
  direction: "bullish" | "bearish";
  broken_level: number;
  swing_high: number | null;
  swing_low: number | null;
  trigger_sweep_id: string;
  trigger_sweep_side: "buy" | "sell";
  timeframe?: "1m" | "5m" | "15m";
  confirmed?: boolean;
}

export interface OrderBlock {
  schema_version: "1.1";
  id: string;
  symbol: string;
  asset_class: AssetClass;
  direction: "bullish" | "bearish";
  high: number;
  low: number;
  created_ts_ms: number;
  mitigated?: boolean;
  ttl_seconds?: number;
  timeframe?: Timeframe;
  displacement_ts_ms?: number;
  origin_open?: number;
  origin_close?: number;
}

export interface PatternBook {
  fvgs: FVGZone[];
  obs: OrderBlock[];
  sweeps: SweepEvent[];
  mss: MssEvent[];
}

/** Discriminated overlay event until ML ships a dedicated overlay payload. */
export type OverlayKind = "fvg" | "order_block" | "sweep" | "mss";

export type OverlayEvent =
  | { kind: "fvg"; payload: FVGZone }
  | { kind: "order_block"; payload: OrderBlock }
  | { kind: "sweep"; payload: SweepEvent }
  | { kind: "mss"; payload: MssEvent };

/** Data Eng PR #5 — no schema_version on the wire. */
export interface AnchoredVwap {
  anchor_id: string;
  symbol: string;
  anchor_time: number;
  anchor_price: number;
  vwap_value: number;
  bands: {
    plus_1_sigma: number;
    plus_2_sigma: number;
    plus_3_sigma: number;
    minus_1_sigma: number;
    minus_2_sigma: number;
    minus_3_sigma: number;
  };
  asset_class: AssetClass;
}

export interface VolumeNode {
  price: number;
  volume: number;
}

export interface VolumeProfile {
  symbol: string;
  session_type: SessionType;
  high_volume_nodes: VolumeNode[];
  low_volume_nodes: VolumeNode[];
  poc: number;
  timestamp: number;
}

export interface KillZoneEvent {
  symbol: string;
  kill_zone: SessionType;
  start_time: number;
  end_time: number;
  active: boolean;
  asset_class: AssetClass;
}

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
  /** Quant publish-only string[] (PR #9 locked ids + any extra tags). */
  contributing_factors?: string[];
  /** Quant publish-only {name, weight, score, note?}[]. */
  factor_breakdown?: FactorBreakdown[];
  /**
   * Quant close fields (PR #2). Do not compute on FE.
   * `realized_r` is null on ACTIVE/CANCELLED; signed R on TP_HIT/SL_HIT.
   */
  realized_r?: number | null;
  exit_price?: number | null;
  closed_ts_ms?: number | null;
}

export interface SignalListResponse {
  items: Signal[];
  next_cursor: string | null;
}

/** Quant PR #2 GET /signals (history = this list + from_ts/to_ts/status/setup_type/symbol). */
export interface SignalListQuery {
  symbol?: string;
  status?: SignalStatus;
  setup_type?: SetupType;
  side?: SignalSide;
  from_ts?: number;
  to_ts?: number;
  limit?: number;
  /** Opaque page token from the previous `next_cursor`. */
  cursor?: string;
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
