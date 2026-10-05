export type ThemeName = 'blue' | 'night';
export type AlertGrade = 'WATCH' | 'PRIME' | 'ELITE' | 'SINGULAR';
export type AlertSide = 'BOTH' | 'LONG' | 'SHORT';
export type AlertRegime = 'ANY' | 'TREND' | 'RANGE' | 'TRANS';

export interface AlertPrefs {
  enabled: boolean;
  minGrade: AlertGrade;
  side: AlertSide;
  regime: AlertRegime;
  sound: boolean;
  notify: boolean;
}

export const THEME_KEY = 'meridian-equities-theme';
export const ALERT_KEY = 'meridian-equities-alerts';

export const DEFAULT_ALERTS: AlertPrefs = {
  enabled: true,
  minGrade: 'PRIME',
  side: 'BOTH',
  regime: 'ANY',
  sound: false,
  notify: false,
};

export function readTheme(): ThemeName {
  return localStorage.getItem(THEME_KEY) === 'night' ? 'night' : 'blue';
}

export function applyTheme(theme: ThemeName) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
}

export function readAlerts(): AlertPrefs {
  try {
    const raw = localStorage.getItem(ALERT_KEY);
    if (!raw) return DEFAULT_ALERTS;
    const parsed = JSON.parse(raw) as Partial<AlertPrefs>;
    return { ...DEFAULT_ALERTS, ...parsed };
  } catch {
    return DEFAULT_ALERTS;
  }
}

export function writeAlerts(prefs: AlertPrefs) {
  localStorage.setItem(ALERT_KEY, JSON.stringify(prefs));
}

export const NEWS_H_KEY = 'meridian-equities-news-h';
/** Tall enough for the header, five wrapped headline rows, and the drag handle. */
export const NEWS_H_DEFAULT = 400;
const NEWS_H_FLOOR = 380;

export function clampNewsHeight(h: number, viewport?: number): number {
  const vh = viewport ?? (typeof window === 'undefined' ? 900 : window.innerHeight);
  const max = Math.min(Math.round(vh * 0.7), Math.max(200, vh - 110));
  const floor = Math.min(NEWS_H_FLOOR, Math.max(200, max));
  const cap = Math.max(floor, max);
  if (!Number.isFinite(h)) return Math.min(NEWS_H_DEFAULT, cap);
  return Math.min(cap, Math.max(floor, Math.round(h)));
}

export function readNewsHeight(): number {
  try {
    const raw = Number(localStorage.getItem(NEWS_H_KEY));
    return clampNewsHeight(Number.isFinite(raw) && raw > 0 ? raw : NEWS_H_DEFAULT);
  } catch {
    return NEWS_H_DEFAULT;
  }
}

export function writeNewsHeight(h: number) {
  try {
    localStorage.setItem(NEWS_H_KEY, String(clampNewsHeight(h)));
  } catch {
    /* private mode */
  }
}
