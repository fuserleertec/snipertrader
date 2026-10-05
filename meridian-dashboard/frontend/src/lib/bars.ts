import type { Bar, Timeframe } from '../types';
import { nyParts } from './ny';

export function dedupeBars(bars: Bar[]): Bar[] {
  const map = new Map<number, Bar>();
  for (const bar of bars) {
    if (!Number.isFinite(bar.time)) continue;
    map.set(bar.time, bar);
  }
  return [...map.values()].sort((a, b) => a.time - b.time);
}

export function aggregate4h(bars: Bar[]): Bar[] {
  const groups = new Map<string, Bar>();
  for (const bar of bars) {
    const ny = nyParts(bar.time * 1000);
    const bucket = Math.floor(ny.hour / 4) * 4;
    const key = `${ny.ymd}-${bucket}`;
    const prev = groups.get(key);
    if (!prev) {
      groups.set(key, { ...bar });
      continue;
    }
    prev.high = Math.max(prev.high, bar.high);
    prev.low = Math.min(prev.low, bar.low);
    prev.close = bar.close;
    prev.volume += bar.volume;
  }
  return [...groups.values()].sort((a, b) => a.time - b.time);
}

export type SessionFilter = 'rth' | 'ext' | 'all';

export function filterSession(bars: Bar[], mode: SessionFilter): Bar[] {
  if (mode === 'all') return bars;
  return bars.filter((bar) => {
    const ny = nyParts(bar.time * 1000);
    if (ny.weekend) return false;
    if (mode === 'rth') return ny.minutes >= 9 * 60 + 30 && ny.minutes <= 16 * 60;
    return ny.minutes >= 4 * 60 && ny.minutes <= 20 * 60;
  });
}

export function shapeBars(bars: Bar[], timeframe: Timeframe, extended: boolean): Bar[] {
  let next = dedupeBars(bars);
  if (timeframe === '4h') next = aggregate4h(next);
  if (timeframe !== '1d') next = filterSession(next, extended ? 'ext' : 'rth');
  return next;
}
