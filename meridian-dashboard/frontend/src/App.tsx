import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchAlpacaBars, fetchCatalyst, fetchScan, fetchYahooChart, fetchYahooNews, overlayBars } from './api';
import { Header } from './components/Header';
import { NewsPanel } from './components/NewsPanel';
import { PriceChart } from './components/PriceChart';
import { ScanPanel } from './components/ScanPanel';
import { TapePanel } from './components/TapePanel';
import { stackLabel, study } from './lib/ta';
import type { Bar, DeskQuote, Feed, NewsItem, ScanRow, ThemeName, Timeframe } from './types';
import { futuresNotation, normalizeSymbol } from './universe';

const EMPTY_STUDY = study([], '15m');

export default function App() {
  const [theme, setTheme] = useState<ThemeName>(() =>
    document.documentElement.classList.contains('light') ? 'light' : 'dark',
  );
  const [symbol, setSymbol] = useState('SPY');
  const [draft, setDraft] = useState('SPY');
  const [timeframe, setTimeframe] = useState<Timeframe>('15m');
  const [extended, setExtended] = useState(false);
  const [bars, setBars] = useState<Bar[]>([]);
  const [quote, setQuote] = useState<DeskQuote | null>(null);
  const [scan, setScan] = useState<ScanRow[]>([]);
  const [scanError, setScanError] = useState<string | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sentiment, setSentiment] = useState<string | null>(null);
  const [newsLoading, setNewsLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feed, setFeed] = useState<Feed>('offline');

  const toggleTheme = useCallback(() => {
    const next: ThemeName = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    document.documentElement.classList.toggle('light', next === 'light');
    localStorage.setItem('meridian-stocks-theme', next);
  }, [theme]);

  const selectSymbol = useCallback((next: string) => {
    const symbolNext = normalizeSymbol(next);
    if (!symbolNext) return;
    setDraft(symbolNext);
    if (futuresNotation(symbolNext)) {
      setError('Equities and ETFs only. Futures contracts stay on the futures desk.');
      return;
    }
    setError(null);
    setSymbol(symbolNext);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async (quiet: boolean) => {
      if (!quiet) {
        setChartLoading(true);
        setError(null);
      }
      try {
        const yahoo = await fetchYahooChart(symbol, timeframe, extended);
        if (cancelled) return;
        setBars(yahoo.bars);
        setQuote(yahoo.quote);
        setFeed('yahoo');
        setChartLoading(false);
        const alpaca = await fetchAlpacaBars(symbol, timeframe, extended);
        if (cancelled || !alpaca) return;
        setBars(alpaca);
        setQuote(overlayBars(yahoo.quote, alpaca));
        setFeed('alpaca');
      } catch (err) {
        if (cancelled) return;
        setBars([]);
        setQuote(null);
        setFeed('offline');
        setChartLoading(false);
        setError(err instanceof Error ? err.message : 'Chart unavailable');
      }
    };
    void load(false);
    const id = window.setInterval(() => void load(true), 30000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [symbol, timeframe, extended]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setNewsLoading(true);
      setSentiment(null);
      try {
        const items = await fetchYahooNews(symbol);
        if (cancelled) return;
        setNews(items);
        setNewsLoading(false);
      } catch {
        if (cancelled) return;
        setNews([]);
        setNewsLoading(false);
      }
      const catalyst = await fetchCatalyst(symbol);
      if (cancelled || !catalyst) return;
      setNews(catalyst.items);
      setSentiment(catalyst.sentiment);
    };
    void load();
    const id = window.setInterval(() => void load(), 120000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [symbol]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const rows = await fetchScan(symbol);
        if (cancelled) return;
        setScan(rows);
        setScanError(null);
      } catch (err) {
        if (cancelled) return;
        setScanError(err instanceof Error ? err.message : 'Scan unavailable');
      }
    };
    void load();
    const id = window.setInterval(() => void load(), 20000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [symbol]);

  useEffect(() => {
    if (!quote) return;
    setScan((rows) =>
      rows.map((row) =>
        row.symbol === quote.symbol ? { ...row, last: quote.last, changePct: quote.changePct } : row,
      ),
    );
  }, [quote]);

  const chartStudy = useMemo(() => (bars.length ? study(bars, timeframe) : EMPTY_STUDY), [bars, timeframe]);

  return (
    <div className="desk">
      <Header
        draft={draft}
        onDraft={setDraft}
        onSubmitSymbol={() => selectSymbol(draft)}
        timeframe={timeframe}
        onTimeframe={setTimeframe}
        extended={extended}
        onExtended={() => setExtended((value) => !value)}
        theme={theme}
        onTheme={toggleTheme}
        feed={feed}
      />
      {error ? (
        <div className="errbar" role="alert">
          {error}
        </div>
      ) : null}
      <main className="desk-grid">
        <PriceChart
          bars={bars}
          study={chartStudy}
          quote={quote}
          timeframe={timeframe}
          theme={theme}
          feed={feed}
          loading={chartLoading}
        />
        <NewsPanel symbol={symbol} items={news} sentiment={sentiment} loading={newsLoading} />
        <aside className="rail">
          <ScanPanel rows={scan} active={symbol} onPick={selectSymbol} error={scanError} />
          <TapePanel quote={quote} last={chartStudy.last} stack={stackLabel(chartStudy.last)} timeframe={timeframe} />
        </aside>
      </main>
    </div>
  );
}
