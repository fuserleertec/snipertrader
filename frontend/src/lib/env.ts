/**
 * Mock ↔ live is env-only.
 *   NEXT_PUBLIC_USE_MOCKS=true  → in-browser streams (offline; default)
 *   NEXT_PUBLIC_USE_MOCKS=false → Data Eng :8000 + Quant :8001
 *
 * Data Eng Phase 2 (PR #5) when live: NEXT_PUBLIC_WS_BASE / NEXT_PUBLIC_HTTP_BASE
 *   /v1/ws/vwap · /v1/ws/avwap · /v1/ws/volume-profile · /v1/ws/kill-zone
 *   /v1/ws/sweep|fvg|mss|ob
 * Quant (PR #2):    NEXT_PUBLIC_QUANT_API_BASE / NEXT_PUBLIC_QUANT_WS_BASE
 *
 * List / ranking placeholders (Quant :8001 until ML/DE own them):
 *   GET /picks/ensemble          → top 10  (as_of_ts_ms, refresh_sec=900, items[];
 *                                  score ← ensemble_score, confidence ← best_confidence;
 *                                  optional rank_components + contributing_factors)
 *   GET /picks/categorized       → ≤20     (?asset_class=&limit=20)
 *   GET /signals                 → multi-symbol desk (~20; ?symbols= + filters;
 *                                  keep contributing_factors + factor_breakdown;
 *                                  optional ensemble_score / rank_components)
 *   GET /signals/history         → same filters; falls back to GET /signals
 *   GET /performance/summary     → optional ?symbols= (≤20)
 *   GET /v1/universe             → prepared (same known fields, cap 20); not the selector
 *   GET /v1/universe/top         → DE PR #12 LIVE :8000 (limit=10|20;
 *                                  schemas/universe_top.schema.json). Mock only if USE_MOCKS=true.
 *   GET/WS /v1/ohlcv|vwap|session|avwap|volume-profile|kill-zone
 *                                → per-symbol; full universe incl ES/CL/GC/NQ seeded
 * live_trading is never flipped here. Paper / mocks only.
 */

export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCKS !== "false";
}

/**
 * DE PR #12 is live at :8000. Universe selector + chart HTTP go live when
 * mocks are off. No mock substitution on a live miss.
 */
export function isLiveDeHttp(): boolean {
  return !isMockMode();
}

/** Optional override of Quant list paths. Empty = same-origin `/picks/*` rewrite. */
export function picksHttpBase(): string {
  const raw = process.env.NEXT_PUBLIC_PICKS_API_BASE || process.env.NEXT_PUBLIC_QUANT_API_BASE;
  if (raw === undefined || raw === "") return "http://localhost:8001";
  return raw.replace(/\/$/, "");
}

export function picksHttpUrl(path: string): string {
  const base = picksHttpBase();
  if (!base) return path;
  return `${base}${path}`;
}

export function wsBase(): string {
  return process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000";
}

/**
 * Pattern overlay sockets. Live when mocks are off (DE :8000).
 * In-browser mock fallback only if NEXT_PUBLIC_USE_MOCKS=true.
 */
export function isLivePatternWs(): boolean {
  return isLiveDeHttp();
}

/** Same-origin `/v1/*` rewrite when unset. Live DE default is :8000. */
export function httpBase(): string {
  const raw = process.env.NEXT_PUBLIC_HTTP_BASE;
  if (raw === undefined || raw === "") return "";
  return raw.replace(/\/$/, "");
}

/** Direct DE HTTP. Used after same-origin rewrite miss. */
export function deHttpBase(): string {
  const raw = process.env.NEXT_PUBLIC_HTTP_BASE;
  if (raw === undefined || raw === "") return "http://localhost:8000";
  return raw.replace(/\/$/, "");
}

export function deHttpUrl(path: string): string {
  return `${deHttpBase()}${path}`;
}

/**
 * Quant REST (`/signals`, `/performance/summary`). Default :8001.
 * `NEXT_PUBLIC_QUANT_API_BASE` is canonical; `QUANT_HTTP_BASE` is an alias.
 */
export function quantHttpBase(): string {
  const raw =
    process.env.NEXT_PUBLIC_QUANT_API_BASE || process.env.NEXT_PUBLIC_QUANT_HTTP_BASE;
  if (raw === undefined || raw === "") return "http://localhost:8001";
  return raw.replace(/\/$/, "");
}

/** Quant WS (`/ws/signals`). Default ws://localhost:8001 — not Data Eng :8000. */
export function quantWsBase(): string {
  return (process.env.NEXT_PUBLIC_QUANT_WS_BASE || "ws://localhost:8001").replace(/\/$/, "");
}

export function httpUrl(path: string): string {
  const base = httpBase();
  if (!base) return path;
  return `${base}${path}`;
}

export function quantHttpUrl(path: string): string {
  const base = quantHttpBase();
  if (!base) return path;
  return `${base}${path}`;
}

export function wsUrl(path: string, params: Record<string, string> = {}): string {
  return buildWsUrl(wsBase(), path, params);
}

export function quantWsUrl(path: string, params: Record<string, string> = {}): string {
  return buildWsUrl(quantWsBase(), path, params);
}

function buildWsUrl(base: string, path: string, params: Record<string, string>): string {
  const url = new URL(`${base.replace(/\/$/, "")}${path}`);
  for (const [key, value] of Object.entries(params)) {
    if (value !== "") url.searchParams.set(key, value);
  }
  return url.toString();
}
