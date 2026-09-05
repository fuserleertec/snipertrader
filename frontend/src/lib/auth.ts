export interface AuthUser {
  email: string;
  token: string;
  watchlist: string[];
}

const KEY = "st-auth";

export function readAuth(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function mockLogin(email: string): AuthUser {
  const user: AuthUser = {
    email,
    token: `mock.${btoa(email)}.${Date.now()}`,
    watchlist: ["BTCUSDT", "ES", "NVDA"],
  };
  window.localStorage.setItem(KEY, JSON.stringify(user));
  return user;
}

export function mockLogout(): void {
  window.localStorage.removeItem(KEY);
}

export function saveWatchlist(symbols: string[]): AuthUser | null {
  const user = readAuth();
  if (!user) return null;
  const next = { ...user, watchlist: symbols };
  window.localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}
