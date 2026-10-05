import type { Bar, LinePoint, Timeframe } from '../types';
import { nyParts } from './ny';

export interface StudyLast {
  close: number;
  vwap: number | null;
  ema9: number | null;
  ema21: number | null;
  ema50: number | null;
}

export interface Study {
  vwap: LinePoint[];
  band1u: LinePoint[];
  band1d: LinePoint[];
  band2u: LinePoint[];
  band2d: LinePoint[];
  ema9: LinePoint[];
  ema21: LinePoint[];
  ema50: LinePoint[];
  last: StudyLast | null;
}

export type StackLabel = 'LONG STACK' | 'SHORT STACK' | 'MIXED';

function emaSeries(bars: Bar[], period: number): LinePoint[] {
  if (!bars.length) return [];
  const k = 2 / (period + 1);
  let prev = bars[0].close;
  const out: LinePoint[] = [{ time: bars[0].time, value: prev }];
  for (let i = 1; i < bars.length; i++) {
    prev = bars[i].close * k + prev * (1 - k);
    out.push({ time: bars[i].time, value: prev });
  }
  return out;
}

export function study(bars: Bar[], timeframe: Timeframe): Study {
  const resetDaily = timeframe !== '1d';
  let cumPV = 0;
  let cumV = 0;
  let cumP2 = 0;
  let day = '';
  const vwap: LinePoint[] = [];
  const band1u: LinePoint[] = [];
  const band1d: LinePoint[] = [];
  const band2u: LinePoint[] = [];
  const band2d: LinePoint[] = [];

  for (const bar of bars) {
    const key = nyParts(bar.time * 1000).ymd;
    if (resetDaily && key !== day) {
      day = key;
      cumPV = 0;
      cumV = 0;
      cumP2 = 0;
    }
    const typical = (bar.high + bar.low + bar.close) / 3;
    const weight = bar.volume > 0 ? bar.volume : 1;
    cumPV += typical * weight;
    cumV += weight;
    cumP2 += typical * typical * weight;
    const mean = cumPV / cumV;
    const variance = Math.max(0, cumP2 / cumV - mean * mean);
    const sd = Math.sqrt(variance);
    vwap.push({ time: bar.time, value: mean });
    band1u.push({ time: bar.time, value: mean + sd });
    band1d.push({ time: bar.time, value: mean - sd });
    band2u.push({ time: bar.time, value: mean + 2 * sd });
    band2d.push({ time: bar.time, value: mean - 2 * sd });
  }

  const ema9 = emaSeries(bars, 9);
  const ema21 = emaSeries(bars, 21);
  const ema50 = emaSeries(bars, 50);
  const lastBar = bars[bars.length - 1];
  const last: StudyLast | null = lastBar
    ? {
        close: lastBar.close,
        vwap: vwap.length ? vwap[vwap.length - 1].value : null,
        ema9: ema9.length ? ema9[ema9.length - 1].value : null,
        ema21: ema21.length ? ema21[ema21.length - 1].value : null,
        ema50: ema50.length ? ema50[ema50.length - 1].value : null,
      }
    : null;

  return { vwap, band1u, band1d, band2u, band2d, ema9, ema21, ema50, last };
}

export function stackLabel(last: StudyLast | null): StackLabel {
  if (!last || last.vwap == null || last.ema9 == null || last.ema21 == null || last.ema50 == null) {
    return 'MIXED';
  }
  if (last.ema9 > last.ema21 && last.ema21 > last.ema50 && last.close > last.vwap) return 'LONG STACK';
  if (last.ema9 < last.ema21 && last.ema21 < last.ema50 && last.close < last.vwap) return 'SHORT STACK';
  return 'MIXED';
}
