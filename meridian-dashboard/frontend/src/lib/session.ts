import { nyParts } from './ny';

export type SessionName = 'PREMARKET' | 'RTH' | 'AFTER HOURS' | 'CLOSED';

const PRE = 4 * 60;
const RTH = 9 * 60 + 30;
const AH = 16 * 60;
const CLOSE = 20 * 60;

export interface SessionView {
  name: SessionName;
  clock: string;
  cue: string;
}

function pad(n: number): string {
  return n.toString().padStart(2, '0');
}

function fmtLeft(mins: number): string {
  const m = Math.max(0, Math.round(mins));
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h <= 0) return `${r}m`;
  return `${h}h ${pad(r)}m`;
}

export function describeSession(now = new Date()): SessionView {
  const ny = nyParts(now);
  const clock = `${pad(ny.hour)}:${pad(ny.minute)}:${pad(ny.second)} ET`;
  if (ny.weekend) {
    return { name: 'CLOSED', clock, cue: 'Opens Mon 04:00 ET' };
  }
  const m = ny.minutes;
  if (m < PRE) {
    return { name: 'CLOSED', clock, cue: `Premarket in ${fmtLeft(PRE - m)}` };
  }
  if (m < RTH) {
    return { name: 'PREMARKET', clock, cue: `RTH opens in ${fmtLeft(RTH - m)}` };
  }
  if (m < AH) {
    return { name: 'RTH', clock, cue: `RTH closes in ${fmtLeft(AH - m)}` };
  }
  if (m < CLOSE) {
    return { name: 'AFTER HOURS', clock, cue: `Session ends in ${fmtLeft(CLOSE - m)}` };
  }
  if (ny.weekday === 'Fri') {
    return { name: 'CLOSED', clock, cue: 'Opens Mon 04:00 ET' };
  }
  return { name: 'CLOSED', clock, cue: `Premarket in ${fmtLeft(24 * 60 - m + PRE)}` };
}
