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
import type { OHLCVBar, SessionLevels, SessionType, Timeframe, VWAPValues } from "@/lib/types";
import type { Theme } from "@/hooks/useTheme";
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
    bg: light ? "#F0F4F8" : "#020408",
    text: light ? "#2A4460" : "#9BB5C8",
    grid: light ? "rgba(0,150,110,0.12)" : "rgba(0,229,160,0.08)",
    border: light ? "rgba(0,150,110,0.25)" : "rgba(0,229,160,0.18)",
    up: "#00E5A0",
    down: "#FF4455",
    wickUp: "#00E5A0",
    wickDown: "#FF4455",
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

export function PriceChart({
  bars,
  historyKey,
  lastBar,
  vwap,
  sessions,
  visibleSessions,
  timeframe,
  theme,
}: {
  bars: OHLCVBar[];
  historyKey: string;
  lastBar: OHLCVBar | null;
  vwap: VWAPValues | null;
  sessions: SessionLevels[];
  visibleSessions: SessionType[];
  timeframe: Timeframe;
  theme: Theme;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const bandsRef = useRef<VwapBandsPrimitive | null>(null);
  const vwapLineRef = useRef<IPriceLine | null>(null);
  const sessionLinesRef = useRef<Map<string, IPriceLine>>(new Map());
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
    series.attachPrimitive(bands);
    chartRef.current = chart;
    seriesRef.current = series;
    bandsRef.current = bands;
    fittedKey.current = "";
    if (barsRef.current.length) {
      series.setData(barsRef.current.map(toCandle));
    }

    const sessionLines = sessionLinesRef.current;

    return () => {
      sessionLines.clear();
      vwapLineRef.current = null;
      bandsRef.current = null;
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
    bandsRef.current?.setLevels(vwap);
    if (!vwap) {
      if (vwapLineRef.current) {
        series.removePriceLine(vwapLineRef.current);
        vwapLineRef.current = null;
      }
      return;
    }
    if (!vwapLineRef.current) {
      vwapLineRef.current = series.createPriceLine({
        price: vwap.vwap,
        color: "#F0C040",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "VWAP",
      });
    } else {
      vwapLineRef.current.applyOptions({ price: vwap.vwap });
    }
  }, [vwap]);

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

  return (
    <div className="chart-wrap">
      <div ref={hostRef} className="chart-canvas" />
      {!bars.length && <div className="chart-empty">Waiting for OHLCV…</div>}
    </div>
  );
}
