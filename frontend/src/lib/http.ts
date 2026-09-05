import { httpUrl, quantHttpUrl } from "./env";
import type {
  AnchorType,
  OHLCVBar,
  PerformanceSummary,
  SessionLevels,
  SessionListResponse,
  SessionType,
  Signal,
  SignalListQuery,
  SignalListResponse,
  VWAPValues,
} from "./types";

async function getJson<T>(path: string, buildUrl: (path: string) => string = httpUrl): Promise<T | null> {
  try {
    const res = await fetch(buildUrl(path), { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function fetchVwap(symbol: string, anchor: AnchorType): Promise<VWAPValues | null> {
  return getJson<VWAPValues>(`/v1/vwap/${symbol}?anchor=${anchor}`);
}

export function fetchSession(symbol: string, sessionType: SessionType): Promise<SessionLevels | null> {
  return getJson<SessionLevels>(`/v1/session/${symbol}/${sessionType}`);
}

export function fetchSessions(symbol: string): Promise<SessionListResponse | null> {
  return getJson<SessionListResponse>(`/v1/session/${symbol}`);
}

/** LIVE (PR #1): GET /v1/ohlcv/{symbol}?timeframe=1m&limit=200 → { symbol, timeframe, bars } */
export async function fetchOhlcv(
  symbol: string,
  timeframe: string,
  limit = 200,
): Promise<OHLCVBar[]> {
  const body = await getJson<OHLCVBar[] | { bars?: OHLCVBar[] }>(
    `/v1/ohlcv/${symbol}?timeframe=${timeframe}&limit=${limit}`,
  );
  if (!body) return [];
  if (Array.isArray(body)) return body;
  return body.bars ?? [];
}

export async function fetchSignals(query: SignalListQuery = {}): Promise<SignalListResponse | null> {
  const params = new URLSearchParams();
  if (query.symbol) params.set("symbol", query.symbol);
  if (query.status) params.set("status", query.status);
  if (query.setup_type) params.set("setup_type", query.setup_type);
  if (query.from_ts != null) params.set("from_ts", String(query.from_ts));
  if (query.to_ts != null) params.set("to_ts", String(query.to_ts));
  if (query.limit != null) params.set("limit", String(query.limit));
  const qs = params.toString();
  return getJson<SignalListResponse>(`/signals${qs ? `?${qs}` : ""}`, quantHttpUrl);
}

export function fetchSignal(id: string): Promise<Signal | null> {
  return getJson<Signal>(`/signals/${id}`, quantHttpUrl);
}

/** Quant PR #2 `GET /performance/summary` via rewrite → :8001, then direct. */
export async function fetchPerformanceSummary(): Promise<PerformanceSummary | null> {
  const viaRewrite = await getJson<PerformanceSummary>("/performance/summary");
  if (viaRewrite) return viaRewrite;
  return getJson<PerformanceSummary>("/performance/summary", quantHttpUrl);
}
