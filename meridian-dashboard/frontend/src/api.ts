import type { Bar, DeskQuote, NewsItem, ScanRow, Timeframe } from './types';
import { shapeBars } from './lib/bars';
import { nyParts } from './lib/ny';
import { UNIVERSE, universeName } from './universe';

/**
 * Stock data sources, in order:
 * 1. Existing SniperTrader equities routes on VITE_API_BASE (default
 *    http://127.0.0.1:8787 from `node api/_server.js`):
 *      GET /api/stocks/klines?symbol=&timeframe=&limit=
 *      GET /api/news/catalyst?symbol=
 *    There is no meridian-dashboard/backend and no stock websocket in this repo.
 *    Alpaca IEX bars replace the Yahoo chart only for regular hours.
 * 2. Yahoo Finance via the Vite `/market` proxy so the desk still runs
 *    without Alpaca keys. Quotes from that feed are delayed.
 */

const API_BASE = (import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8787').replace(/\/$/, '');

const YAHOO_TF: Record<Timeframe, { interval: string; range: string }> = {
  '1m': { interval: '1m', range: '1d' },
  '5m': { interval: '5m', range: '5d' },
  '15m': { interval: '15m', range: '1mo' },
  '1h': { interval: '60m', range: '3mo' },
  '4h': { interval: '60m', range: '6mo' },
  '1d': { interval: '1d', range: '2y' },
};

const ALPACA_TF: Record<Timeframe, string> = {
  '1m': '1m',
  '5m': '5m',
  '15m': '15m',
  '1h': '1h',
  '4h': '1h',
  '1d': '1d',
};

async function fetchTimeout(url: string, ms: number): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

function num(value: unknown): number | null {
  const n = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN;
  return Number.isFinite(n) ? n : null;
}

function quoteFromMeta(symbol: string, meta: Record<string, unknown>, bars: Bar[]): DeskQuote {
  const lastBar = bars[bars.length - 1];
  const last = num(meta.regularMarketPrice) ?? lastBar?.close ?? 0;
  const prevClose = num(meta.previousClose) ?? num(meta.chartPreviousClose) ?? last;
  const change = last - prevClose;
  const dayHigh = num(meta.regularMarketDayHigh) ?? Math.max(...bars.map((b) => b.high));
  const dayLow = num(meta.regularMarketDayLow) ?? Math.min(...bars.map((b) => b.low));
  return {
    symbol,
    name: String(meta.shortName || meta.longName || universeName(symbol)),
    exchange: String(meta.fullExchangeName || meta.exchangeName || ''),
    instrument: String(meta.instrumentType || 'EQUITY'),
    last,
    prevClose,
    change,
    changePct: prevClose ? (change / prevClose) * 100 : 0,
    dayHigh,
    dayLow,
    volume: num(meta.regularMarketVolume) ?? bars.reduce((sum, bar) => sum + bar.volume, 0),
    week52High: num(meta.fiftyTwoWeekHigh),
    week52Low: num(meta.fiftyTwoWeekLow),
  };
}

export function overlayBars(quote: DeskQuote, bars: Bar[]): DeskQuote {
  const lastBar = bars[bars.length - 1];
  if (!lastBar) return quote;
  const day = nyParts(lastBar.time * 1000).ymd;
  const today = bars.filter((bar) => nyParts(bar.time * 1000).ymd === day);
  const last = lastBar.close;
  const prev = quote.prevClose || last;
  const change = last - prev;
  return {
    ...quote,
    last,
    change,
    changePct: prev ? (change / prev) * 100 : 0,
    dayHigh: today.length ? Math.max(...today.map((bar) => bar.high)) : quote.dayHigh,
    dayLow: today.length ? Math.min(...today.map((bar) => bar.low)) : quote.dayLow,
    volume: today.reduce((sum, bar) => sum + bar.volume, 0) || quote.volume,
  };
}

export async function fetchYahooChart(
  symbol: string,
  timeframe: Timeframe,
  extended: boolean,
): Promise<{ bars: Bar[]; quote: DeskQuote }> {
  const spec = YAHOO_TF[timeframe];
  const url =
    `/market/v8/finance/chart/${encodeURIComponent(symbol)}` +
    `?interval=${spec.interval}&range=${spec.range}&includePrePost=${extended ? 'true' : 'false'}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Chart request failed (${res.status})`);
  const body = (await res.json()) as {
    chart?: {
      result?: Array<{
        meta?: Record<string, unknown>;
        timestamp?: number[];
        indicators?: { quote?: Array<Record<string, Array<number | null>>> };
      }> | null;
      error?: { description?: string };
    };
  };
  if (body.chart?.error) throw new Error(body.chart.error.description || 'No chart data');
  const result = body.chart?.result?.[0];
  const times = result?.timestamp;
  const q = result?.indicators?.quote?.[0];
  if (!result || !times || !q) throw new Error(`No bars for ${symbol}`);
  const raw: Bar[] = [];
  for (let i = 0; i < times.length; i++) {
    const open = q.open?.[i];
    const high = q.high?.[i];
    const low = q.low?.[i];
    const close = q.close?.[i];
    if (open == null || high == null || low == null || close == null) continue;
    raw.push({
      time: times[i],
      open,
      high,
      low,
      close,
      volume: q.volume?.[i] ?? 0,
    });
  }
  const bars = shapeBars(raw, timeframe, extended);
  if (!bars.length) throw new Error(`No ${extended ? 'extended' : 'regular'} session bars for ${symbol}`);
  return { bars, quote: quoteFromMeta(symbol, result.meta ?? {}, bars) };
}

export async function fetchAlpacaBars(symbol: string, timeframe: Timeframe, extended: boolean): Promise<Bar[] | null> {
  if (!API_BASE || extended) return null;
  const limit = timeframe === '1d' ? 400 : 512;
  const url = `${API_BASE}/api/stocks/klines?symbol=${encodeURIComponent(symbol)}&timeframe=${ALPACA_TF[timeframe]}&limit=${limit}`;
  try {
    const res = await fetchTimeout(url, 2500);
    if (!res.ok) return null;
    const data: unknown = await res.json();
    if (!Array.isArray(data)) return null;
    const raw: Bar[] = [];
    for (const row of data) {
      if (!row || typeof row !== 'object') continue;
      const rec = row as Record<string, unknown>;
      const parsed = Date.parse(String(rec.timestamp ?? ''));
      const open = num(rec.open);
      const high = num(rec.high);
      const low = num(rec.low);
      const close = num(rec.close);
      if (!Number.isFinite(parsed) || open == null || high == null || low == null || close == null) continue;
      raw.push({
        time: Math.floor(parsed / 1000),
        open,
        high,
        low,
        close,
        volume: num(rec.volume) ?? 0,
      });
    }
    const bars = shapeBars(raw, timeframe, false);
    return bars.length ? bars : null;
  } catch {
    return null;
  }
}

interface SparkEntry {
  symbol?: string;
  close?: Array<number | null>;
  previousClose?: number;
  chartPreviousClose?: number;
  fulldayPrice?: number;
  fulldayChangePercent?: number;
}

export async function fetchScan(extra?: string): Promise<ScanRow[]> {
  const symbols = [...UNIVERSE.map((row) => row.symbol)];
  if (extra && !symbols.includes(extra)) symbols.unshift(extra);
  const url = `/market/v8/finance/spark?symbols=${encodeURIComponent(symbols.join(','))}&range=1d&interval=5m`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Scan request failed (${res.status})`);
  const body = (await res.json()) as Record<string, SparkEntry>;
  return symbols.map((symbol) => {
    const entry = body[symbol];
    const spark = (entry?.close ?? []).filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
    const prev = entry?.previousClose ?? entry?.chartPreviousClose ?? null;
    const last = entry?.fulldayPrice ?? (spark.length ? spark[spark.length - 1] : null);
    const changePct =
      entry?.fulldayChangePercent ??
      (last != null && prev ? ((last - prev) / prev) * 100 : null);
    return {
      symbol,
      name: universeName(symbol),
      last,
      changePct,
      spark: spark.slice(-36),
    };
  });
}

export async function fetchYahooNews(symbol: string): Promise<NewsItem[]> {
  const url = `/market/v1/finance/search?q=${encodeURIComponent(symbol + ' stock')}&newsCount=10&quotesCount=0`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`News request failed (${res.status})`);
  const body = (await res.json()) as {
    news?: Array<{ uuid?: string; title?: string; publisher?: string; link?: string; providerPublishTime?: number }>;
  };
  return (body.news ?? [])
    .filter((item) => item.title && item.link)
    .slice(0, 8)
    .map((item, index) => ({
      id: item.uuid || `${symbol}-${index}`,
      title: item.title || '',
      source: item.publisher || 'Yahoo',
      url: item.link || '',
      publishedAt: item.providerPublishTime ?? null,
    }));
}

export async function fetchCatalyst(
  symbol: string,
): Promise<{ items: NewsItem[]; sentiment: string | null } | null> {
  if (!API_BASE) return null;
  try {
    const res = await fetchTimeout(`${API_BASE}/api/news/catalyst?symbol=${encodeURIComponent(symbol)}`, 8000);
    if (!res.ok) return null;
    const data = (await res.json()) as {
      sentiment_bias?: string;
      headlines?: string[];
      catalysts?: Array<{ headline?: string; executive_summary?: string; sentiment_bias?: string }>;
    };
    const catalysts = Array.isArray(data.catalysts) ? data.catalysts : [];
    const items: NewsItem[] = catalysts.length
      ? catalysts
          .filter((item) => item.headline)
          .slice(0, 6)
          .map((item, index) => ({
            id: `cat-${symbol}-${index}`,
            title: item.headline || '',
            source: 'Catalyst',
            url: '',
            publishedAt: null,
            summary: item.executive_summary,
          }))
      : (data.headlines ?? []).slice(0, 8).map((title, index) => ({
          id: `hd-${symbol}-${index}`,
          title,
          source: 'Headline',
          url: '',
          publishedAt: null,
        }));
    if (!items.length) return null;
    return { items, sentiment: data.sentiment_bias ?? null };
  } catch {
    return null;
  }
}
