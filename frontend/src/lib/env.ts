/**
 * Mock ↔ live is env-only.
 *   NEXT_PUBLIC_USE_MOCKS=true  → in-browser streams (offline)
 *   NEXT_PUBLIC_USE_MOCKS=false → Data Eng /v1/* + Quant /signals and /ws/signals
 */

export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCKS !== "false";
}

export function wsBase(): string {
  return process.env.NEXT_PUBLIC_WS_BASE || "ws://localhost:8000";
}

/** Empty = same-origin `/v1/*` (Next rewrite → Data Eng). */
export function httpBase(): string {
  const raw = process.env.NEXT_PUBLIC_HTTP_BASE;
  if (raw === undefined || raw === "") return "";
  return raw.replace(/\/$/, "");
}

/** Quant REST (`/signals`). Falls back to Data Eng HTTP host. */
export function quantHttpBase(): string {
  const raw = process.env.NEXT_PUBLIC_QUANT_HTTP_BASE;
  if (raw === undefined || raw === "") return httpBase();
  return raw.replace(/\/$/, "");
}

/** Quant planned WS (`/ws/signals`). Falls back to Data Eng WS host. */
export function quantWsBase(): string {
  return (process.env.NEXT_PUBLIC_QUANT_WS_BASE || wsBase()).replace(/\/$/, "");
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
