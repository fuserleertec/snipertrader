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
import type { PatternDrawModel } from "@/lib/draw";
export type { PatternDrawModel } from "@/lib/draw";

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
        const label =
          z.kind === "fvg"
            ? "FVG"
            : z.kind === "ob"
              ? "OB"
              : z.kind === "pullback"
                ? "PULLBACK"
                : z.kind === "confluence"
                  ? "CONF"
                  : z.kind === "kill_zone"
                    ? "KZ"
                    : "ASIA";
        ctx.fillText(z.highlight ? `${label} ★` : label, left + 4, Math.max(top + 12, 12));
      }
      for (const line of this.model.lines) {
        const x1 = ts.timeToCoordinate(Math.floor(line.start_ms / 1000) as UTCTimestamp);
        const y1 = series.priceToCoordinate(line.price);
        if (y1 == null) continue;
        ctx.strokeStyle = line.color;
        ctx.lineWidth = line.highlight ? 2 : 1;
        ctx.setLineDash(line.end_price != null ? [] : [5, 4]);
        ctx.beginPath();
        if (line.end_ms != null && line.end_price != null) {
          const x2 = ts.timeToCoordinate(Math.floor(line.end_ms / 1000) as UTCTimestamp);
          const y2 = series.priceToCoordinate(line.end_price);
          if (x1 == null || x2 == null || y2 == null) continue;
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
        } else {
          ctx.moveTo(x1 ?? 0, y1);
          ctx.lineTo(mediaSize.width, y1);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = line.color;
        ctx.font = `${line.highlight ? 11 : 10}px monospace`;
        const tag = line.label ?? "MSS";
        ctx.fillText(line.highlight ? `${tag} ★` : tag, (x1 ?? 8) + 8, y1 - 6);
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
        ctx.font = `${arrow.highlight || arrow.confirmed ? 11 : 10}px monospace`;
        const bits = ["SWEEP"];
        if (arrow.confirmed) bits.push("✓");
        if (arrow.delta) bits.push("Δ");
        if (arrow.highlight) bits.push("★");
        ctx.fillText(bits.join(" "), x + 10, y + 4);
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
