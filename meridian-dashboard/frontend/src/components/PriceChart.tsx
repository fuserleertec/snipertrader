import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import type { Candle as FuturesCandle, EngineView, PathCard } from '../types';
import { fmtEtAxis, px } from '../clock';

const L = 78;
const R = 10;
const T = 10;
const B = 28;
const MIN_BARS = 5;

interface Props {
  candles: FuturesCandle[];
  engine: EngineView | null;
  card: PathCard | null;
  sampleNote: string | null;
}

interface Span {
  start: number;
  end: number;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function finite(values: number[]): number[] {
  return values.filter((n) => Number.isFinite(n));
}

/** Zoom the bar window around a fraction of the current span. null means fit all. */
function zoomSpan(n: number, span: Span, factor: number, anchorFrac: number): Span | null {
  const count = Math.max(2, span.end - span.start);
  let next = Math.round(count * factor);
  next = clamp(next, Math.min(MIN_BARS, n), n);
  if (next >= n) return null;
  const anchor = span.start + clamp(anchorFrac, 0, 1) * count;
  let start = Math.round(anchor - clamp(anchorFrac, 0, 1) * next);
  let end = start + next;
  if (start < 0) {
    end -= start;
    start = 0;
  }
  if (end > n) {
    start -= end - n;
    end = n;
  }
  start = clamp(start, 0, Math.max(0, n - next));
  end = start + next;
  if (start <= 0 && end >= n) return null;
  return { start, end };
}

export default function PriceChart({ candles, engine, card, sampleNote }: Props) {
  const stageRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [view, setView] = useState<Span | null>(null);
  const [sel, setSel] = useState<{ x0: number; x1: number; y0: number; y1: number } | null>(null);
  const drag = useRef<{ x0: number; y0: number; pointer: number } | null>(null);
  const viewRef = useRef(view);
  viewRef.current = view;

  const firstT = candles[0]?.t ?? 0;
  useEffect(() => {
    setView(null);
  }, [firstT]);

  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const n = candles.length;
  const span: Span = view && n >= 2
    ? { start: clamp(view.start, 0, n - 2), end: clamp(Math.max(view.end, view.start + 2), 2, n) }
    : { start: 0, end: n };

  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (n < 2) return;
      e.preventDefault();
      const svg = svgRef.current;
      const rect = (svg || el).getBoundingClientRect();
      const w = rect.width || 1;
      const x = e.clientX - rect.left;
      const plotL = (L / Math.max(size.w, 1)) * w;
      const plotR = w - (R / Math.max(size.w, 1)) * w;
      const frac = clamp((x - plotL) / Math.max(1, plotR - plotL), 0, 1);
      const current = viewRef.current && n >= 2
        ? { start: clamp(viewRef.current.start, 0, n - 2), end: clamp(viewRef.current.end, 2, n) }
        : { start: 0, end: n };
      const factor = e.deltaY < 0 ? 0.8 : 1.25;
      setView(zoomSpan(n, current, factor, frac));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [n, size.w]);

  const w = Math.max(0, size.w);
  const h = Math.max(0, size.h);
  const ready = n >= 2 && w > 80 && h > 60;

  const localPoint = (ev: { clientX: number; clientY: number }) => {
    const svg = svgRef.current;
    const rect = svg?.getBoundingClientRect();
    if (!svg || !rect || !rect.width || !rect.height) return { x: 0, y: 0 };
    const vb = svg.viewBox.baseVal;
    return {
      x: ((ev.clientX - rect.left) / rect.width) * (vb.width || w),
      y: ((ev.clientY - rect.top) / rect.height) * (vb.height || h),
    };
  };

  const indexAt = (x: number, current: Span) => {
    const plotW = Math.max(1, w - L - R);
    const frac = clamp((x - L) / plotW, 0, 1);
    const count = current.end - current.start;
    return clamp(Math.round(current.start + frac * (count - 1)), current.start, current.end - 1);
  };

  const onPointerDown = (ev: ReactPointerEvent<SVGSVGElement>) => {
    if (!ready) return;
    if (ev.button !== 0) return;
    const pt = localPoint(ev);
    drag.current = { x0: pt.x, y0: pt.y, pointer: ev.pointerId };
    setSel({ x0: pt.x, x1: pt.x, y0: pt.y, y1: pt.y });
    ev.currentTarget.setPointerCapture(ev.pointerId);
  };

  const onPointerMove = (ev: ReactPointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    const pt = localPoint(ev);
    setSel({ x0: drag.current.x0, x1: pt.x, y0: drag.current.y0, y1: pt.y });
  };

  const onPointerUp = (ev: ReactPointerEvent<SVGSVGElement>) => {
    const origin = drag.current;
    drag.current = null;
    setSel(null);
    if (!origin || !ready) return;
    const pt = localPoint(ev);
    if (Math.abs(pt.x - origin.x0) < 12) return;
    const a = indexAt(Math.min(origin.x0, pt.x), span);
    const b = indexAt(Math.max(origin.x0, pt.x), span);
    const start = Math.min(a, b);
    const end = Math.max(a, b) + 1;
    if (end - start < 2) return;
    if (start <= 0 && end >= n) setView(null);
    else setView({ start, end: Math.min(n, end) });
  };

  const zoomButton = (factor: number) => {
    if (n < 2) return;
    setView(zoomSpan(n, span, factor, 0.5));
  };

  let body: ReactNode = null;
  if (ready) {
    const vis = candles.slice(span.start, span.end);
    const series = engine?.series;
    const aligned = !!series && series.vwap.length === candles.length && series.time.length === candles.length;
    const extra: number[] = [];
    if (aligned && series) {
      extra.push(
        ...series.up2.slice(span.start, span.end),
        ...series.dn2.slice(span.start, span.end),
      );
    }
    const cardIdx = card?.time ? candles.findIndex((c) => c.t === card.time) : -1;
    const cardVisible = card && cardIdx >= span.start && cardIdx < span.end;
    if (cardVisible && card) extra.push(card.entry, card.stop, card.tp1, card.tp2);
    const prices = finite([
      ...vis.flatMap((c) => [c.l, c.h]),
      ...extra,
    ]);
    let min = prices.length ? Math.min(...prices) : 0;
    let max = prices.length ? Math.max(...prices) : 1;
    if (max - min < 1e-9) {
      min -= 1;
      max += 1;
    }
    const pad = (max - min) * 0.04;
    min -= pad;
    max += pad;
    const plotW = w - L - R;
    const plotH = h - T - B;
    const count = vis.length;
    const dx = plotW / Math.max(1, count);
    const yOf = (price: number) => T + ((max - price) / (max - min)) * plotH;
    const xOf = (i: number) => L + (i + 0.5) * dx;

    const line = (values: number[], reverse = false) => {
      const seq = values.map((v, i) => ({ i, v }));
      const ordered = reverse ? [...seq].reverse() : seq;
      return ordered
        .map(({ i, v }) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`)
        .join(' ');
    };

    const yTicks = [max, max - (max - min) * 0.33, max - (max - min) * 0.66, min];
    const xSlots = Math.max(2, Math.floor(plotW / 92));
    const xStep = Math.max(1, Math.floor((count - 1) / (xSlots - 1)));
    const xIdx: number[] = [];
    for (let i = 0; i < count; i += xStep) xIdx.push(i);
    if (xIdx[xIdx.length - 1] !== count - 1) xIdx.push(count - 1);

    const hLine = (price: number, color: string, label: string, dash?: string) => {
      const y = yOf(price);
      const x1 = cardVisible ? xOf(cardIdx - span.start) : L;
      return (
        <g key={label}>
          <line x1={x1} x2={w - R} y1={y} y2={y} stroke={color} strokeWidth={1} strokeDasharray={dash} />
          <text x={L + 4} y={y - 3} fill={color} fontSize={11} fontFamily="JetBrains Mono, monospace">
            {label} {px(price)}
          </text>
        </g>
      );
    };

    const selBox = sel && Math.abs(sel.x1 - sel.x0) > 2
      ? {
          x: Math.min(sel.x0, sel.x1),
          y: T,
          width: Math.abs(sel.x1 - sel.x0),
          height: plotH,
        }
      : null;

    body = (
      <svg
        ref={svgRef}
        className="price-chart"
        width={w}
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <rect x={0} y={0} width={L} height={h} fill="var(--surface)" />
        <rect x={0} y={h - B} width={w} height={B} fill="var(--surface)" />
        {yTicks.map((p, i) => (
          <g key={`y${i}`}>
            <line x1={L} x2={w - R} y1={yOf(p)} y2={yOf(p)} stroke="var(--chart-grid)" strokeWidth={1} />
            <text x={8} y={Math.min(yOf(p) + 4, h - B - 4)} fill="var(--chart-ink)" fontSize={11} fontFamily="JetBrains Mono, monospace">
              {px(p)}
            </text>
          </g>
        ))}
        {aligned && series && (
          <polygon
            points={`${line(series.up2.slice(span.start, span.end))} ${line(series.dn2.slice(span.start, span.end), true)}`}
            fill="rgba(16,185,129,0.06)"
            stroke="none"
          />
        )}
        {vis.map((c, i) => {
          const x = xOf(i);
          const up = c.c >= c.o;
          const color = up ? 'rgb(34 197 94)' : 'rgb(239 68 68)';
          const yH = yOf(c.h);
          const yL = yOf(c.l);
          const yO = yOf(c.o);
          const yC = yOf(c.c);
          const top = Math.min(yO, yC);
          const bh = Math.max(1, Math.abs(yC - yO));
          return (
            <g key={c.t}>
              <line x1={x} x2={x} y1={yH} y2={yL} stroke={color} strokeWidth={1} />
              <rect x={x - Math.max(1, dx * 0.28)} y={top} width={Math.max(1.5, dx * 0.56)} height={bh} fill={color} />
            </g>
          );
        })}
        {aligned && series && (
          <>
            <polyline fill="none" stroke="rgb(239 68 68)" strokeOpacity={0.45} strokeWidth={1} points={line(series.up2.slice(span.start, span.end))} />
            <polyline fill="none" stroke="rgb(34 197 94)" strokeOpacity={0.55} strokeWidth={1} points={line(series.up1.slice(span.start, span.end))} />
            <polyline fill="none" stroke="var(--chart-vwap)" strokeWidth={1.4} points={line(series.vwap.slice(span.start, span.end))} />
            <polyline fill="none" stroke="rgb(34 197 94)" strokeOpacity={0.55} strokeWidth={1} points={line(series.dn1.slice(span.start, span.end))} />
            <polyline fill="none" stroke="rgb(239 68 68)" strokeOpacity={0.45} strokeWidth={1} points={line(series.dn2.slice(span.start, span.end))} />
          </>
        )}
        {cardVisible && card && (
          <>
            {hLine(card.entry, 'rgb(251 191 36)', 'ENTRY')}
            {hLine(card.stop, 'rgb(239 68 68)', 'STOP', '4 3')}
            {hLine(card.tp1, 'rgb(34 197 94)', 'TP1', '4 3')}
            {hLine(card.tp2, 'rgb(6 182 212)', 'TP2', '2 3')}
          </>
        )}
        {xIdx.map((i) => {
          const x = xOf(i);
          const anchor = i === 0 ? 'start' : i === count - 1 ? 'end' : 'middle';
          const tx = i === 0 ? L : i === count - 1 ? w - R : x;
          return (
            <text
              key={`x${vis[i].t}`}
              x={tx}
              y={h - 8}
              textAnchor={anchor}
              fill="var(--chart-ink)"
              fontSize={11}
              fontFamily="JetBrains Mono, monospace"
            >
              {fmtEtAxis(vis[i].t)}
            </text>
          );
        })}
        {selBox && (
          <rect
            x={selBox.x}
            y={selBox.y}
            width={selBox.width}
            height={selBox.height}
            fill="rgba(14,116,144,0.16)"
            stroke="var(--cyan)"
            strokeWidth={1}
          />
        )}
      </svg>
    );
  }

  return (
    <div className="chart-stage" ref={stageRef}>
      {!ready && (
        <div className="pos-empty">{n < 2 ? (sampleNote || 'No equity bars.') : ' '}</div>
      )}
      {body}
      {n >= 2 && (
        <div className="chart-tools">
          <button type="button" className="mini" title="Zoom in" onClick={() => zoomButton(0.7)}>+</button>
          <button type="button" className="mini" title="Zoom out" onClick={() => zoomButton(1.4)}>−</button>
          <button type="button" className="mini" title="Fit all bars" onClick={() => setView(null)}>Fit</button>
        </div>
      )}
    </div>
  );
}
