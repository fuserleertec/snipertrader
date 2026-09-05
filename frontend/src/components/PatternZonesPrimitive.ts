import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IChartApi,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitivePaneRenderer,
  ISeriesPrimitivePaneView,
  SeriesAttachedParameter,
  SeriesType,
  Time,
  UTCTimestamp,
} from "lightweight-charts";
import type { FVGZone, MssEvent, OrderBlock, OverlayPreset, SessionLevels, SweepEvent } from "@/lib/types";

export interface ZoneDraw {
  id: string;
  kind: "fvg" | "ob" | "asia";
  start_ms: number;
  end_ms: number | null;
  high: number;
  low: number;
  fill: string;
  stroke: string;
  highlight: boolean;
}

interface LineDraw {
  id: string;
  start_ms: number;
  price: number;
  color: string;
  highlight: boolean;
}

interface ArrowDraw {
  id: string;
  ts_ms: number;
  price: number;
  side: "buy" | "sell";
  color: string;
  highlight: boolean;
}

export interface PatternDrawModel {
  zones: ZoneDraw[];
  lines: LineDraw[];
  arrows: ArrowDraw[];
}

function fvgFill(z: FVGZone, highlight: boolean): { fill: string; stroke: string } {
  const dim = !!z.mitigated;
  if (z.direction === "bullish") {
    return {
      fill: highlight ? "rgba(0,229,160,0.38)" : dim ? "rgba(0,229,160,0.08)" : "rgba(0,229,160,0.22)",
      stroke: highlight ? "#F0C040" : dim ? "rgba(0,229,160,0.25)" : "rgba(0,229,160,0.7)",
    };
  }
  return {
    fill: highlight ? "rgba(255,68,85,0.36)" : dim ? "rgba(255,68,85,0.08)" : "rgba(255,68,85,0.22)",
    stroke: highlight ? "#F0C040" : dim ? "rgba(255,68,85,0.25)" : "rgba(255,68,85,0.7)",
  };
}

export function buildDrawModel(
  preset: OverlayPreset,
  fvgs: FVGZone[],
  obs: OrderBlock[],
  mss: MssEvent[],
  sweeps: SweepEvent[],
  highlightIds: Set<string>,
  asia: SessionLevels | null,
): PatternDrawModel {
  const showFvg = preset === "all" || preset === "fvg_ob";
  const showOb = preset === "all" || preset === "fvg_ob";
  const showMss = preset === "all" || preset === "sweep_reclaim" || preset === "po3_judas";
  const showSweep = preset === "all" || preset === "sweep_reclaim" || preset === "po3_judas";
  const showAsia = preset === "all" || preset === "po3_judas";

  const zones: ZoneDraw[] = [];
  if (showFvg) {
    for (const z of fvgs) {
      const colors = fvgFill(z, highlightIds.has(z.id));
      zones.push({
        id: z.id,
        kind: "fvg",
        start_ms: z.created_ts_ms,
        end_ms: null,
        high: z.high,
        low: z.low,
        fill: colors.fill,
        stroke: colors.stroke,
        highlight: highlightIds.has(z.id),
      });
    }
  }
  if (showOb) {
    for (const z of obs) {
      const hi = highlightIds.has(z.id);
      zones.push({
        id: z.id,
        kind: "ob",
        start_ms: z.created_ts_ms,
        // Displacement timestamps the impulse, not zone expiry — extend forward like FVGs.
        end_ms: null,
        high: z.high,
        low: z.low,
        fill: hi ? "rgba(168,85,247,0.48)" : z.mitigated ? "rgba(168,85,247,0.10)" : "rgba(168,85,247,0.32)",
        stroke: hi ? "#F0C040" : "#C084FC",
        highlight: hi,
      });
    }
  }
  if (showAsia && asia) {
    zones.push({
      id: `asia_${asia.session_start_ms}`,
      kind: "asia",
      start_ms: asia.session_start_ms,
      end_ms: asia.session_end_ms,
      high: asia.high,
      low: asia.low,
      fill: "rgba(0,212,255,0.10)",
      stroke: "rgba(0,212,255,0.55)",
      highlight: false,
    });
  }

  const lines: LineDraw[] = [];
  if (showMss) {
    for (const ev of mss) {
      lines.push({
        id: ev.id,
        start_ms: ev.ts_ms,
        price: ev.broken_level,
        color: highlightIds.has(ev.id) ? "#F0C040" : ev.direction === "bullish" ? "#00D4FF" : "#FF8A3D",
        highlight: highlightIds.has(ev.id),
      });
    }
  }
  const arrows: ArrowDraw[] = [];
  if (showSweep) {
    for (const sw of sweeps) {
      arrows.push({
        id: sw.id,
        ts_ms: sw.ts_ms,
        price: sw.swept_level,
        side: sw.side,
        color: highlightIds.has(sw.id) ? "#F0C040" : sw.side === "sell" ? "#FF4455" : "#00E5A0",
        highlight: highlightIds.has(sw.id),
      });
    }
  }
  return { zones, lines, arrows };
}

class ZonesRenderer implements ISeriesPrimitivePaneRenderer {
  constructor(
    private readonly chart: IChartApi | null,
    private readonly series: ISeriesApi<SeriesType> | null,
    private readonly model: PatternDrawModel,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const ts = chart.timeScale();
      for (const z of this.model.zones) {
        const x1 = ts.timeToCoordinate(Math.floor(z.start_ms / 1000) as UTCTimestamp);
        const x2 =
          z.end_ms != null
            ? ts.timeToCoordinate(Math.floor(z.end_ms / 1000) as UTCTimestamp)
            : mediaSize.width;
        const y1 = series.priceToCoordinate(z.high);
        const y2 = series.priceToCoordinate(z.low);
        if (x1 == null || y1 == null || y2 == null) continue;
        const left = Math.min(x1, x2 ?? mediaSize.width);
        const right = x2 == null ? mediaSize.width : Math.max(x1, x2);
        const top = Math.min(y1, y2);
        const h = Math.abs(y2 - y1);
        ctx.fillStyle = z.fill;
        ctx.fillRect(left, top, Math.max(right - left, 4), Math.max(h, 3));
        ctx.strokeStyle = z.stroke;
        ctx.lineWidth = z.highlight ? 2.5 : 1;
        ctx.strokeRect(left, top, Math.max(right - left, 4), Math.max(h, 3));
        ctx.fillStyle = z.stroke;
        ctx.font = `${z.highlight ? 11 : 10}px monospace`;
        const label = z.kind === "fvg" ? "FVG" : z.kind === "ob" ? "OB" : "ASIA";
        ctx.fillText(z.highlight ? `${label} ★` : label, left + 4, Math.max(top + 12, 12));
      }
      for (const line of this.model.lines) {
        const x = ts.timeToCoordinate(Math.floor(line.start_ms / 1000) as UTCTimestamp);
        const y = series.priceToCoordinate(line.price);
        if (y == null) continue;
        ctx.strokeStyle = line.color;
        ctx.lineWidth = line.highlight ? 2 : 1;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(x ?? 0, y);
        ctx.lineTo(mediaSize.width, y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = line.color;
        ctx.font = `${line.highlight ? 11 : 10}px monospace`;
        ctx.fillText(line.highlight ? "MSS ★" : "MSS", (x ?? 8) + 8, y - 6);
      }
    });
  }
}

class ArrowsRenderer implements ISeriesPrimitivePaneRenderer {
  constructor(
    private readonly chart: IChartApi | null,
    private readonly series: ISeriesApi<SeriesType> | null,
    private readonly model: PatternDrawModel,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series) return;
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const ts = chart.timeScale();
      for (const arrow of this.model.arrows) {
        const x = ts.timeToCoordinate(Math.floor(arrow.ts_ms / 1000) as UTCTimestamp);
        const y = series.priceToCoordinate(arrow.price);
        if (x == null || y == null) continue;
        const dir = arrow.side === "sell" ? 1 : -1;
        ctx.fillStyle = arrow.color;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x - 8, y + dir * 18);
        ctx.lineTo(x + 8, y + dir * 18);
        ctx.closePath();
        ctx.fill();
        ctx.font = `${arrow.highlight ? 11 : 10}px monospace`;
        ctx.fillText(arrow.highlight ? "SWEEP ★" : "SWEEP", x + 10, y + 4);
      }
    });
  }
}

class ZonesPaneView implements ISeriesPrimitivePaneView {
  model: PatternDrawModel = { zones: [], lines: [], arrows: [] };
  chart: IChartApi | null = null;
  series: ISeriesApi<SeriesType> | null = null;

  zOrder(): "bottom" {
    return "bottom";
  }

  renderer(): ISeriesPrimitivePaneRenderer {
    return new ZonesRenderer(this.chart, this.series, this.model);
  }
}

class ArrowsPaneView implements ISeriesPrimitivePaneView {
  model: PatternDrawModel = { zones: [], lines: [], arrows: [] };
  chart: IChartApi | null = null;
  series: ISeriesApi<SeriesType> | null = null;

  zOrder(): "top" {
    return "top";
  }

  renderer(): ISeriesPrimitivePaneRenderer {
    return new ArrowsRenderer(this.chart, this.series, this.model);
  }
}

export class PatternZonesPrimitive implements ISeriesPrimitive<Time> {
  private requestUpdate: (() => void) | null = null;
  private readonly zonesView = new ZonesPaneView();
  private readonly arrowsView = new ArrowsPaneView();
  private readonly views = [this.zonesView, this.arrowsView];

  attached(param: SeriesAttachedParameter<Time>): void {
    this.zonesView.chart = param.chart as IChartApi;
    this.zonesView.series = param.series;
    this.arrowsView.chart = param.chart as IChartApi;
    this.arrowsView.series = param.series;
    this.requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this.zonesView.chart = null;
    this.zonesView.series = null;
    this.arrowsView.chart = null;
    this.arrowsView.series = null;
    this.requestUpdate = null;
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return this.views;
  }

  updateAllViews(): void {
    /* coordinates resolved in renderer */
  }

  setModel(model: PatternDrawModel): void {
    this.zonesView.model = model;
    this.arrowsView.model = model;
    this.requestUpdate?.();
  }
}
