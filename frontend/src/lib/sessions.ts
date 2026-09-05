import { sessionsForAsset } from "./constants";
import type { AssetClass, SessionType } from "./types";

export interface SessionWindow {
  session_type: SessionType;
  start_ms: number;
  end_ms: number;
}

function utcDayStart(ms: number): number {
  const d = new Date(ms);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

function utcAt(dayStart: number, hh: number, mm: number): number {
  return dayStart + (hh * 60 + mm) * 60_000;
}

/** America/New_York wall-clock parts for a UTC instant. */
function nyParts(ms: number): { y: number; mo: number; d: number; h: number; mi: number } {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(fmt.formatToParts(new Date(ms)).map((p) => [p.type, p.value]));
  const h = parts.hour === "24" ? 0 : Number(parts.hour);
  return {
    y: Number(parts.year),
    mo: Number(parts.month),
    d: Number(parts.day),
    h,
    mi: Number(parts.minute),
  };
}

function nyDateUtcMs(y: number, mo: number, d: number, h: number, mi: number): number {
  let guess = Date.UTC(y, mo - 1, d, h + 4, mi);
  for (let i = 0; i < 3; i++) {
    const p = nyParts(guess);
    const target = ((h * 60 + mi) - (p.h * 60 + p.mi)) * 60_000;
    const dayDrift =
      Date.UTC(y, mo - 1, d) - Date.UTC(p.y, p.mo - 1, p.d);
    guess += target + dayDrift;
  }
  return guess;
}

function cryptoWindows(ms: number): SessionWindow[] {
  const day = utcDayStart(ms);
  const prev = day - 86_400_000;
  const next = day + 86_400_000;
  const spec: [SessionType, number, number, number, number][] = [
    ["asia", 0, 0, 7, 0],
    ["london", 7, 0, 13, 30],
    ["ny_am", 13, 30, 15, 0],
    ["ny_pm", 18, 0, 20, 0],
  ];
  const out: SessionWindow[] = [];
  for (const dayStart of [prev, day, next]) {
    for (const [type, sh, sm, eh, em] of spec) {
      out.push({
        session_type: type,
        start_ms: utcAt(dayStart, sh, sm),
        end_ms: utcAt(dayStart, eh, em),
      });
    }
  }
  return out;
}

function nyWindows(ms: number, asset: AssetClass): SessionWindow[] {
  const p = nyParts(ms);
  const days: [number, number, number][] = [];
  const center = Date.UTC(p.y, p.mo - 1, p.d);
  for (const offset of [-1, 0, 1]) {
    const d = new Date(center + offset * 86_400_000);
    const np = nyParts(d.getTime() + 12 * 3600_000);
    days.push([np.y, np.mo, np.d]);
  }
  const out: SessionWindow[] = [];
  for (const [y, mo, d] of days) {
    out.push({
      session_type: "rth",
      start_ms: nyDateUtcMs(y, mo, d, 9, 30),
      end_ms: nyDateUtcMs(y, mo, d, 16, 0),
    });
    if (asset === "equity") {
      out.push({
        session_type: "eth",
        start_ms: nyDateUtcMs(y, mo, d, 4, 0),
        end_ms: nyDateUtcMs(y, mo, d, 20, 0),
      });
    }
    if (asset === "futures") {
      const next = new Date(Date.UTC(y, mo - 1, d) + 86_400_000);
      const n = nyParts(next.getTime() + 12 * 3600_000);
      out.push({
        session_type: "globex",
        start_ms: nyDateUtcMs(y, mo, d, 18, 0),
        end_ms: nyDateUtcMs(n.y, n.mo, n.d, 9, 30),
      });
    }
  }
  return out;
}

export function sessionWindows(asset: AssetClass, ms: number): SessionWindow[] {
  return asset === "crypto" ? cryptoWindows(ms) : nyWindows(ms, asset);
}

export function windowContaining(
  asset: AssetClass,
  session: SessionType,
  ms: number,
): SessionWindow | null {
  return (
    sessionWindows(asset, ms).find(
      (w) => w.session_type === session && ms >= w.start_ms && ms < w.end_ms,
    ) ?? null
  );
}

export function activeSessionTypes(asset: AssetClass, ms: number): SessionType[] {
  const allowed = new Set(sessionsForAsset(asset));
  const types = new Set<SessionType>();
  for (const w of sessionWindows(asset, ms)) {
    if (allowed.has(w.session_type) && ms >= w.start_ms && ms < w.end_ms) {
      types.add(w.session_type);
    }
  }
  return [...types];
}

export function defaultVisibleSessions(asset: AssetClass, ms: number): SessionType[] {
  const active = activeSessionTypes(asset, ms);
  if (active.length) return active;
  const allowed = sessionsForAsset(asset);
  let best: SessionWindow | null = null;
  for (const w of sessionWindows(asset, ms)) {
    if (!allowed.includes(w.session_type) || w.end_ms > ms) continue;
    if (!best || w.end_ms > best.end_ms) best = w;
  }
  return best ? [best.session_type] : [allowed[0]];
}

export function mondayAnchorMs(asset: AssetClass, ms: number): number {
  if (asset === "crypto") {
    const d = new Date(ms);
    const dow = d.getUTCDay();
    const back = dow === 0 ? 6 : dow - 1;
    const day = utcDayStart(ms) - back * 86_400_000;
    return day;
  }
  const p = nyParts(ms);
  const utcNoon = Date.UTC(p.y, p.mo - 1, p.d, 16);
  const dow = new Date(utcNoon).getUTCDay();
  const back = dow === 0 ? 6 : dow - 1;
  const monday = new Date(utcNoon - back * 86_400_000);
  const mp = nyParts(monday.getTime());
  return nyDateUtcMs(mp.y, mp.mo, mp.d, 9, 30);
}
