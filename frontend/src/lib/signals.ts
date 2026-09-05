import type { Signal, SignalWsEvent } from "./types";

function fmtPx(n: number): string {
  return n >= 1000 ? n.toFixed(1) : n.toFixed(2);
}

/** Display-only. zone_low / zone_high are derived from stop/entry — not wire fields. */
export function zoneLowHigh(signal: Signal): { zone_low: number; zone_high: number } {
  return {
    zone_low: Math.min(signal.stop, signal.entry),
    zone_high: Math.max(signal.stop, signal.entry),
  };
}

export function zoneLabel(signal: Signal): string {
  const { zone_low, zone_high } = zoneLowHigh(signal);
  return `${fmtPx(zone_low)}–${fmtPx(zone_high)}  E ${fmtPx(signal.entry)}  S ${fmtPx(signal.stop)}  T ${fmtPx(signal.target)}`;
}

export function isSignal(value: unknown): value is Signal {
  if (!value || typeof value !== "object") return false;
  const s = value as Signal;
  return (
    typeof s.id === "string" &&
    typeof s.ts_ms === "number" &&
    typeof s.symbol === "string" &&
    typeof s.setup_type === "string" &&
    typeof s.side === "string" &&
    typeof s.entry === "number" &&
    typeof s.stop === "number" &&
    typeof s.target === "number" &&
    typeof s.status === "string"
  );
}

export function isSignalWsEvent(value: unknown): value is SignalWsEvent {
  if (!value || typeof value !== "object") return false;
  const ev = value as SignalWsEvent;
  return (ev.type === "signal.upsert" || ev.type === "signal.status") && isSignal(ev.signal);
}

export function upsertSignal(prev: Signal[], signal: Signal): Signal[] {
  const next = [signal, ...prev.filter((row) => row.id !== signal.id)];
  next.sort((a, b) => b.ts_ms - a.ts_ms);
  return next.slice(0, 80);
}
