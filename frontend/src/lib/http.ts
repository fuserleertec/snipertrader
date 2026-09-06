import { DESK_SYMBOL_LIMIT, ENSEMBLE_LIMIT, inferAssetClass, LIST_REFRESH_SEC, wireAssetClass } from "./constants";
import { activeSetupQuery, capCategorized, clampRefreshSec, rankItems } from "./desk";
import { httpUrl, picksHttpUrl, quantHttpUrl } from "./env";
import { normalizeAvwap, normalizeKillZone, normalizeVolumeProfile } from "./overlays";
import { normalizeSignal } from "./signals";
import type {
  AnchorType,
  AnchoredVwap,
  AssetClass,
  AssetTab,
  CategorizedPickItem,
  CategorizedPicksResponse,
  EnsemblePickItem,
  EnsemblePicksResponse,
  KillZoneEvent,
  OHLCVBar,
  PerformanceSummary,
  PickCategory,
  RankComponents,
  SessionLevels,
  SessionListResponse,
  SessionType,
  SetupType,
  Signal,
  SignalListQuery,
  SignalListResponse,
  UniverseSource,
  UniverseTopResponse,
  UniverseTopSymbol,
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

export function joinSymbols(symbols: string[] | undefined, limit = DESK_SYMBOL_LIMIT): string | undefined {
  if (!symbols?.length) return undefined;
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of symbols) {
    const sym = raw.trim().toUpperCase();
    if (!sym || seen.has(sym)) continue;
    seen.add(sym);
    out.push(sym);
    if (out.length >= limit) break;
  }
  return out.length ? out.join(",") : undefined;
}

export function signalListPath(query: SignalListQuery = {}, path = "/signals"): string {
  const params = new URLSearchParams();
  const multi = joinSymbols(query.symbols);
  if (multi) params.set("symbols", multi);
  else if (query.symbol) params.set("symbol", query.symbol);
  if (query.status) params.set("status", query.status);
  if (query.setup_type) params.set("setup_type", query.setup_type);
  if (query.side) params.set("side", query.side);
  const asset = wireAssetClass(query.asset_class);
  if (asset) params.set("asset_class", asset);
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

/** Quant PR #2 `GET /signals` — `{ items: Signal[], next_cursor }`. */
export async function fetchSignals(query: SignalListQuery = {}): Promise<SignalListResponse | null> {
  const path = signalListPath(query);
  const viaRewrite = await getSameOrigin<SignalListResponse>(path);
  if (viaRewrite) return normalizeList(viaRewrite);
  return normalizeList(await getJson<SignalListResponse>(path, quantHttpUrl));
}

/**
 * Active Setup Cards — exact Quant query:
 * GET /signals?status=ACTIVE&asset_class=futures|equity|crypto&setup_type=&symbol=&limit=
 * Stocks tab maps to `equity`.
 */
export function fetchActiveSetups(
  tab: AssetTab,
  extras: { setup_type?: SetupType | "all"; symbol?: string; limit?: number } = {},
): Promise<SignalListResponse | null> {
  return fetchSignals(activeSetupQuery(tab, extras));
}

/** Quant PR #2 `GET /signals/{id}` — same close fields as the list + WS. */
export async function fetchSignal(id: string): Promise<Signal | null> {
  const path = `/signals/${encodeURIComponent(id)}`;
  const viaRewrite = await getSameOrigin<unknown>(path);
  if (viaRewrite) return normalizeSignal(viaRewrite);
  return normalizeSignal(await getJson<unknown>(path, quantHttpUrl));
}

/** DE Phase 2 — `GET /v1/avwap/{symbol}` or `/{anchor_id}`. Same-origin `/v1/*` rewrite. */
export async function fetchAvwap(symbol: string, anchorId?: string): Promise<AnchoredVwap | null> {
  const path = anchorId
    ? `/v1/avwap/${symbol}/${encodeURIComponent(anchorId)}`
    : `/v1/avwap/${symbol}`;
  return normalizeAvwap(await getJson<unknown>(path));
}

/** DE Phase 2 — one session book, or unwrap `{ profiles: [{ value }] }`. */
export async function fetchVolumeProfile(symbol: string, sessionType?: SessionType): Promise<VolumeProfile | null> {
  if (sessionType) {
    return normalizeVolumeProfile(await getJson<unknown>(`/v1/volume-profile/${symbol}/${sessionType}`));
  }
  const listed = await getJson<unknown>(`/v1/volume-profile/${symbol}`);
  const fromList = normalizeVolumeProfile(listed);
  if (fromList) return fromList;
  return normalizeVolumeProfile(await getJson<unknown>(`/v1/volume-profile/${symbol}/asia`));
}

export async function fetchKillZone(symbol: string): Promise<KillZoneEvent | null> {
  return normalizeKillZone(await getJson<unknown>(`/v1/kill-zone/${symbol}`));
}

/** Quant PR #2 `GET /performance/summary` via rewrite → :8001, then direct. Optional `symbols=` (≤20). */
export async function fetchPerformanceSummary(symbols?: string[]): Promise<PerformanceSummary | null> {
  const joined = joinSymbols(symbols);
  const path = joined ? `/performance/summary?symbols=${encodeURIComponent(joined)}` : "/performance/summary";
  const viaRewrite = await getSameOrigin<PerformanceSummary>(path);
  if (viaRewrite) return viaRewrite;
  return getJson<PerformanceSummary>(path, quantHttpUrl);
}

/**
 * GET /signals/history — same filters as GET /signals.
 * Falls back to GET /signals when the history path is not deployed yet.
 */
export async function fetchSignalHistory(query: SignalListQuery = {}): Promise<SignalListResponse | null> {
  const path = signalListPath(query, "/signals/history");
  const viaRewrite = await getSameOrigin<SignalListResponse>(path);
  if (viaRewrite) return normalizeList(viaRewrite);
  const direct = await getJson<SignalListResponse>(path, quantHttpUrl);
  if (direct) return normalizeList(direct);
  return fetchSignals(query);
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readSetupTypes(raw: unknown): SetupType[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter((x): x is SetupType => typeof x === "string" && x !== "ob_fvg");
}

function readComponents(raw: unknown): RankComponents {
  const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    setup_quality: num(row.setup_quality),
    risk_adjusted: num(row.risk_adjusted),
    kill_zone: num(row.kill_zone),
    volume: num(row.volume),
    freshness: num(row.freshness),
  };
}

export function normalizeEnsemblePicks(raw: unknown): EnsemblePicksResponse | null {
  if (!raw || typeof raw !== "object") return null;
  const body = raw as Record<string, unknown>;
  const rows = Array.isArray(body.items) ? body.items : [];
  const items: EnsemblePickItem[] = [];
  for (const item of rows) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    if (typeof row.symbol !== "string" || !row.symbol) continue;
    const asset = (wireAssetClass(typeof row.asset_class === "string" ? row.asset_class : "") ??
      inferAssetClass(row.symbol)) as AssetClass;
    const hasEnsemble = typeof row.ensemble_score === "number" && Number.isFinite(row.ensemble_score);
    const ensemble_score = hasEnsemble ? (row.ensemble_score as number) : undefined;
    const score = ensemble_score ?? num(row.score);
    const best = typeof row.best_confidence === "number" && Number.isFinite(row.best_confidence)
      ? row.best_confidence
      : undefined;
    const factors = Array.isArray(row.contributing_factors)
      ? row.contributing_factors.filter((x): x is string => typeof x === "string")
      : undefined;
    const hasComponents = row.rank_components && typeof row.rank_components === "object";
    items.push({
      rank: num(row.rank, items.length + 1),
      symbol: row.symbol.toUpperCase(),
      asset_class: asset,
      score,
      setup_types: readSetupTypes(row.setup_types),
      confidence: best ?? num(row.confidence),
      ...(ensemble_score != null ? { ensemble_score } : {}),
      ...(hasComponents ? { rank_components: readComponents(row.rank_components) } : {}),
      ...(factors?.length ? { contributing_factors: factors } : {}),
      ...(best != null ? { best_confidence: best } : {}),
    });
  }
  const source: UniverseSource | undefined =
    body.universe_source === "DE" ? "DE" : body.universe_source === "SETUP_UNIVERSE" ? "SETUP_UNIVERSE" : undefined;
  return {
    as_of_ts_ms: num(body.as_of_ts_ms),
    refresh_sec: clampRefreshSec(body.refresh_sec ?? LIST_REFRESH_SEC),
    ...(source ? { universe_source: source } : {}),
    items: rankItems(items).slice(0, ENSEMBLE_LIMIT),
  };
}

const PICK_CATS = new Set(["momentum", "mean_reversion", "confluence", "other"]);

export function normalizeCategorizedPicks(raw: unknown): CategorizedPicksResponse | null {
  if (!raw || typeof raw !== "object") return null;
  const body = raw as Record<string, unknown>;
  const rows = Array.isArray(body.items) ? body.items : [];
  const items: CategorizedPickItem[] = [];
  for (const item of rows) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    if (typeof row.symbol !== "string" || !row.symbol) continue;
    const cat = typeof row.category === "string" && PICK_CATS.has(row.category) ? (row.category as PickCategory) : "other";
    const asset = (wireAssetClass(typeof row.asset_class === "string" ? row.asset_class : "") ??
      inferAssetClass(row.symbol)) as AssetClass;
    items.push({
      symbol: row.symbol.toUpperCase(),
      asset_class: asset,
      category: cat,
      score: num(row.score),
      confidence: num(row.confidence, num(row.score) / 100),
      setup_types: readSetupTypes(row.setup_types),
      entry: num(row.entry),
      stop: num(row.stop),
      target: num(row.target),
      atr: num(row.atr, Math.abs(num(row.entry) - num(row.stop))),
      reward_risk: num(row.reward_risk, row.rewardRisk as number),
    });
  }
  const source: UniverseSource = body.universe_source === "DE" ? "DE" : "SETUP_UNIVERSE";
  return {
    as_of_ts_ms: num(body.as_of_ts_ms, Date.now()),
    refresh_sec: clampRefreshSec(body.refresh_sec ?? LIST_REFRESH_SEC),
    universe_source: source,
    items: capCategorized(items).slice(0, DESK_SYMBOL_LIMIT),
  };
}

async function getPicksJson<T>(path: string): Promise<T | null> {
  const viaRewrite = await getSameOrigin<T>(path);
  if (viaRewrite) return viaRewrite;
  return getJson<T>(path, picksHttpUrl);
}

/** GET /picks/ensemble — top 10 ranked symbols. */
export async function fetchEnsemblePicks(): Promise<EnsemblePicksResponse | null> {
  return normalizeEnsemblePicks(await getPicksJson<unknown>("/picks/ensemble"));
}

export function normalizeUniverseTop(raw: unknown, fallbackLimit = ENSEMBLE_LIMIT): UniverseTopResponse | null {
  if (!raw || typeof raw !== "object") return null;
  const body = raw as Record<string, unknown>;
  const rows = Array.isArray(body.symbols) ? body.symbols : Array.isArray(body.items) ? body.items : [];
  const symbols: UniverseTopSymbol[] = [];
  for (const item of rows) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    if (typeof row.symbol !== "string" || !row.symbol) continue;
    const asset = (wireAssetClass(typeof row.asset_class === "string" ? row.asset_class : "") ??
      inferAssetClass(row.symbol)) as AssetClass;
    symbols.push({
      symbol: row.symbol.toUpperCase(),
      asset_class: asset,
      rank: num(row.rank, symbols.length + 1),
      score: num(row.score),
    });
  }
  if (!symbols.length) return null;
  const limit = Math.min(DESK_SYMBOL_LIMIT, Math.max(1, num(body.limit, fallbackLimit)));
  return {
    as_of_ts_ms: num(body.as_of_ts_ms, Date.now()),
    limit,
    symbols: symbols.sort((a, b) => a.rank - b.rank).slice(0, limit),
  };
}

/** DE `GET /v1/universe/top?limit=10|20` — allowed set. Quant re-ranks P0/P4. */
export async function fetchUniverseTop(limit: number): Promise<UniverseTopResponse | null> {
  const cap = limit <= ENSEMBLE_LIMIT ? ENSEMBLE_LIMIT : DESK_SYMBOL_LIMIT;
  return normalizeUniverseTop(await getJson<unknown>(`/v1/universe/top?limit=${cap}`), cap);
}

/** GET /picks/categorized?asset_class=&limit=20 — no class required; ≤20 symbols. */
export async function fetchCategorizedPicks(query: {
  asset_class?: AssetClass | "stocks";
  limit?: number;
} = {}): Promise<CategorizedPicksResponse | null> {
  const params = new URLSearchParams();
  const asset = wireAssetClass(query.asset_class);
  if (asset) params.set("asset_class", asset);
  params.set("limit", String(query.limit ?? DESK_SYMBOL_LIMIT));
  const path = `/picks/categorized?${params.toString()}`;
  return normalizeCategorizedPicks(await getPicksJson<unknown>(path));
}
