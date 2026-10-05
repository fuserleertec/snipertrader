export const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d'] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LinePoint {
  time: number;
  value: number;
}

export interface DeskQuote {
  symbol: string;
  name: string;
  exchange: string;
  instrument: string;
  last: number;
  prevClose: number;
  change: number;
  changePct: number;
  dayHigh: number;
  dayLow: number;
  volume: number;
  week52High: number | null;
  week52Low: number | null;
}

export interface ScanRow {
  symbol: string;
  name: string;
  last: number | null;
  changePct: number | null;
  spark: number[];
}

export interface NewsItem {
  id: string;
  title: string;
  source: string;
  url: string;
  publishedAt: number | null;
  summary?: string;
}

export type Feed = 'alpaca' | 'yahoo' | 'offline';
export type ThemeName = 'dark' | 'light';
