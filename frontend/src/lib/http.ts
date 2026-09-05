import { httpUrl } from "./env";
import type { AnchorType, OHLCVBar, SessionLevels, SessionListResponse, SessionType, VWAPValues } from "./types";

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(httpUrl(path), { cache: "no-store" });
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

/** Planned: GET /v1/ohlcv/{symbol}?timeframe=1m&limit=200 */
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
