export interface NyStamp {
  ymd: string;
  weekday: string;
  hour: number;
  minute: number;
  second: number;
  minutes: number;
  weekend: boolean;
}

export function nyParts(input: Date | number): NyStamp {
  const date = typeof input === 'number' ? new Date(input) : input;
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  let hour = Number(get('hour'));
  if (hour === 24) hour = 0;
  const minute = Number(get('minute'));
  const second = Number(get('second'));
  const weekday = get('weekday');
  return {
    ymd: `${get('year')}-${get('month')}-${get('day')}`,
    weekday,
    hour,
    minute,
    second,
    minutes: hour * 60 + minute + second / 60,
    weekend: weekday === 'Sat' || weekday === 'Sun',
  };
}
