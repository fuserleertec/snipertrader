import { useEffect, useRef } from 'react';
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { Bar, DeskQuote, Feed, ThemeName, Timeframe } from '../types';
import type { Study } from '../lib/ta';
import { fmtPx } from '../lib/format';

interface PriceChartProps {
  bars: Bar[];
  study: Study;
  quote: DeskQuote | null;
  timeframe: Timeframe;
  theme: ThemeName;
  feed: Feed;
  loading: boolean;
  fitKey: string;
}

function cssVar(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function stamp(time: number): UTCTimestamp {
  return time as UTCTimestamp;
}

export function PriceChart({ bars, study, quote, timeframe, theme, feed, loading, fitKey }: PriceChartProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const linesRef = useRef<Array<ISeriesApi<'Line'>> | null>(null);
  const fittedRef = useRef('');

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const bull = cssVar('--bull', '#22C55E');
    const bear = cssVar('--bear', '#EF4444');
    const vwap = cssVar('--vwap', '#F97316');
    const text = cssVar('--text3', '#93B4A5');
    const grid = cssVar('--grid', 'rgba(16,185,129,0.08)');
    const bg = cssVar('--panel', '#071a14');
    const chart = createChart(host, {
      width: host.clientWidth,
      height: host.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: bg },
        textColor: text,
        fontFamily: '"Space Mono", ui-monospace, monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: grid },
        horzLines: { color: grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: grid, scaleMargins: { top: 0.08, bottom: 0.22 } },
      timeScale: { borderColor: grid, timeVisible: timeframe !== '1d', secondsVisible: false },
      localization: {
        timeFormatter: (time: number) =>
          new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/New_York',
            month: 'short',
            day: 'numeric',
            hour: timeframe === '1d' ? undefined : '2-digit',
            minute: timeframe === '1d' ? undefined : '2-digit',
          }).format(time * 1000),
      },
    });
    const candles = chart.addCandlestickSeries({
      upColor: bull,
      downColor: bear,
      borderUpColor: bull,
      borderDownColor: bear,
      wickUpColor: bull,
      wickDownColor: bear,
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const line = (color: string, width: 1 | 2, dashed = false) =>
      chart.addLineSeries({
        color,
        lineWidth: width,
        lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
    linesRef.current = [
      line(vwap, 2),
      line(bear, 1, true),
      line(bear, 1, true),
      line(cssVar('--band2', 'rgba(239,68,68,0.45)'), 1, true),
      line(cssVar('--band2', 'rgba(239,68,68,0.45)'), 1, true),
      line(bull, 1),
      line(cssVar('--ema21', '#9CA5C4'), 1),
      line(cssVar('--text4', '#5A7567'), 1),
    ];
    chartRef.current = chart;
    candleRef.current = candles;
    volumeRef.current = volume;
    const observer = new ResizeObserver(() => {
      chart.applyOptions({ width: host.clientWidth, height: host.clientHeight });
    });
    observer.observe(host);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      linesRef.current = null;
    };
  }, [theme, timeframe]);

  useEffect(() => {
    const candles = candleRef.current;
    const volume = volumeRef.current;
    const lines = linesRef.current;
    const chart = chartRef.current;
    if (!candles || !volume || !lines || !chart) return;
    const bull = cssVar('--bull', '#22C55E');
    const bear = cssVar('--bear', '#EF4444');
    candles.setData(bars.map((bar) => ({ ...bar, time: stamp(bar.time) })));
    volume.setData(
      bars.map((bar) => ({
        time: stamp(bar.time),
        value: bar.volume,
        color: bar.close >= bar.open ? `${bull}88` : `${bear}88`,
      })),
    );
    const sets = [study.vwap, study.band1u, study.band1d, study.band2u, study.band2d, study.ema9, study.ema21, study.ema50];
    sets.forEach((series, index) => {
      lines[index].setData(series.map((point) => ({ time: stamp(point.time), value: point.value })));
    });
    if (fittedRef.current !== fitKey) {
      chart.timeScale().fitContent();
      fittedRef.current = fitKey;
    }
  }, [bars, study, theme, timeframe, fitKey]);

  const last = study.last;

  return (
    <section className="panel chart-panel">
      <div className="panel-h">
        <span>Price · VWAP</span>
        <span className="panel-meta">
          {quote ? `${quote.symbol} · ${quote.instrument} · ${quote.exchange}` : 'US equities'}
          {bars.length ? ` · ${bars.length} bars` : ''}
          {feed === 'yahoo' ? ' · delayed' : ''}
        </span>
      </div>
      <div className="chart-stage">
        <div ref={hostRef} className="chart-host" />
        {loading && !bars.length ? <div className="chart-msg">Loading chart…</div> : null}
        {!loading && !bars.length ? <div className="chart-msg">No bars for this symbol.</div> : null}
      </div>
      <div className="legend">
        <span><i className="sw close" /> Close {fmtPx(last?.close)}</span>
        <span><i className="sw vwap" /> VWAP {fmtPx(last?.vwap)}</span>
        <span><i className="sw band" /> ±1σ ±2σ</span>
        <span><i className="sw ema9" /> EMA 9 {fmtPx(last?.ema9)}</span>
        <span><i className="sw ema21" /> EMA 21 {fmtPx(last?.ema21)}</span>
        <span><i className="sw ema50" /> EMA 50 {fmtPx(last?.ema50)}</span>
      </div>
    </section>
  );
}
