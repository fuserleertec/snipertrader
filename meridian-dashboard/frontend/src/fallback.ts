import type { EngineState, NewsResponse, ScanResponse } from './types';
import { bookName } from './types';

const TF: Record<string, { interval: string; range: string }> = {
  '5m': { interval: '5m', range: '5d' },
  '15m': { interval: '15m', range: '1mo' },
  '1h': { interval: '60m', range: '3mo' },
  '1d': { interval: '1d', range: '2y' },
};

interface YahooBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

async function yahooBars(symbol: string, timeframe: string): Promise<YahooBar[]> {
  const spec = TF[timeframe] || TF['15m'];
  const url = `/market/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${spec.interval}&range=${spec.range}&includePrePost=false`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`chart ${res.status}`);
  const body = await res.json();
  const result = body.chart?.result?.[0];
  if (body.chart?.error) throw new Error(body.chart.error.description || 'no bars');
  const times: number[] = result?.timestamp || [];
  const q = result?.indicators?.quote?.[0];
  if (!times.length || !q) throw new Error(`no bars for ${symbol}`);
  const bars: YahooBar[] = [];
  for (let i = 0; i < times.length; i++) {
    const o = q.open?.[i];
    const h = q.high?.[i];
    const l = q.low?.[i];
    const c = q.close?.[i];
    if (o == null || h == null || l == null || c == null) continue;
    bars.push({ t: times[i] * 1000, o, h, l, c, v: q.volume?.[i] || 0 });
  }
  return bars.slice(-400);
}

function study(bars: YahooBar[]) {
  let pv = 0;
  let vv = 0;
  let p2 = 0;
  const vwap: number[] = [];
  const up1: number[] = [];
  const dn1: number[] = [];
  const up2: number[] = [];
  const dn2: number[] = [];
  for (const bar of bars) {
    const tp = (bar.h + bar.l + bar.c) / 3;
    const w = bar.v > 0 ? bar.v : 1;
    pv += tp * w;
    vv += w;
    p2 += tp * tp * w;
    const mean = pv / vv;
    const sd = Math.sqrt(Math.max(0, p2 / vv - mean * mean));
    vwap.push(mean);
    up1.push(mean + sd);
    dn1.push(mean - sd);
    up2.push(mean + 2 * sd);
    dn2.push(mean - 2 * sd);
  }
  return { vwap, up1, dn1, up2, dn2 };
}

export async function yahooState(symbol: string, timeframe: string): Promise<EngineState> {
  const bars = await yahooBars(symbol, timeframe);
  const s = study(bars);
  const last = bars[bars.length - 1];
  const lastOf = (xs: number[]) => xs[xs.length - 1];
  const zone = last.c >= lastOf(s.up2) ? '+2σ' : last.c >= lastOf(s.up1) ? '+1σ' : last.c <= lastOf(s.dn2) ? '-2σ' : last.c <= lastOf(s.dn1) ? '-1σ' : 'FV';
  return {
    symbol,
    timeframe,
    bar_time: last.t,
    close: last.c,
    regime: { name: '—', adx: 0, atr_rs: 0, ribbon: '—', rr: 0 },
    bias: { dir: 'none' },
    lattice: { dens_l: 0, dens_s: 0, grade_l: '—', grade_s: '—', rank_l: 0, rank_s: 0 },
    gates: {
      gate1_long: false, gate1_short: false, bull_armed: false, bear_armed: false,
      armed_type_l: null, armed_type_s: null, in_bull_zone: false, in_bear_zone: false,
      grade_ok_l: false, grade_ok_s: false,
    },
    cvd: { value: 0, slope: 'flat', session_high: 0, session_low: 0 },
    ofi: {
      absorption_bull: false, absorption_bear: false, imbalance_bull: false, imbalance_bear: false,
      stack_bull: false, stack_bear: false, stack_count: 0, stack_dir: 0, source: 'yahoo',
    },
    liquidity: { active_count: 0, top_magnet: { price: null, dir: 0, magnet: 0 }, pools: [] },
    vwap: { value: lastOf(s.vwap) || last.c, up1: lastOf(s.up1) || last.c, dn1: lastOf(s.dn1) || last.c, up2: lastOf(s.up2) || last.c, dn2: lastOf(s.dn2) || last.c, zone },
    signal: null,
    path: null,
    series: {
      time: bars.map((b) => b.t),
      close: bars.map((b) => b.c),
      vwap: s.vwap,
      up1: s.up1,
      dn1: s.dn1,
      up2: s.up2,
      dn2: s.dn2,
    },
    ohlc: {
      o: bars.map((b) => b.o),
      h: bars.map((b) => b.h),
      l: bars.map((b) => b.l),
      v: bars.map((b) => b.v),
    },
    signals: [],
    fallback: true,
    feed: 'yahoo',
  };
}

export async function yahooScan(symbols: string[]): Promise<ScanResponse> {
  const url = `/market/v8/finance/spark?symbols=${encodeURIComponent(symbols.join(','))}&range=1d&interval=5m`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`scan ${res.status}`);
  const body = await res.json() as Record<string, { fulldayPrice?: number }>;
  return {
    timeframe: '15m',
    min_grade: 'PRIME',
    feed: 'yahoo',
    rows: symbols.map((symbol) => ({
      symbol,
      name: bookName(symbol),
      regime: null,
      bias: null,
      grade_l: null,
      grade_s: null,
      path_status: null,
      signal: null,
      signal_grade: null,
      close: body[symbol]?.fulldayPrice ?? null,
      error: body[symbol] ? null : 'no quote',
    })),
  };
}

export async function yahooNews(symbol: string): Promise<NewsResponse> {
  try {
    const url = `/market/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=12&quotesCount=0`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`news ${res.status}`);
    const body = await res.json() as { news?: Array<{ title?: string; publisher?: string; link?: string; providerPublishTime?: number }> };
    const items = (body.news || [])
      .filter((item) => item.title && item.link)
      .slice(0, 10)
      .map((item) => ({
        title: item.title || '',
        url: item.link || '',
        source: item.publisher || 'Yahoo',
        time: item.providerPublishTime ? new Date(item.providerPublishTime * 1000).toISOString() : '',
      }));
    return { source: 'Yahoo Finance', items, error: items.length ? null : 'no headlines' };
  } catch (e) {
    return { source: 'Yahoo Finance', items: [], error: e instanceof Error ? e.message : 'news failed' };
  }
}
