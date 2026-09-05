"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type {
  KillZoneEvent,
  OHLCVBar,
  OverlayPreset,
  PatternBook,
  SessionLevels,
  SessionType,
  Signal,
  Timeframe,
  VolumeProfile,
  VWAPValues,
} from "@/lib/types";
import type { Theme } from "@/hooks/useTheme";
import { buildDrawModelFromOverlays, highlightIds, normalizeOverlays } from "@/lib/draw";
import { viewAllows } from "@/lib/setupView";
import { PatternZonesPrimitive } from "./PatternZonesPrimitive";
import { VwapBandsPrimitive } from "./VwapBandsPrimitive";

const SESSION_COLORS: Record<string, string> = {
  open: "#00D4FF",
  high: "#00E5A0",
  low: "#FF4455",
  close: "#F0C040",
};

const SESSION_ABBR: Record<SessionType, string> = {
  asia: "ASIA",
  london: "LDN",
  ny_am: "NYAM",
  ny_pm: "NYPM",
  rth: "RTH",
  eth: "ETH",
  globex: "GLX",
};

function palette(theme: Theme) {
  const light = theme === "light";
  return {
    bg: light ? "#eef2f7" : "#04070c",
    text: light ? "#2A4460" : "#9BB5C8",
    grid: light ? "rgba(0,150,110,0.12)" : "rgba(0,229,160,0.08)",
    border: light ? "rgba(0,150,110,0.25)" : "rgba(0,229,160,0.18)",
    up: light ? "#007A44" : "#00E5A0",
    down: light ? "#C02030" : "#FF4455",
    wickUp: light ? "#007A44" : "#00E5A0",
    wickDown: light ? "#C02030" : "#FF4455",
  };
}

function toCandle(bar: OHLCVBar) {
  return {
    time: Math.floor(bar.open_ts_ms / 1000) as UTCTimestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  };
}

function snapMs(bars: OHLCVBar[], ms: number): number {
  if (!bars.length) return ms;
  let best = bars[0].open_ts_ms;
  let bestD = Math.abs(best - ms);
  for (const bar of bars) {
    const d = Math.abs(bar.open_ts_ms - ms);
    if (d < bestD) {
      bestD = d;
      best = bar.open_ts_ms;
    }
  }
  return best;
}

function snapTime(bars: OHLCVBar[], ms: number): UTCTimestamp {
  return Math.floor(snapMs(bars, ms) / 1000) as UTCTimestamp;
}

export function PriceChart({
  bars,
  historyKey,
  lastBar,
  vwap,
  sessions,
  visibleSessions,
  timeframe,
  theme,
  patterns,
  overlayPreset,
  selected,
  anchorVwap = null,
  volumeProfile = null,
  killZone = null,
}: {
  bars: OHLCVBar[];
  historyKey: string;
  lastBar: OHLCVBar | null;
  vwap: VWAPValues | null;
  sessions: SessionLevels[];
  visibleSessions: SessionType[];
  timeframe: Timeframe;
  theme: Theme;
  patterns: PatternBook;
  overlayPreset: OverlayPreset;
  selected: Signal | null;
  /** Weekly / rolling VWAP for 6_avwap_ob_confluence. */
  anchorVwap?: VWAPValues | null;
  volumeProfile?: VolumeProfile | null;
  killZone?: KillZoneEvent | null;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const bandsRef = useRef<VwapBandsPrimitive | null>(null);
  const zonesRef = useRef<PatternZonesPrimitive | null>(null);
  const vwapLineRef = useRef<IPriceLine | null>(null);
  const avwapLineRef = useRef<IPriceLine | null>(null);
  const sessionLinesRef = useRef<Map<string, IPriceLine>>(new Map());
  const setupLinesRef = useRef<Map<string, IPriceLine>>(new Map());
  const hvnLinesRef = useRef<Map<string, IPriceLine>>(new Map());
  const fittedKey = useRef<string>("");
  const barsRef = useRef(bars);
  useEffect(() => {
    barsRef.current = bars;
  }, [bars]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const colors = palette(theme);
    const chart = createChart(host, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: colors.bg },
        textColor: colors.text,
        fontFamily: "var(--font-space), 'Space Mono', monospace",
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: {
        borderColor: colors.border,
        timeVisible: true,
        secondsVisible: timeframe === "1m",
      },
      crosshair: { mode: CrosshairMode.Normal },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });
    const series = chart.addCandlestickSeries({
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.wickUp,
      wickDownColor: colors.wickDown,
    });
    const bands = new VwapBandsPrimitive();
    const zones = new PatternZonesPrimitive();
    series.attachPrimitive(bands);
    series.attachPrimitive(zones);
    chartRef.current = chart;
    seriesRef.current = series;
    bandsRef.current = bands;
    zonesRef.current = zones;
    fittedKey.current = "";
    if (barsRef.current.length) {
      series.setData(barsRef.current.map(toCandle));
    }

    const sessionLines = sessionLinesRef.current;
    const setupLines = setupLinesRef.current;
    const hvnLines = hvnLinesRef.current;

    return () => {
      sessionLines.clear();
      setupLines.clear();
      hvnLines.clear();
      vwapLineRef.current = null;
      avwapLineRef.current = null;
      bandsRef.current = null;
      zonesRef.current = null;
      seriesRef.current = null;
      chart.remove();
      chartRef.current = null;
    };
  }, [theme, timeframe]);

  useEffect(() => {
    const series = seriesRef.current;
    const data = barsRef.current;
    if (!series || !historyKey || !data.length) return;
    series.setData(data.map(toCandle));
    chartRef.current?.timeScale().fitContent();
    fittedKey.current = historyKey;
  }, [historyKey]);

  useEffect(() => {
    if (!seriesRef.current || !lastBar) return;
    seriesRef.current.update(toCandle(lastBar));
  }, [lastBar]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const fade = overlayPreset === "sd_extension_fade";
    const showVwap = viewAllows(overlayPreset, "vwap");
    bandsRef.current?.setLevels(showVwap ? vwap : null, fade ? "sigma23" : "all");
    const vwapTitle =
      overlayPreset === "sweep_reclaim" ? "ref_vwap" : fade ? "VWAP tgt" : "VWAP";
    const refPrice = !showVwap
      ? null
      : overlayPreset === "sweep_reclaim" && selected?.ref_vwap != null
        ? selected.ref_vwap
        : vwap?.vwap;
    if (refPrice == null) {
      if (vwapLineRef.current) {
        series.removePriceLine(vwapLineRef.current);
        vwapLineRef.current = null;
      }
    } else if (!vwapLineRef.current) {
      vwapLineRef.current = series.createPriceLine({
        price: refPrice,
        color: "#F0C040",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: vwapTitle,
      });
    } else {
      vwapLineRef.current.applyOptions({ price: refPrice, title: vwapTitle });
    }

    const showAvwap = viewAllows(overlayPreset, "avwap");
    const av = showAvwap ? (anchorVwap ?? null) : null;
    if (!av) {
      if (avwapLineRef.current) {
        series.removePriceLine(avwapLineRef.current);
        avwapLineRef.current = null;
      }
    } else if (!avwapLineRef.current) {
      avwapLineRef.current = series.createPriceLine({
        price: av.vwap,
        color: "#7A5FD6",
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "AVWAP",
      });
    } else {
      avwapLineRef.current.applyOptions({ price: av.vwap });
    }
  }, [vwap, anchorVwap, overlayPreset, selected]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const wanted = new Set<string>();
    const visible = new Set(visibleSessions);
    for (const book of sessions) {
      if (!visible.has(book.session_type)) continue;
      const abbr = SESSION_ABBR[book.session_type];
      const specs: Array<["open" | "high" | "low" | "close", number]> = [
        ["open", book.open],
        ["high", book.high],
        ["low", book.low],
        ["close", book.close],
      ];
      for (const [field, price] of specs) {
        const id = `${book.session_type}:${field}`;
        wanted.add(id);
        const existing = sessionLinesRef.current.get(id);
        const opts = {
          price,
          color: SESSION_COLORS[field],
          lineWidth: field === "close" ? 2 as const : 1 as const,
          lineStyle: field === "close" ? LineStyle.Solid : LineStyle.Dotted,
          axisLabelVisible: true,
          title: `${abbr} ${field[0].toUpperCase()}`,
        };
        if (!existing) {
          sessionLinesRef.current.set(id, series.createPriceLine(opts));
        } else {
          existing.applyOptions(opts);
        }
      }
    }
    for (const [id, line] of sessionLinesRef.current) {
      if (!wanted.has(id)) {
        series.removePriceLine(line);
        sessionLinesRef.current.delete(id);
      }
    }
  }, [sessions, visibleSessions]);

  useEffect(() => {
    const highlight = highlightIds(selected);
    const asia = sessions.find((s) => s.session_type === "asia") ?? null;
    const snap = (ms: number) => snapMs(bars, ms);
    const nowMs = bars[bars.length - 1]?.close_ts_ms ?? Date.now();
    const overlays = normalizeOverlays({ book: patterns, asia, selected, nowMs }).map((ov) => {
      if (ov.kind === "zone") return { ...ov, t0: snap(ov.t0), t1: snap(ov.t1) };
      if (ov.kind === "marker") return { ...ov, time: snap(ov.time) };
      if (ov.kind === "session_box") return { ...ov, t0: snap(ov.t0), t1: snap(ov.t1) };
      return { ...ov, time: snap(ov.time) };
    });
    const model = buildDrawModelFromOverlays({
      preset: overlayPreset,
      overlays,
      book: patterns,
      highlight,
      asia,
      killZone,
      sessions,
    });
    for (const z of model.zones) {
      z.start_ms = snap(z.start_ms);
      if (z.end_ms != null) z.end_ms = snap(z.end_ms);
    }
    for (const line of model.lines) {
      line.start_ms = snap(line.start_ms);
      if (line.end_ms != null) line.end_ms = snap(line.end_ms);
    }
    for (const arrow of model.arrows) arrow.ts_ms = snap(arrow.ts_ms);
    if (viewAllows(overlayPreset, "pullback") && vwap) {
      const touch = patterns.obs[0] ?? patterns.fvgs[0];
      if (touch) {
        const start = bars[0]?.open_ts_ms ?? touch.created_ts_ms;
        model.zones.push({
          id: "pullback_vwap",
          kind: "pullback",
          start_ms: snap(start),
          end_ms: null,
          high: Math.max(vwap.vwap, touch.high),
          low: Math.min(vwap.vwap, touch.low),
          fill: "rgba(10,111,176,0.14)",
          stroke: "rgba(10,111,176,0.55)",
          highlight: true,
        });
      }
    }
    if (viewAllows(overlayPreset, "avwap") && patterns.obs[0]) {
      const av = anchorVwap ?? vwap;
      const ob = patterns.obs[0];
      if (av) {
        model.zones.push({
          id: "confluence_avwap_ob",
          kind: "confluence",
          start_ms: snap(ob.created_ts_ms),
          end_ms: null,
          high: Math.max(ob.high, av.vwap + av.sigma),
          low: Math.min(ob.low, av.vwap - av.sigma),
          fill: "rgba(122,95,214,0.18)",
          stroke: "rgba(122,95,214,0.7)",
          highlight: true,
        });
      }
    }
    zonesRef.current?.setModel(model);

    const series = seriesRef.current;
    if (!series || !bars.length) return;
    const markers: Array<{
      time: UTCTimestamp;
      position: "aboveBar" | "belowBar";
      color: string;
      shape: "arrowUp" | "arrowDown" | "circle";
      text: string;
    }> = [];
    for (const arrow of model.arrows) {
      const bits = ["SWEEP"];
      if (arrow.confirmed) bits.push("✓");
      if (arrow.delta) bits.push("Δ");
      if (arrow.highlight) bits.push("★");
      markers.push({
        time: snapTime(bars, arrow.ts_ms),
        position: arrow.side === "sell" ? "aboveBar" : "belowBar",
        color: arrow.color,
        shape: arrow.side === "sell" ? "arrowDown" : "arrowUp",
        text: bits.join(" "),
      });
    }
    for (const ov of overlays) {
      if (ov.kind !== "marker" || ov.source !== "mss") continue;
      if (!viewAllows(overlayPreset, "mss")) continue;
      const hot = highlight.has(ov.id);
      markers.push({
        time: snapTime(bars, ov.time),
        position: ov.direction === "bearish" ? "aboveBar" : "belowBar",
        color: hot ? "#F0C040" : ov.direction === "bullish" ? "#00D4FF" : "#FF8A3D",
        shape: "circle",
        text: hot ? "MSS ★" : "MSS",
      });
    }
    if (viewAllows(overlayPreset, "rejection")) {
      if (vwap) {
        for (const bar of bars.slice(-40)) {
          const rejectHigh = bar.high >= vwap.band_p2 && bar.close < vwap.band_p2;
          const rejectLow = bar.low <= vwap.band_m2 && bar.close > vwap.band_m2;
          if (!rejectHigh && !rejectLow) continue;
          markers.push({
            time: snapTime(bars, bar.open_ts_ms),
            position: rejectHigh ? "aboveBar" : "belowBar",
            color: rejectHigh ? "#C02030" : "#007A44",
            shape: rejectHigh ? "arrowDown" : "arrowUp",
            text: "REJ",
          });
        }
      }
    }
    if (selected && viewAllows(overlayPreset, "entry")) {
      markers.push({
        time: snapTime(bars, selected.ts_ms),
        position: "belowBar",
        color: "#00D4FF",
        shape: "circle",
        text: "ENTRY",
      });
    }
    if (selected && viewAllows(overlayPreset, "disp")) {
      markers.push({
        time: snapTime(bars, selected.ts_ms),
        position: selected.side === "short" ? "aboveBar" : "belowBar",
        color: "#F0C040",
        shape: selected.side === "short" ? "arrowDown" : "arrowUp",
        text: "DISP",
      });
    }
    const byTime = new Map<number, (typeof markers)[number]>();
    for (const m of markers) byTime.set(Number(m.time), m);
    series.setMarkers([...byTime.values()].sort((a, b) => Number(a.time) - Number(b.time)));

    const hvnWanted = new Set<string>();
    const showHvn = viewAllows(overlayPreset, "hvn");
    if (showHvn && volumeProfile) {
      for (const [i, node] of volumeProfile.high_volume_nodes.entries()) {
        const id = `hvn_${i}`;
        hvnWanted.add(id);
        const opts = {
          price: node.price,
          color: "#0A7D8C",
          lineWidth: 1 as const,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: "HVN",
        };
        const existing = hvnLinesRef.current.get(id);
        if (!existing) hvnLinesRef.current.set(id, series.createPriceLine(opts));
        else existing.applyOptions(opts);
      }
    }
    for (const [id, line] of hvnLinesRef.current) {
      if (!hvnWanted.has(id)) {
        series.removePriceLine(line);
        hvnLinesRef.current.delete(id);
      }
    }
  }, [patterns, overlayPreset, selected, sessions, bars, theme, vwap, anchorVwap, volumeProfile, killZone]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const wanted = new Map<string, { price: number; color: string; title: string }>();
    if (selected) {
      wanted.set("E", { price: selected.entry, color: "#00D4FF", title: "E" });
      wanted.set("S", { price: selected.stop, color: "#FF4455", title: "S" });
      wanted.set("T", { price: selected.target, color: "#00E5A0", title: "T" });
    }
    for (const [id, spec] of wanted) {
      const existing = setupLinesRef.current.get(id);
      const opts = {
        price: spec.price,
        color: spec.color,
        lineWidth: 2 as const,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: spec.title,
      };
      if (!existing) setupLinesRef.current.set(id, series.createPriceLine(opts));
      else existing.applyOptions(opts);
    }
    for (const [id, line] of setupLinesRef.current) {
      if (!wanted.has(id)) {
        series.removePriceLine(line);
        setupLinesRef.current.delete(id);
      }
    }
  }, [selected]);

  return (
    <div className="chart-wrap">
      <div ref={hostRef} className="chart-canvas" />
      {!bars.length && <div className="chart-empty">Waiting for OHLCV…</div>}
    </div>
  );
}
