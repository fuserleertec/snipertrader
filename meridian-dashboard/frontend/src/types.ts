export interface Candle {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface SampleInfo {
  bars: number;
  min_bars: number;
  sufficient: boolean;
  note: string | null;
}

export interface Regime {
  name: string;
  adx: number;
  atr_rs: number;
  ribbon: string;
  rr: number;
}

export interface Lattice {
  dens_l: number;
  dens_s: number;
  grade_l: string;
  grade_s: string;
  rank_l: number;
  rank_s: number;
}

export interface Gates {
  gate1_long: boolean;
  gate1_short: boolean;
  bull_armed: boolean;
  bear_armed: boolean;
  armed_type_l: string | null;
  armed_type_s: string | null;
  in_bull_zone: boolean;
  in_bear_zone: boolean;
  grade_ok_l: boolean;
  grade_ok_s: boolean;
}

export interface Ofi {
  absorption_bull: boolean;
  absorption_bear: boolean;
  imbalance_bull: boolean;
  imbalance_bear: boolean;
  stack_bull: boolean;
  stack_bear: boolean;
  stack_count: number;
  stack_dir: number;
  source: string;
}

export interface LiquidityPool {
  price: number;
  dir: number;
  magnet: number;
  active: boolean;
}

export interface Liquidity {
  active_count: number;
  top_magnet: { price: number | null; dir: number; magnet: number };
  pools: LiquidityPool[];
}

export interface Risk {
  regime_flip_count: number;
  consecutive_path_breaks: number;
  min_density: number;
}

export interface Series {
  time: number[];
  close: number[];
  vwap: number[];
  up1: number[];
  dn1: number[];
  up2: number[];
  dn2: number[];
  cvd?: number[];
  e9?: number[];
  e21?: number[];
  e50?: number[];
}

/** Subset PriceChart reads. Matches the futures chart component. */
export interface EngineView {
  close: number;
  series: Series;
}

export interface Signal {
  side: string;
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  tp3?: number | null;
  rr?: number;
  grade: string;
  bar_time: number;
}

export interface PathState {
  side: string;
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  status: string;
  bar_time?: number;
}

export interface Trade {
  side: string;
  entry: number;
  sl: number;
  tp1: number;
  tp2: number;
  grade?: string;
  regime?: string;
  bar_time: number;
  status: string;
}

/** GET /api/state — Meridian engine document. See DATA_CONTRACT. */
export interface EngineState {
  symbol: string;
  timeframe: string;
  min_grade?: string;
  bar_time: number;
  close: number;
  regime: Regime;
  bias: { dir: string };
  lattice: Lattice;
  gates: Gates;
  cvd: { value: number; slope: string; session_high: number; session_low: number };
  ofi: Ofi;
  liquidity?: Liquidity;
  risk?: Risk;
  vwap: { value: number; up1: number; dn1: number; up2: number; dn2: number; zone: string };
  signal: Signal | null;
  path: PathState | null;
  series: Series;
  signals?: Trade[];
  /** Present on the Yahoo fallback. /api/state series is close-only. */
  ohlc?: { o: number[]; h: number[]; l: number[]; v: number[] };
  fallback?: boolean;
  feed?: string;
}

export function candlesOf(state: EngineState | null): Candle[] {
  const series = state?.series;
  if (!series?.time?.length || !series.close?.length) return [];
  const n = Math.min(series.time.length, series.close.length);
  const ohlc = state?.ohlc;
  const out: Candle[] = [];
  for (let i = 0; i < n; i++) {
    const c = series.close[i];
    const o = ohlc?.o?.[i] ?? (i ? series.close[i - 1] : c);
    out.push({
      t: series.time[i],
      o,
      h: ohlc?.h?.[i] ?? Math.max(o, c),
      l: ohlc?.l?.[i] ?? Math.min(o, c),
      c,
      v: ohlc?.v?.[i] ?? 0,
    });
  }
  return out;
}

export interface PathCard {
  side: 'BUY' | 'SELL' | string;
  entry: number;
  stop: number;
  tp1: number;
  tp2: number;
  time: number | null;
  status: string;
  grade?: string;
  regime?: string;
}

export interface ScanRow {
  symbol: string;
  name: string;
  regime: string | null;
  bias: string | null;
  grade_l: string | null;
  grade_s: string | null;
  path_status: string | null;
  signal: string | null;
  signal_grade: string | null;
  close: number | null;
  error: string | null;
}

export interface ScanResponse {
  timeframe: string;
  min_grade: string;
  rows: ScanRow[];
  feed: string;
}

export interface NewsItem {
  title: string;
  url: string;
  source: string;
  time: string;
}

export interface NewsResponse {
  source: string;
  items: NewsItem[];
  error: string | null;
}

export interface Quote {
  symbol: string;
  last: number | null;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  ts: number | null;
  live: boolean;
  source: string;
}

export interface Meta {
  provider: string;
  simulation: boolean;
  data: string;
  symbol: string;
  timeframe: string;
  preset: string;
  engine: string;
  footprint: string;
}

export interface Position {
  symbol: string;
  side: string;
  qty: number;
  avg_entry_price: number;
  market_value: number;
  unrealized_pl: number;
  current_price: number;
}

export const TIMEFRAMES = ['5m', '15m', '1h'] as const;
export const MIN_GRADES = ['WATCH', 'PRIME', 'ELITE', 'SINGULAR'] as const;

export const BOOK: { symbol: string; name: string }[] = [
  { symbol: 'SPY', name: 'S&P 500' },
  { symbol: 'QQQ', name: 'Nasdaq 100' },
  { symbol: 'IWM', name: 'Russell 2000' },
  { symbol: 'NVDA', name: 'NVIDIA' },
  { symbol: 'TSLA', name: 'Tesla' },
  { symbol: 'AAPL', name: 'Apple' },
];

export function bookName(symbol: string): string {
  return BOOK.find((row) => row.symbol === symbol)?.name ?? symbol;
}
