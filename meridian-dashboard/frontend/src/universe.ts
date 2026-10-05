export interface UniverseName {
  symbol: string;
  name: string;
}

/** Liquid US ETFs and mega-caps. Typed symbols outside this list still chart. */
export const UNIVERSE: UniverseName[] = [
  { symbol: 'SPY', name: 'S&P 500' },
  { symbol: 'QQQ', name: 'Nasdaq 100' },
  { symbol: 'IWM', name: 'Russell 2000' },
  { symbol: 'DIA', name: 'Dow' },
  { symbol: 'SMH', name: 'Semis' },
  { symbol: 'XLF', name: 'Financials' },
  { symbol: 'XLE', name: 'Energy' },
  { symbol: 'TLT', name: '20Y Treasury' },
  { symbol: 'GLD', name: 'Gold' },
  { symbol: 'IBIT', name: 'Bitcoin ETF' },
  { symbol: 'AAPL', name: 'Apple' },
  { symbol: 'MSFT', name: 'Microsoft' },
  { symbol: 'NVDA', name: 'NVIDIA' },
  { symbol: 'AMZN', name: 'Amazon' },
  { symbol: 'META', name: 'Meta' },
  { symbol: 'GOOGL', name: 'Alphabet' },
  { symbol: 'TSLA', name: 'Tesla' },
  { symbol: 'AMD', name: 'AMD' },
  { symbol: 'AVGO', name: 'Broadcom' },
  { symbol: 'JPM', name: 'JPMorgan' },
];

export function universeName(symbol: string): string {
  return UNIVERSE.find((row) => row.symbol === symbol)?.name ?? symbol;
}

/** Continuous futures notation stays on the futures desk. ES the stock is allowed. */
export function futuresNotation(symbol: string): boolean {
  return symbol.includes('!') || symbol.endsWith('=F') || symbol.startsWith('/');
}

export function normalizeSymbol(raw: string): string {
  return raw.trim().toUpperCase().replace(/\./g, '-').replace(/[^A-Z0-9!=/-]/g, '').slice(0, 12);
}
