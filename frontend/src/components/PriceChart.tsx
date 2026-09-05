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
  OHLCVBar,
  OverlayPreset,
  PatternBook,
  SessionLevels,
  SessionType,
  Signal,
  Timeframe,
  VWAPValues,
} from "@/lib/types";
import type { Theme } from "@/hooks/useTheme";
import { buildDrawModel, PatternZonesPrimitive } from "./PatternZonesPrimitive";
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

    return () => {
      sessionLines.clear();
      setupLines.clear();
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
    bandsRef.current?.setLevels(vwap, fade ? "sigma23" : "all");
    const vwapTitle = fade ? "VWAP tgt" : "VWAP";
    if (!vwap) {
      if (vwapLineRef.current) {
        series.removePriceLine(vwapLineRef.current);
        vwapLineRef.current = null;
      }
    } else if (!vwapLineRef.current) {
      vwapLineRef.current = series.createPriceLine({
        price: vwap.vwap,
        color: "#F0C040",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: vwapTitle,
      });
    } else {
      vwapLineRef.current.applyOptions({ price: vwap.vwap, title: vwapTitle });
    }

    const showAvwap = overlayPreset === "avwap_ob_confluence" || overlayPreset === "all";
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
  }, [vwap, anchorVwap, overlayPreset]);

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
    const highlight = new Set(selected?.trigger_event_ids ?? []);
    const asia = overlayPreset === "po3_judas" || overlayPreset === "all"
      ? sessions.find((s) => s.session_type === "asia") ?? null
      : null;
    const snap = (ms: number) => snapMs(bars, ms);
    const model = buildDrawModel(
      overlayPreset,
      patterns.fvgs.map((z) => ({ ...z, created_ts_ms: snap(z.created_ts_ms) })),
      patterns.obs.map((z) => ({
        ...z,
        created_ts_ms: snap(z.created_ts_ms),
        displacement_ts_ms: z.displacement_ts_ms != null ? snap(z.displacement_ts_ms) : undefined,
      })),
      patterns.mss.map((ev) => ({ ...ev, ts_ms: snap(ev.ts_ms) })),
      patterns.sweeps.map((sw) => ({ ...sw, ts_ms: snap(sw.ts_ms) })),
      highlight,
      asia,
    );
    if ((overlayPreset === "vwap_pullback_cont" || overlayPreset === "all") && vwap) {
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
    if ((overlayPreset === "avwap_ob_confluence" || overlayPreset === "all") && patterns.obs[0]) {
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
    const showSweep = overlayPreset === "all" || overlayPreset === "sweep_reclaim" || overlayPreset === "po3_judas";
    const showMss = overlayPreset === "all" || overlayPreset === "sweep_reclaim" || overlayPreset === "po3_judas";
    const markers: Array<{
      time: UTCTimestamp;
      position: "aboveBar" | "belowBar";
      color: string;
      shape: "arrowUp" | "arrowDown" | "circle";
      text: string;
    }> = [];
    if (showSweep) {
      for (const sw of patterns.sweeps) {
        const hot = highlight.has(sw.id);
        // sell = session high swept (arrow at high); buy = session low swept (arrow at low)
        markers.push({
          time: snapTime(bars, sw.ts_ms),
          position: sw.side === "sell" ? "aboveBar" : "belowBar",
          color: hot ? "#F0C040" : sw.side === "sell" ? "#FF4455" : "#00E5A0",
          shape: sw.side === "sell" ? "arrowDown" : "arrowUp",
          text: hot ? "SWEEP ★" : "SWEEP",
        });
      }
    }
    if (overlayPreset === "sd_extension_fade" || overlayPreset === "all") {
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
    if (showMss) {
      for (const ev of patterns.mss) {
        const hot = highlight.has(ev.id);
        markers.push({
          time: snapTime(bars, ev.ts_ms),
          position: ev.direction === "bearish" ? "aboveBar" : "belowBar",
          color: hot ? "#F0C040" : ev.direction === "bullish" ? "#00D4FF" : "#FF8A3D",
          shape: "circle",
          text: hot ? "MSS ★" : "MSS",
        });
      }
    }
    series.setMarkers(markers);
  }, [patterns, overlayPreset, selected, sessions, bars, theme, vwap, anchorVwap]);

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
