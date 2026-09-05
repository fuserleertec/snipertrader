/**
 * Mock ↔ live is env-only.
 *   NEXT_PUBLIC_USE_MOCKS=true  → in-browser streams (offline; default)
 *   NEXT_PUBLIC_USE_MOCKS=false → Data Eng :8000 + Quant :8001
 *
 * Data Eng Phase 2 (PR #5) when live: NEXT_PUBLIC_WS_BASE / NEXT_PUBLIC_HTTP_BASE
 *   /v1/ws/vwap · /v1/ws/avwap · /v1/ws/volume-profile · /v1/ws/kill-zone
 *   /v1/ws/sweep|fvg|mss|ob
 * Quant (PR #2):    NEXT_PUBLIC_QUANT_API_BASE / NEXT_PUBLIC_QUANT_WS_BASE
 */

export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCKS !== "false";
}

export function wsBase(): string {
  return process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000";
}

/**
 * Pattern overlay sockets (DE PR #5). Live only when mocks are off *and*
 * `NEXT_PUBLIC_WS_BASE` is set. Otherwise keep the in-browser mock fallback.
 */
export function isLivePatternWs(): boolean {
  if (isMockMode()) return false;
  const base = process.env.NEXT_PUBLIC_WS_BASE;
  return typeof base === "string" && base.length > 0;
}

/** Empty = same-origin `/v1/*` (Next rewrite → Data Eng). */
export function httpBase(): string {
  const raw = process.env.NEXT_PUBLIC_HTTP_BASE;
  if (raw === undefined || raw === "") return "";
  return raw.replace(/\/$/, "");
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
