import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitivePaneRenderer,
  ISeriesPrimitivePaneView,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";
import type { VWAPValues } from "@/lib/types";

export type BandLevels = Pick<
  VWAPValues,
  "band_m3" | "band_m2" | "band_m1" | "band_p1" | "band_p2" | "band_p3"
>;

interface Ys {
  m3: number;
  m2: number;
  m1: number;
  p1: number;
  p2: number;
  p3: number;
}

class BandsRenderer implements ISeriesPrimitivePaneRenderer {
  constructor(private readonly ys: Ys | null) {}

  draw(target: CanvasRenderingTarget2D): void {
    const ys = this.ys;
    if (!ys) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const w = mediaSize.width;
      const fill = (a: number, b: number, color: string) => {
        ctx.fillStyle = color;
        ctx.fillRect(0, Math.min(a, b), w, Math.abs(b - a));
      };
      // Single canvas pass — not six series.
      fill(ys.p3, ys.p2, "rgba(240,192,64,0.07)");
      fill(ys.m3, ys.m2, "rgba(240,192,64,0.07)");
      fill(ys.p2, ys.p1, "rgba(0,212,255,0.09)");
      fill(ys.m2, ys.m1, "rgba(0,212,255,0.09)");
      fill(ys.p1, ys.m1, "rgba(0,229,160,0.11)");
    });
  }
}

class BandsPaneView implements ISeriesPrimitivePaneView {
  private ys: Ys | null = null;

  zOrder(): "bottom" {
    return "bottom";
  }

  update(series: ISeriesApi<SeriesType> | null, levels: BandLevels | null): void {
    if (!series || !levels) {
      this.ys = null;
      return;
    }
    const y = (price: number) => series.priceToCoordinate(price);
    const m3 = y(levels.band_m3);
    const m2 = y(levels.band_m2);
    const m1 = y(levels.band_m1);
    const p1 = y(levels.band_p1);
    const p2 = y(levels.band_p2);
    const p3 = y(levels.band_p3);
    if ([m3, m2, m1, p1, p2, p3].some((v) => v == null)) {
      this.ys = null;
      return;
    }
    this.ys = { m3: m3!, m2: m2!, m1: m1!, p1: p1!, p2: p2!, p3: p3! };
  }

  renderer(): ISeriesPrimitivePaneRenderer | null {
    return this.ys ? new BandsRenderer(this.ys) : null;
  }
}

export class VwapBandsPrimitive implements ISeriesPrimitive<Time> {
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;
  private levels: BandLevels | null = null;
  private readonly view = new BandsPaneView();
  private readonly views = [this.view];

  attached(param: SeriesAttachedParameter<Time>): void {
    this.series = param.series;
    this.requestUpdate = param.requestUpdate;
    this.view.update(this.series, this.levels);
  }

  detached(): void {
    this.series = null;
    this.requestUpdate = null;
  }

  paneViews(): readonly ISeriesPrimitivePaneView[] {
    return this.views;
  }

  updateAllViews(): void {
    this.view.update(this.series, this.levels);
  }

  setLevels(levels: BandLevels | null): void {
    this.levels = levels;
    this.view.update(this.series, this.levels);
    this.requestUpdate?.();
  }
}
