import type { EngineState, Meta, NewsResponse, Quote, ScanResponse, ScanRow } from './types';
import { BOOK, bookName } from './types';
import { yahooNews, yahooScan, yahooState } from './fallback';

/**
 * Stock client. Same shape as the futures dashboard client.
 * VITE_API_URL defaults to the FastAPI app on :8010.
 *
 *   GET /api/health
 *   GET /api/meta?symbol=&timeframe=
 *   GET /api/symbols
 *   GET /api/state?symbol=&timeframe=&min_grade=
 *   GET /api/quote?symbol=
 *   GET /api/broker  ·  POST /api/broker/deploy  ·  POST /api/broker/disconnect
 *   GET /api/broker/positions
 *   WS  /ws
 *
 * There is no stock news route. Headlines use the Yahoo /market proxy.
 * If /api/state is unreachable, the chart falls back to that proxy too.
 * /api/state updates the backend WS "current" symbol, so a scan always
 * re-reads the active symbol last.
 */

export const BASE = (import.meta.env.VITE_API_URL as string | undefined) || 'http://127.0.0.1:8010';

export function wsUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL as string | undefined;
  if (explicit) return explicit.endsWith('/ws') ? explicit : `${explicit.replace(/\/$/, '')}/ws`;
  const http = BASE.replace(/\/$/, '');
  return `${http.replace(/^http/, 'ws')}/ws`;
}

async function get<T>(path: string, timeoutMs = 20000): Promise<T> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(`${BASE}${path}`, { signal: ctrl.signal });
    if (!r.ok) {
      let detail = '';
      try {
        detail = (await r.json()).detail || '';
      } catch {
        /* non-JSON */
      }
      throw new Error(detail || `${path} -> ${r.status}`);
    }
    return r.json() as Promise<T>;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') {
      throw new Error(`${path} timed out`);
    }
    throw e;
  } finally {
    window.clearTimeout(timer);
  }
}

export function fetchHealth(): Promise<{ ok: boolean; provider: string; simulation: boolean; engine: string }> {
  return get('/api/health', 4000);
}

export function fetchMeta(symbol: string, timeframe: string): Promise<Meta> {
  const q = new URLSearchParams({ symbol, timeframe });
  return get<Meta>(`/api/meta?${q}`);
}

export function fetchState(symbol: string, timeframe: string, minGrade: string): Promise<EngineState> {
  const q = new URLSearchParams({ symbol, timeframe, min_grade: minGrade });
  return get<EngineState>(`/api/state?${q}`);
}

export async function fetchStateOrFallback(symbol: string, timeframe: string, minGrade: string): Promise<EngineState> {
  try {
    const st = await fetchState(symbol, timeframe, minGrade);
    return { ...st, feed: 'meridian' };
  } catch {
    return yahooState(symbol, timeframe);
  }
}

export function fetchQuote(symbol: string): Promise<{ quote: Quote }> {
  const q = new URLSearchParams({ symbol });
  return get<{ quote: Quote }>(`/api/quote?${q}`, 5000);
}

function rowFromState(st: EngineState): ScanRow {
  return {
    symbol: st.symbol,
    name: bookName(st.symbol),
    regime: st.regime?.name ?? null,
    bias: st.bias?.dir ?? null,
    grade_l: st.lattice?.grade_l ?? null,
    grade_s: st.lattice?.grade_s ?? null,
    path_status: st.path?.status ?? null,
    signal: st.signal?.side ?? null,
    signal_grade: st.signal?.grade ?? null,
    close: st.close ?? null,
    error: null,
  };
}

export async function fetchScan(timeframe: string, minGrade: string, active: string): Promise<ScanResponse> {
  let symbols = BOOK.map((row) => row.symbol);
  try {
    const res = await get<{ symbols: string[] }>('/api/symbols', 4000);
    if (res.symbols?.length) symbols = res.symbols.map((s) => s.toUpperCase());
  } catch {
    return yahooScan(symbols);
  }
  if (active && !symbols.includes(active)) symbols = [active, ...symbols];
  const ordered = [...symbols.filter((s) => s !== active), active].filter(Boolean);
  const rows: ScanRow[] = [];
  let feed = 'meridian';
  for (const symbol of ordered) {
    try {
      const st = await fetchState(symbol, timeframe, minGrade);
      rows.push(rowFromState(st));
    } catch (e) {
      feed = 'yahoo';
      rows.push({
        symbol,
        name: bookName(symbol),
        regime: null,
        bias: null,
        grade_l: null,
        grade_s: null,
        path_status: null,
        signal: null,
        signal_grade: null,
        close: null,
        error: e instanceof Error ? e.message : 'state failed',
      });
    }
  }
  if (feed === 'yahoo' && rows.every((row) => row.error)) {
    return yahooScan(symbols);
  }
  return { timeframe, min_grade: minGrade, rows, feed };
}

export function fetchNews(symbol: string): Promise<NewsResponse> {
  return yahooNews(symbol);
}
