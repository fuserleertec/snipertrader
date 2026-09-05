import { httpUrl, quantHttpUrl } from "./env";
import { normalizeSignal } from "./signals";
import type {
  AnchorType,
  AnchoredVwap,
  KillZoneEvent,
  OHLCVBar,
  PerformanceSummary,
  SessionLevels,
  SessionListResponse,
  SessionType,
  Signal,
  SignalListQuery,
  SignalListResponse,
  VWAPValues,
  VolumeProfile,
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

/** Same-origin path so Next rewrites hit Quant even when HTTP_BASE points at Data Eng. */
async function getSameOrigin<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(path, { cache: "no-store" });
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

export function signalListPath(query: SignalListQuery = {}, path = "/signals"): string {
  const params = new URLSearchParams();
  if (query.symbol) params.set("symbol", query.symbol);
  if (query.status) params.set("status", query.status);
  if (query.setup_type) params.set("setup_type", query.setup_type);
  if (query.side) params.set("side", query.side);
  if (query.from_ts != null) params.set("from_ts", String(query.from_ts));
  if (query.to_ts != null) params.set("to_ts", String(query.to_ts));
  if (query.limit != null) params.set("limit", String(query.limit));
  if (query.cursor) params.set("cursor", query.cursor);
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

function normalizeList(raw: SignalListResponse | null): SignalListResponse | null {
  if (!raw) return null;
  return {
    items: raw.items.map((row) => normalizeSignal(row)).filter((row): row is Signal => !!row),
    next_cursor: raw.next_cursor ?? null,
  };
}

/** Quant PR #2 `GET /signals` — history is this same list (`from_ts`/`to_ts` + filters). */
export async function fetchSignals(query: SignalListQuery = {}): Promise<SignalListResponse | null> {
  const path = signalListPath(query);
  const viaRewrite = await getSameOrigin<SignalListResponse>(path);
  if (viaRewrite) return normalizeList(viaRewrite);
  return normalizeList(await getJson<SignalListResponse>(path, quantHttpUrl));
}

/** Quant PR #2 `GET /signals/{id}` — same close fields as the list + WS. */
export async function fetchSignal(id: string): Promise<Signal | null> {
  const path = `/signals/${encodeURIComponent(id)}`;
  const viaRewrite = await getSameOrigin<unknown>(path);
  if (viaRewrite) return normalizeSignal(viaRewrite);
  return normalizeSignal(await getJson<unknown>(path, quantHttpUrl));
}

/** Data Eng PR #5 — optional overlay helpers. Same-origin `/v1/*` rewrite. */
export function fetchAvwap(symbol: string, anchorId?: string): Promise<AnchoredVwap | null> {
  const path = anchorId
    ? `/v1/avwap/${symbol}/${encodeURIComponent(anchorId)}`
    : `/v1/avwap/${symbol}`;
  return getJson<AnchoredVwap>(path);
}

export function fetchVolumeProfile(symbol: string, sessionType?: SessionType): Promise<VolumeProfile | null> {
  const path = sessionType ? `/v1/volume-profile/${symbol}/${sessionType}` : `/v1/volume-profile/${symbol}`;
  return getJson<VolumeProfile>(path);
}

export function fetchKillZone(symbol: string): Promise<KillZoneEvent | null> {
  return getJson<KillZoneEvent>(`/v1/kill-zone/${symbol}`);
}

/** Quant PR #2 `GET /performance/summary` via rewrite → :8001, then direct. */
export async function fetchPerformanceSummary(): Promise<PerformanceSummary | null> {
  const viaRewrite = await getSameOrigin<PerformanceSummary>("/performance/summary");
  if (viaRewrite) return viaRewrite;
  return getJson<PerformanceSummary>("/performance/summary", quantHttpUrl);
}
