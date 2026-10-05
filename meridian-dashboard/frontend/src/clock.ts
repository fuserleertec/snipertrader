/** America/New_York clock. Equity session, not the CME Globex window. */
export type Phase = 'open' | 'pre' | 'after' | 'closed';

export function nyParts(now = new Date()): { wd: number; mins: number; label: string } {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
  const parts = fmt.formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value || '';
  const wdName = get('weekday');
  const wd = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 }[wdName] ?? 0;
  let hour = Number(get('hour'));
  if (hour === 24) hour = 0;
  const mins = hour * 60 + Number(get('minute'));
  const label = `${wdName} ${String(hour).padStart(2, '0')}:${get('minute')}:${get('second')} ET`;
  return { wd, mins, label };
}

/** Regular session 09:30–16:00 ET. Premarket and after-hours are labeled, not armed. */
export function equityPhase(now = new Date()): Phase {
  const { wd, mins } = nyParts(now);
  if (wd >= 5) return 'closed';
  if (mins >= 4 * 60 && mins < 9 * 60 + 30) return 'pre';
  if (mins >= 9 * 60 + 30 && mins < 16 * 60) return 'open';
  if (mins >= 16 * 60 && mins < 20 * 60) return 'after';
  return 'closed';
}

export function fmtEt(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return '—';
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(ms);
  } catch {
    return '—';
  }
}

/** Compact America/New_York stamp for the chart time axis. */
export function fmtEtAxis(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return '—';
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(ms);
  } catch {
    return '—';
  }
}

export function px(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
