import { viewAllows } from "./setupView";
import type {
  KillZoneEvent,
  Overlay,
  OverlayPreset,
  PatternBook,
  SessionLevels,
  Signal,
  SweepEvent,
} from "./types";
export interface ZoneDraw {
  id: string;
  kind: "fvg" | "ob" | "asia" | "pullback" | "confluence" | "kill_zone";
  start_ms: number;
  end_ms: number | null;
  high: number;
  low: number;
  fill: string;
  stroke: string;
  highlight: boolean;
}

export interface LineDraw {
  id: string;
  start_ms: number;
  end_ms?: number | null;
  price: number;
  end_price?: number;
  color: string;
  highlight: boolean;
  label?: string;
}

export interface ArrowDraw {
  id: string;
  ts_ms: number;
  price: number;
  side: "buy" | "sell";
  color: string;
  highlight: boolean;
  confirmed?: boolean;
  delta?: boolean;
}

export interface PatternDrawModel {
  zones: ZoneDraw[];
  lines: LineDraw[];
  arrows: ArrowDraw[];
}

function zoneT1(created_ts_ms: number, mitigated: boolean | undefined, ttl_seconds: number | undefined, nowMs: number): number {
  if (mitigated) return created_ts_ms + (ttl_seconds ?? 3600) * 1000;
  return nowMs;
}

/** Chart join: highlight overlays whose `id` is in `setup_signals.trigger_event_ids`. */
export function highlightIds(selected: Signal | null): Set<string> {
  const ids = new Set<string>();
  if (!selected) return ids;
  for (const id of selected.trigger_event_ids ?? []) {
    if (id) ids.add(id);
  }
  return ids;
}

/** Schema payloads → FE-only Overlay DTO. `nowMs` extends open FVG/OB to now. */
export function normalizeOverlays(input: {
  book: PatternBook;
  asia: SessionLevels | null;
  selected: Signal | null;
  nowMs: number;
}): Overlay[] {
  const { book, asia, selected, nowMs } = input;
  const out: Overlay[] = [];
  for (const z of book.fvgs) {
    out.push({
      kind: "zone",
      source: "fvg",
      id: z.id,
      symbol: z.symbol,
      t0: z.created_ts_ms,
      t1: zoneT1(z.created_ts_ms, z.mitigated, z.ttl_seconds, nowMs),
      high: z.high,
      low: z.low,
      direction: z.direction,
      mitigated: z.mitigated,
    });
  }
  for (const z of book.obs) {
    out.push({
      kind: "zone",
      source: "ob",
      id: z.id,
      symbol: z.symbol,
      t0: z.created_ts_ms,
      t1: zoneT1(z.created_ts_ms, z.mitigated, z.ttl_seconds, nowMs),
      high: z.high,
      low: z.low,
      direction: z.direction,
      mitigated: z.mitigated,
    });
  }
  for (const sw of book.sweeps) {
    out.push({
      kind: "marker",
      source: "sweep",
      id: sw.id,
      symbol: sw.symbol,
      time: sw.ts_ms,
      price: sw.swept_level,
      side: sw.side,
      confirmed: sw.confirmed,
      delta_divergence: sw.delta_divergence,
    });
  }
  for (const ev of book.mss) {
    out.push({
      kind: "marker",
      source: "mss",
      id: ev.id,
      symbol: ev.symbol,
      time: ev.ts_ms,
      price: ev.broken_level,
      direction: ev.direction,
      confirmed: ev.confirmed,
      trigger_sweep_id: ev.trigger_sweep_id,
    });
  }
  if (asia) {
    out.push({
      kind: "session_box",
      source: "asia",
      symbol: asia.symbol,
      t0: asia.session_start_ms,
      t1: asia.session_end_ms,
      high: asia.high,
      low: asia.low,
    });
  }
  if (selected) {
    out.push({
      kind: "setup",
      id: selected.id,
      symbol: selected.symbol,
      setup_type: selected.setup_type,
      side: selected.side,
      time: selected.ts_ms,
      entry: selected.entry,
      stop: selected.stop,
      target: selected.target,
      trigger_event_ids: selected.trigger_event_ids,
      confidence: selected.confidence,
    });
  }
  return out;
}

function fvgColors(direction: "bullish" | "bearish", mitigated: boolean, highlight: boolean): { fill: string; stroke: string } {
  const bull = direction === "bullish";
  if (highlight) {
    return { fill: bull ? "rgba(0,229,160,0.38)" : "rgba(255,68,85,0.36)", stroke: "#F0C040" };
  }
  if (mitigated) {
    return {
      fill: bull ? "rgba(0,229,160,0.08)" : "rgba(255,68,85,0.08)",
      stroke: bull ? "rgba(0,229,160,0.25)" : "rgba(255,68,85,0.25)",
    };
  }
  return {
    fill: bull ? "rgba(0,229,160,0.22)" : "rgba(255,68,85,0.22)",
    stroke: bull ? "rgba(0,229,160,0.7)" : "rgba(255,68,85,0.7)",
  };
}

function obColors(direction: "bullish" | "bearish", mitigated: boolean, highlight: boolean): { fill: string; stroke: string } {
  if (highlight) return { fill: "rgba(168,85,247,0.48)", stroke: "#F0C040" };
  if (mitigated) return { fill: "rgba(168,85,247,0.10)", stroke: "rgba(192,132,252,0.35)" };
  return {
    fill: direction === "bullish" ? "rgba(168,85,247,0.32)" : "rgba(168,85,247,0.22)",
    stroke: "#C084FC",
  };
}

function asiaExtremeSweep(sw: SweepEvent, asia: SessionLevels | null): boolean {
  if (!asia) return true;
  const span = Math.max(asia.high - asia.low, 1e-9);
  if (sw.side === "sell") return Math.abs(sw.swept_level - asia.high) <= span * 0.08;
  return Math.abs(sw.swept_level - asia.low) <= span * 0.08;
}

export function buildDrawModelFromOverlays(input: {
  preset: OverlayPreset;
  overlays: Overlay[];
  book: PatternBook;
  highlight: Set<string>;
  asia: SessionLevels | null;
  killZone: KillZoneEvent | null;
  sessions?: SessionLevels[];
}): PatternDrawModel {
  const { preset, overlays, book, highlight, asia, killZone, sessions = [] } = input;
  const showFvg = viewAllows(preset, "fvg");
  const showOb = viewAllows(preset, "ob");
  const showSweep = viewAllows(preset, "sweep");
  const showMss = viewAllows(preset, "mss");
  const showAsia = viewAllows(preset, "asia");
  const restrictToTriggers = preset !== "all" && highlight.size > 0;

  const zones: ZoneDraw[] = [];
  const lines: PatternDrawModel["lines"] = [];
  const arrows: PatternDrawModel["arrows"] = [];

  for (const ov of overlays) {
    if (ov.kind === "zone" && ov.source === "fvg" && showFvg) {
      if (restrictToTriggers && !highlight.has(ov.id)) continue;
      const colors = fvgColors(ov.direction, !!ov.mitigated, highlight.has(ov.id));
      zones.push({
        id: ov.id,
        kind: "fvg",
        start_ms: ov.t0,
        end_ms: ov.t1,
        high: ov.high,
        low: ov.low,
        fill: colors.fill,
        stroke: colors.stroke,
        highlight: highlight.has(ov.id),
      });
    }
    if (ov.kind === "zone" && ov.source === "ob" && showOb) {
      if (restrictToTriggers && !highlight.has(ov.id)) continue;
      const colors = obColors(ov.direction, !!ov.mitigated, highlight.has(ov.id));
      zones.push({
        id: ov.id,
        kind: "ob",
        start_ms: ov.t0,
        end_ms: ov.t1,
        high: ov.high,
        low: ov.low,
        fill: colors.fill,
        stroke: colors.stroke,
        highlight: highlight.has(ov.id),
      });
    }
    if (ov.kind === "session_box" && ov.source === "asia" && showAsia) {
      zones.push({
        id: `asia_${ov.t0}`,
        kind: "asia",
        start_ms: ov.t0,
        end_ms: ov.t1,
        high: ov.high,
        low: ov.low,
        fill: "rgba(0,212,255,0.10)",
        stroke: "rgba(0,212,255,0.55)",
        highlight: false,
      });
    }
    if (ov.kind === "marker" && ov.source === "sweep" && showSweep) {
      if (restrictToTriggers && !highlight.has(ov.id)) continue;
      const sw = book.sweeps.find((s) => s.id === ov.id);
      if (preset === "po3_judas" && !restrictToTriggers && sw) {
        const extreme = book.sweeps.filter((row) => asiaExtremeSweep(row, asia));
        if (extreme.length && !extreme.some((row) => row.id === ov.id) && !highlight.has(ov.id)) {
          continue;
        }
      }
      arrows.push({
        id: ov.id,
        ts_ms: ov.time,
        price: ov.price,
        side: ov.side === "buy" ? "buy" : "sell",
        color: highlight.has(ov.id) ? "#F0C040" : ov.side === "sell" ? "#FF4455" : "#00E5A0",
        highlight: highlight.has(ov.id),
        confirmed: ov.confirmed,
        delta: ov.delta_divergence,
      });
    }
    if (ov.kind === "marker" && ov.source === "mss" && showMss) {
      if (restrictToTriggers && !highlight.has(ov.id)) continue;
      const ev = book.mss.find((m) => m.id === ov.id);
      lines.push({
        id: ov.id,
        start_ms: ov.time,
        price: ov.price,
        color: highlight.has(ov.id) ? "#F0C040" : ov.direction === "bullish" ? "#00D4FF" : "#FF8A3D",
        highlight: highlight.has(ov.id),
        label: "MSS",
      });
      if (ev) {
        const swing = ev.direction === "bullish" ? ev.swing_low : ev.swing_high;
        const trigger = book.sweeps.find((s) => s.id === ev.trigger_sweep_id);
        if (swing != null && trigger) {
          lines.push({
            id: `${ov.id}_seg`,
            start_ms: trigger.ts_ms,
            end_ms: ev.ts_ms,
            price: swing,
            end_price: ev.broken_level,
            color: highlight.has(ov.id) || highlight.has(ev.trigger_sweep_id) ? "#F0C040" : "rgba(0,212,255,0.7)",
            highlight: highlight.has(ov.id),
            label: "SWING→BRK",
          });
        }
      }
    }
  }

  if (viewAllows(preset, "kill_zone") && killZone?.active) {
    const band =
      sessions.find((row) => row.session_type === killZone.kill_zone) ??
      asia ??
      sessions[0] ??
      null;
    if (band) {
      zones.push({
        id: `kz_${killZone.start_time}`,
        kind: "kill_zone",
        start_ms: killZone.start_time,
        end_ms: killZone.end_time,
        high: band.high,
        low: band.low,
        fill: "rgba(240,192,64,0.08)",
        stroke: "rgba(240,192,64,0.45)",
        highlight: false,
      });
    }
  }

  return { zones, lines, arrows };
}
