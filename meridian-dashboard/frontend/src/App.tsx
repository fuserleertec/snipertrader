import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchNews, fetchQuote, fetchScan, fetchStateOrFallback, wsUrl } from './api';
import { equityBroker, uiStateLabel, type BrokerStatus } from './broker';
import { equityPhase, fmtEt, nyParts, px, type Phase } from './clock';
import PriceChart from './components/PriceChart';
import {
  applyTheme,
  clampNewsHeight,
  readAlerts,
  readNewsHeight,
  readTheme,
  writeAlerts,
  writeNewsHeight,
  type AlertGrade,
  type AlertPrefs,
  type AlertRegime,
  type AlertSide,
  type ThemeName,
} from './prefs';
import { candlesOf, type EngineState, type NewsItem, type PathCard, type Position, type Quote, type ScanRow } from './types';
import { MIN_GRADES, TIMEFRAMES } from './types';

const RANK: Record<string, number> = { WATCH: 2, PRIME: 3, ELITE: 4, SINGULAR: 5 };

function presetFor(tf: string): string {
  if (tf === '5m') return 'Scalp';
  if (tf === '1h') return 'Swing';
  return 'Intraday';
}

function cardsOf(state: EngineState | null): PathCard[] {
  return (state?.signals || []).map((trade) => ({
    side: trade.side,
    entry: trade.entry,
    stop: trade.sl,
    tp1: trade.tp1,
    tp2: trade.tp2,
    time: trade.bar_time,
    status: trade.status,
    grade: trade.grade,
    regime: trade.regime,
  }));
}

function matches(card: PathCard, alerts: AlertPrefs): boolean {
  if (!alerts.enabled) return true;
  const rank = RANK[card.grade || ''] ?? 0;
  if (rank < (RANK[alerts.minGrade] ?? 3)) return false;
  if (alerts.side === 'LONG' && card.side !== 'BUY') return false;
  if (alerts.side === 'SHORT' && card.side !== 'SELL') return false;
  if (alerts.regime !== 'ANY') {
    const want = alerts.regime === 'TRANS' ? 'TRANSITION' : alerts.regime;
    if ((card.regime || '') !== want) return false;
  }
  return true;
}

function csvCell(value: string | number | null | undefined): string {
  const s = value === null || value === undefined ? '' : String(value);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function downloadHistory(symbol: string, cards: PathCard[]) {
  const header = ['time', 'symbol', 'side', 'grade', 'status', 'entry', 'stop', 'TP1', 'TP2'];
  const lines = [header.join(',')];
  for (const card of cards) {
    lines.push([
      csvCell(card.time ? fmtEt(card.time) : ''),
      csvCell(symbol),
      csvCell(card.side),
      csvCell(card.grade || ''),
      csvCell(card.status),
      csvCell(card.entry),
      csvCell(card.stop),
      csvCell(card.tp1),
      csvCell(card.tp2),
    ].join(','));
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `meridian-equities-${symbol}-paths.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function beep() {
  const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return;
  const ctx = new Ctx();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = 740;
  osc.type = 'sine';
  gain.gain.value = 0.04;
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + 0.08);
  osc.onended = () => void ctx.close();
}

function phaseLabel(phase: Phase): string {
  if (phase === 'open') return 'RTH';
  if (phase === 'pre') return 'PREMARKET';
  if (phase === 'after') return 'AFTER HOURS';
  return 'CLOSED';
}

export default function App() {
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>('15m');
  const [minGrade, setMinGrade] = useState<(typeof MIN_GRADES)[number]>('PRIME');
  const [symbol, setSymbol] = useState('SPY');
  const [query, setQuery] = useState('');
  const [manualHalt, setManualHalt] = useState(false);
  const [theme, setTheme] = useState<ThemeName>(() => readTheme());
  const [alerts, setAlerts] = useState<AlertPrefs>(() => readAlerts());
  const [rows, setRows] = useState<ScanRow[]>([]);
  const [scanError, setScanError] = useState<string | null>(null);
  const [state, setState] = useState<EngineState | null>(null);
  const [stateError, setStateError] = useState<string | null>(null);
  const [cardKey, setCardKey] = useState<number | null>(null);
  const [tab, setTab] = useState<'chart' | 'lattice' | 'pools' | 'blotter'>('chart');
  const [clock, setClock] = useState(() => nyParts().label);
  const [localPhase, setLocalPhase] = useState<Phase>(() => equityPhase());
  const [toast, setToast] = useState<string | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [newsSource, setNewsSource] = useState('Yahoo Finance');
  const [newsH, setNewsH] = useState(() => readNewsHeight());
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [broker, setBroker] = useState<BrokerStatus | null>(null);
  const [brokerBusy, setBrokerBusy] = useState(false);
  const [brokerMsg, setBrokerMsg] = useState<string | null>(null);
  const [tradingArmed, setTradingArmed] = useState(false);
  const [positions, setPositions] = useState<Position[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const alertsRef = useRef<HTMLDivElement>(null);
  const seen = useRef<Set<string>>(new Set());
  const primedSym = useRef<string | null>(null);
  const symbolRef = useRef(symbol);
  symbolRef.current = symbol;

  useEffect(() => { applyTheme(theme); }, [theme]);
  useEffect(() => { writeAlerts(alerts); }, [alerts]);
  useEffect(() => { writeNewsHeight(newsH); }, [newsH]);

  useEffect(() => {
    equityBroker.status().then(setBroker).catch((e: Error) => setBrokerMsg(e.message));
  }, []);

  const brokerConnected = !!broker?.connected;
  useEffect(() => {
    if (!brokerConnected) setTradingArmed(false);
  }, [brokerConnected]);

  const onConnect = () => {
    if (brokerBusy) return;
    setBrokerBusy(true);
    const go = brokerConnected ? equityBroker.disconnect() : equityBroker.connect();
    go
      .then((res) => {
        setBroker(res);
        setBrokerMsg(res.reason || null);
        if (!res.connected) setTradingArmed(false);
      })
      .catch((e: Error) => setBrokerMsg(e.message))
      .finally(() => setBrokerBusy(false));
  };

  useEffect(() => {
    if (!alertsOpen) return;
    const onDown = (e: MouseEvent) => {
      if (alertsRef.current && !alertsRef.current.contains(e.target as Node)) setAlertsOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAlertsOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [alertsOpen]);

  useEffect(() => {
    const onResize = () => setNewsH((h) => clampNewsHeight(h));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const onNewsResize = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const originY = e.clientY;
    const originH = newsH;
    const move = (ev: PointerEvent) => setNewsH(clampNewsHeight(originH + (originY - ev.clientY)));
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  useEffect(() => {
    let stop = false;
    let inflight = false;
    const load = () => {
      if (inflight) return;
      inflight = true;
      fetchNews(symbolRef.current)
        .then((res) => {
          if (stop) return;
          setNewsSource(res.source || 'Yahoo Finance');
          setNews(res.items || []);
          setNewsError(res.error);
        })
        .catch((e: Error) => {
          if (!stop) {
            setNews([]);
            setNewsError(e.message || 'news request failed');
          }
        })
        .finally(() => { inflight = false; });
    };
    load();
    const id = window.setInterval(load, 180000);
    return () => { stop = true; window.clearInterval(id); };
  }, [symbol]);

  useEffect(() => {
    const id = window.setInterval(() => {
      setClock(nyParts().label);
      setLocalPhase(equityPhase());
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    let stop = false;
    let inflight = false;
    const load = () => {
      if (inflight) return;
      inflight = true;
      fetchScan(timeframe, minGrade, symbolRef.current)
        .then((res) => {
          if (!stop) {
            setRows(res.rows || []);
            setScanError(null);
          }
        })
        .catch((e: Error) => {
          if (!stop) setScanError(e.message || 'scanner request failed');
        })
        .finally(() => { inflight = false; });
    };
    load();
    const id = window.setInterval(load, 20000);
    return () => { stop = true; window.clearInterval(id); };
  }, [timeframe, minGrade, symbol]);

  useEffect(() => {
    let stop = false;
    let inflight = false;
    const load = () => {
      if (inflight) return;
      inflight = true;
      fetchStateOrFallback(symbol, timeframe, minGrade)
        .then((res) => {
          if (!stop) {
            setState(res);
            setStateError(res.fallback ? 'Backend unreachable — Yahoo bars. Engine panels stay empty until :8010 answers.' : null);
          }
        })
        .catch((e: Error) => {
          if (!stop) setStateError(e.message || 'state request failed');
        })
        .finally(() => { inflight = false; });
    };
    load();
    const id = window.setInterval(load, 15000);
    return () => { stop = true; window.clearInterval(id); };
  }, [symbol, timeframe, minGrade]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stop = false;
    let retry = 0;
    const open = () => {
      if (stop) return;
      try {
        ws = new WebSocket(wsUrl());
      } catch {
        retry = window.setTimeout(open, 5000);
        return;
      }
      ws.onmessage = (ev) => {
        if (stop) return;
        try {
          const msg = JSON.parse(ev.data as string) as EngineState & { type?: string };
          if (msg.type === 'state' && msg.symbol === symbolRef.current && msg.series) {
            setState({ ...msg, feed: 'meridian', fallback: false });
            setStateError(null);
          }
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (!stop) retry = window.setTimeout(open, 5000);
      };
    };
    open();
    return () => {
      stop = true;
      window.clearTimeout(retry);
      ws?.close();
    };
  }, [symbol]);

  useEffect(() => {
    // /api/quote imports Alpaca. With no keys it 500s. The broker badge already
    // says the adapter is simulated, so skip the tape instead of polling the error.
    if (!broker || (broker.mode === 'simulated' && !broker.connected)) {
      setQuote(null);
      return undefined;
    }
    let stop = false;
    const load = () => {
      fetchQuote(symbol)
        .then((res) => { if (!stop) setQuote(res.quote); })
        .catch(() => { if (!stop) setQuote(null); });
    };
    load();
    const id = window.setInterval(load, 10000);
    return () => { stop = true; window.clearInterval(id); };
  }, [symbol, broker]);

  useEffect(() => {
    if (!brokerConnected) {
      setPositions([]);
      return undefined;
    }
    let stop = false;
    const load = () => {
      fetch(`${(import.meta.env.VITE_API_URL as string | undefined) || 'http://127.0.0.1:8010'}/api/broker/positions`)
        .then(async (r) => {
          if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `positions ${r.status}`);
          return r.json() as Promise<{ positions: Position[] }>;
        })
        .then((body) => { if (!stop) setPositions(body.positions || []); })
        .catch((e: Error) => { if (!stop) setBrokerMsg(e.message); });
    };
    load();
    const id = window.setInterval(load, 15000);
    return () => { stop = true; window.clearInterval(id); };
  }, [brokerConnected]);

  const armed = !!state && !state.fallback && !manualHalt && localPhase === 'open';
  const blockReason = state?.fallback
    ? 'Engine is offline. Yahoo is charting only. Orders are not sent.'
    : manualHalt
      ? 'Manual halt: new signals are blocked in this UI only. Nothing is flattened. Orders are not sent.'
      : localPhase !== 'open'
        ? `Equity clock is ${phaseLabel(localPhase)}. New signals are not armed. This does not flatten.`
        : null;

  const surfaced = useMemo(
    () => cardsOf(state).filter((card) => matches(card, alerts)),
    [state, alerts],
  );

  const card: PathCard | null = useMemo(() => {
    if (!surfaced.length) return null;
    if (cardKey !== null && surfaced[cardKey]) return surfaced[cardKey];
    return surfaced[0];
  }, [surfaced, cardKey]);

  useEffect(() => {
    const sig = state?.signal;
    if (!sig || !state || state.fallback) return;
    const id = `${state.symbol}:${sig.bar_time}:${sig.side}`;
    if (primedSym.current !== state.symbol) {
      primedSym.current = state.symbol;
      seen.current.add(id);
      return;
    }
    if (seen.current.has(id)) return;
    seen.current.add(id);
    const fake: PathCard = {
      side: sig.side,
      entry: sig.entry,
      stop: sig.sl,
      tp1: sig.tp1,
      tp2: sig.tp2,
      time: sig.bar_time,
      status: 'OPEN',
      grade: sig.grade,
      regime: state.regime?.name,
    };
    if (!matches(fake, alerts) || !alerts.enabled || !armed) return;
    const text = `Engine signal ${state.symbol} ${sig.side} ${sig.grade}. Not an order.`;
    setToast(text);
    if (alerts.sound) beep();
    if (alerts.notify && 'Notification' in window && Notification.permission === 'granted') {
      new Notification('Meridian equities engine', { body: `${text} Orders are not sent.` });
    }
  }, [state, alerts, armed]);

  const q = query.trim().toUpperCase();
  const visibleRows = rows.filter((row) => {
    if (!q) return true;
    return row.symbol.includes(q) || row.name.toUpperCase().includes(q);
  });

  const eng = state;
  const candles = useMemo(() => candlesOf(state), [state]);
  const first = candles[0]?.c;
  const last = quote?.last ?? eng?.close ?? candles[candles.length - 1]?.c;
  const chg = first != null && last != null ? last - first : null;
  const phase = localPhase;
  const pools = eng?.liquidity?.pools || [];
  const topMag = eng?.liquidity?.top_magnet;
  const cvd = eng?.cvd.value ?? 0;
  const cvdPct = Math.min(100, Math.abs(cvd) / Math.max(Math.abs(eng?.cvd.session_high || 0), Math.abs(eng?.cvd.session_low || 0), 1) * 100);
  const feedLabel = state?.fallback ? 'yahoo fallback' : state?.feed === 'meridian' ? (quote?.live ? 'alpaca iex' : 'meridian') : 'meridian';

  const patchAlerts = (partial: Partial<AlertPrefs>) => setAlerts((prev) => ({ ...prev, ...partial }));

  const enableNotify = async () => {
    patchAlerts({ notify: true });
    if ('Notification' in window && Notification.permission === 'default') {
      await Notification.requestPermission();
    }
  };

  const submitQuery = () => {
    const next = query.trim().toUpperCase().replace(/\./g, '-');
    if (!next) return;
    if (next.includes('!') || next.endsWith('=F') || next.startsWith('/')) {
      setToast('Equities and ETFs only. Futures stay on the futures desk.');
      return;
    }
    if (!/^[A-Z][A-Z0-9.-]{0,9}$/.test(next)) return;
    setSymbol(next);
    setCardKey(null);
    setQuery('');
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="mk" />
          <div>
            MERIDIAN
            <div className="sub">EQUITIES · ENGINE v2.2</div>
          </div>
        </div>
        <form className="search" onSubmit={(e) => { e.preventDefault(); submitQuery(); }}>
          <span className="mono">⌕</span>
          <input
            value={query}
            placeholder="Symbol…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </form>
        <div className="pill">EQUITIES</div>
        <div className="pill">ORDERS NOT SENT</div>
        <div className="spacer" />
        <select className="mini" value={timeframe} onChange={(e) => setTimeframe(e.target.value as (typeof TIMEFRAMES)[number])}>
          {TIMEFRAMES.map((tf) => <option key={tf}>{tf}</option>)}
        </select>
        <select className="mini" value={minGrade} onChange={(e) => setMinGrade(e.target.value as (typeof MIN_GRADES)[number])}>
          {MIN_GRADES.map((g) => <option key={g}>{g}</option>)}
        </select>
        <button
          type="button"
          className={`ctrl-btn ${theme === 'night' ? 'on' : ''}`}
          onClick={() => setTheme(theme === 'night' ? 'blue' : 'night')}
          title="Switch the field between the light turquoise and night blue-gray"
        >
          {theme === 'night' ? 'NIGHT' : 'LIGHT'}
        </button>
        <div className="alerts-menu" ref={alertsRef}>
          <button
            type="button"
            className={`ctrl-btn ${alertsOpen ? 'on' : ''}`}
            aria-haspopup="true"
            aria-expanded={alertsOpen}
            onClick={() => setAlertsOpen((v) => !v)}
            title="Alert filters, notifications, and UI halt"
          >
            ALERTS {manualHalt ? '· HALT' : alerts.enabled ? '· ON' : '· OFF'} {alertsOpen ? '▴' : '▾'}
          </button>
          {alertsOpen && (
            <div className="alerts-drop" role="menu">
              <div className="panel-h">Alert Control <span className="tag">{manualHalt ? 'UI HALT' : alerts.enabled ? 'FILTERS ON' : 'FILTERS OFF'}</span></div>
              <div className="panel-b">
                <button type="button" className={`ctrl-btn ${manualHalt ? 'on' : ''}`} onClick={() => setManualHalt((v) => !v)}>
                  {manualHalt ? 'UI HALT ON · DOES NOT FLATTEN' : 'UI HALT · BLOCKS SIGNALS ONLY'}
                </button>
                <p className="fine">{blockReason || 'Regular session is open. A halt here never flattens and never sends an order.'}</p>
                <div className="ar-row"><span className="lab">Enable filters + notify</span><button type="button" className={`switch ${alerts.enabled ? 'on' : ''}`} onClick={() => patchAlerts({ enabled: !alerts.enabled })} /></div>
                <div className="ar-row">
                  <span className="lab">Min grade</span>
                  <div className="seg">
                    {(['WATCH', 'PRIME', 'ELITE', 'SINGULAR'] as AlertGrade[]).map((g) => (
                      <button key={g} type="button" className={alerts.minGrade === g ? 'on' : ''} onClick={() => patchAlerts({ minGrade: g })}>{g}</button>
                    ))}
                  </div>
                </div>
                <div className="ar-row">
                  <span className="lab">Side</span>
                  <div className="seg">
                    {(['BOTH', 'LONG', 'SHORT'] as AlertSide[]).map((g) => (
                      <button key={g} type="button" className={alerts.side === g ? 'on' : ''} onClick={() => patchAlerts({ side: g })}>{g}</button>
                    ))}
                  </div>
                </div>
                <div className="ar-row">
                  <span className="lab">Regime</span>
                  <div className="seg">
                    {(['ANY', 'TREND', 'RANGE', 'TRANS'] as AlertRegime[]).map((g) => (
                      <button key={g} type="button" className={alerts.regime === g ? 'on' : ''} onClick={() => patchAlerts({ regime: g })}>{g}</button>
                    ))}
                  </div>
                </div>
                <div className="ar-row"><span className="lab">Sound</span><button type="button" className={`switch ${alerts.sound ? 'on' : ''}`} onClick={() => patchAlerts({ sound: !alerts.sound })} /></div>
                <div className="ar-row"><span className="lab">Browser notify</span><button type="button" className={`switch ${alerts.notify ? 'on' : ''}`} onClick={() => void enableNotify()} /></div>
                <p className="fine">Local only. Filters hide non-matching engine signals in this UI. This desk does not submit Alpaca orders.</p>
                {eng?.risk && !eng.fallback && (
                  <p className="fine">Engine counters · flips {eng.risk.regime_flip_count} · path breaks {eng.risk.consecutive_path_breaks} · min density {eng.risk.min_density}.</p>
                )}
                <button
                  type="button"
                  className="ctrl-btn"
                  onClick={() => {
                    setToast('Test alert · local UI only. Orders are not sent.');
                    if (alerts.sound) beep();
                  }}
                >
                  TEST LOCAL ALERT
                </button>
                {toast && <p className="fine">{toast}</p>}
              </div>
            </div>
          )}
        </div>
        <div className={`sig-badge ${!armed || !eng?.signal ? 'wait' : eng.signal.side === 'BUY' ? 'buy' : 'sell'}`}>
          {!armed ? 'NOT ARMED' : eng?.signal ? eng.signal.side : 'WAIT'}
        </div>
        <div className="pill"><span className="dot" /> {feedLabel}</div>
      </header>

      <div className="caption">
        <div className="cap-txt">
          <b>{state?.symbol || symbol}</b>
          <span className="cap-seg">Regime <span className="v">{eng && !eng.fallback ? eng.regime.name : '—'}</span></span>
          <span className="cap-seg">Lattice <span className="v">{eng && !eng.fallback ? `${eng.lattice.grade_l}/${eng.lattice.grade_s}` : '—'}</span></span>
          <span className="cap-seg">Path <span className="v">{eng?.path?.status || '—'}</span></span>
          <span className="cap-seg">Preset <span className="v">{presetFor(timeframe)}</span></span>
          <span className="cap-seg">OFI <span className="v">{eng?.fallback ? 'chart only' : 'close-to-close proxy'}</span></span>
        </div>
        <div className="live-status">
          <span className="pulse" />
          <span>{phaseLabel(phase)} · {feedLabel} · orders not sent</span>
        </div>
      </div>

      <div className="main">
        <div className="col left">
          <div className="panel">
            <div className="panel-h">Scanner <span className="tag">{visibleRows.length}</span></div>
            <div className="scan-row hdr">
              <div>SYM</div><div>REG</div><div>BIAS</div><div>LAT</div><div>PATH</div><div>SIG</div>
            </div>
            {scanError && <div className="err">{scanError}</div>}
            {!scanError && rows.some((row) => row.error) && <div className="err">{rows.find((row) => row.error)?.error}</div>}
            {visibleRows.map((row) => {
              const grade = row.grade_l || row.grade_s ? `${row.grade_l || '—'}/${row.grade_s || '—'}` : '—';
              const showSig = !alerts.enabled || !row.signal || matches({
                side: row.signal,
                entry: 0, stop: 0, tp1: 0, tp2: 0, time: null, status: 'OPEN',
                grade: row.signal_grade || undefined,
                regime: row.regime || undefined,
              }, alerts);
              return (
                <button
                  key={row.symbol}
                  type="button"
                  className={`scan-row ${row.symbol === symbol ? 'sel' : ''}`}
                  onClick={() => { setSymbol(row.symbol); setCardKey(null); }}
                >
                  <div className="sym" title={row.name}>{row.symbol}</div>
                  <div className={`reg ${row.regime || ''}`}>{(row.regime || '—').slice(0, 5)}</div>
                  <div className={`bias ${row.bias || 'flat'}`}>{(row.bias || '—').slice(0, 4)}</div>
                  <div style={{ textAlign: 'center', fontSize: 9 }}>{grade}</div>
                  <div style={{ textAlign: 'center', fontSize: 9, color: 'var(--muted)' }}>{row.path_status || '—'}</div>
                  <div className={`sig ${showSig && row.signal ? row.signal : 'dash'}`}>{showSig && row.signal ? row.signal : '—'}</div>
                </button>
              );
            })}
            {!rows.length && !scanError && <div className="pos-empty">Loading scanner…</div>}
          </div>
          <div className="panel news-panel" style={{ height: newsH, flexBasis: newsH }}>
            <div className="panel-h">Equity news <span className="tag">{newsSource}</span></div>
            {newsError && <div className="err">{newsError}</div>}
            {!newsError && !news.length && <div className="pos-empty">Loading headlines…</div>}
            <div className="news-list">
              {news.map((item) => (
                <a key={item.url || item.title} className="news-item" href={item.url} target="_blank" rel="noreferrer">
                  <div className="meta">{item.source} · {item.time ? fmtEt(Date.parse(item.time)) : '—'}</div>
                  <div className="hd">{item.title}</div>
                </a>
              ))}
            </div>
            <div
              className="news-resize"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize news"
              title="Drag up to show more news"
              onPointerDown={onNewsResize}
            />
          </div>
        </div>

        <div className="col mid">
          <div className="panel" style={{ marginBottom: 0 }}>
            <div className="dd-head">
              <div>
                <div className="dd-title">
                  <span className="s">{state?.symbol || symbol}</span>
                  <span className="p">{last != null ? px(last) : '—'}</span>
                  {chg != null && <span className={`d ${chg >= 0 ? 'up' : 'dn'}`}>{chg >= 0 ? '+' : ''}{px(chg)} window</span>}
                </div>
                <div className="dd-meta">
                  <span>ADX <b>{eng && !eng.fallback ? eng.regime.adx : '—'}</b></span>
                  <span>ATR-RS <b>{eng && !eng.fallback ? eng.regime.atr_rs : '—'}</b></span>
                  <span>RR <b>{eng && !eng.fallback ? eng.regime.rr : '—'}</b></span>
                  <span>Bars <b>{candles.length}</b></span>
                  <span>bid/ask <b>{quote?.bid != null && quote.ask != null ? `${px(quote.bid)} / ${px(quote.ask)}` : '—'}</b></span>
                </div>
              </div>
              <div className="dd-preset">
                <div className="k">PRESET</div>
                <div>{presetFor(timeframe)}</div>
              </div>
            </div>
          </div>

          <div className="panel chart-panel">
            <div className="tabs">
              {(['chart', 'lattice', 'pools', 'blotter'] as const).map((id) => (
                <button key={id} type="button" className={tab === id ? 'on' : ''} onClick={() => setTab(id)}>
                  {id === 'chart' ? 'Price · VWAP' : id === 'lattice' ? 'Event Lattice' : id === 'pools' ? 'Liquidity Memory' : 'Path Blotter'}
                </button>
              ))}
            </div>
            {stateError && <div className="err">{stateError}</div>}
            {tab === 'chart' && (
              <div className="chart-wrap">
                <PriceChart
                  candles={candles}
                  engine={eng ? { close: eng.close, series: eng.series } : null}
                  card={card}
                  sampleNote={stateError || (!state ? 'Loading candles…' : null)}
                />
              </div>
            )}
            {tab === 'lattice' && (
              <div className="tab-body">
                <div className="ev-row hdr"><div>SIDE</div><div>GRADE · DENSITY</div><div>ARMED</div></div>
                <div className="ev-row"><div>LONG</div><div>{eng?.lattice.grade_l || '—'} · {eng?.lattice.dens_l ?? '—'}</div><div>{eng?.gates.armed_type_l || '—'}</div></div>
                <div className="ev-row"><div>SHORT</div><div>{eng?.lattice.grade_s || '—'} · {eng?.lattice.dens_s ?? '—'}</div><div>{eng?.gates.armed_type_s || '—'}</div></div>
                <p className="fine" style={{ padding: 8 }}>
                  Live lattice reading from /api/state. Stocks use the same engine document as the command center.
                </p>
              </div>
            )}
            {tab === 'pools' && (
              <div className="tab-body">
                <div className="pool-row hdr"><div>PRICE</div><div>DIR</div><div>MAGNET</div><div>SCORE</div></div>
                {pools.length === 0 && <div className="pos-empty">No active liquidity pools on this bar.</div>}
                {pools.map((pool) => (
                  <div key={`${pool.price}-${pool.dir}`} className={`pool-row ${pool.dir < 0 ? 'bear' : ''}`}>
                    <div>{px(pool.price)}</div>
                    <div>{pool.dir > 0 ? 'BUY' : 'SELL'}</div>
                    <div className="pool-bar"><div className="fill" style={{ width: `${Math.min(100, pool.magnet * 20)}%` }} /></div>
                    <div>{pool.magnet.toFixed(2)}</div>
                  </div>
                ))}
                {topMag?.price != null && <p className="fine" style={{ padding: 8 }}>Top magnet {px(topMag.price)} · score {topMag.magnet}</p>}
              </div>
            )}
            {tab === 'blotter' && (
              <div className="tab-body">
                <PathCards cards={surfaced} active={card} onPick={setCardKey} armed={armed} />
              </div>
            )}
          </div>

          <div className="panel hist">
            <div className="panel-h">
              <span>Trade History <span className="tag">{surfaced.length}/{state?.signals?.length ?? 0} engine</span></span>
              <button type="button" className="ctrl-btn" onClick={() => downloadHistory(state?.symbol || symbol, surfaced)}>
                Download CSV
              </button>
            </div>
            <div className="hist-scroll">
              <PathCards cards={surfaced} active={card} onPick={setCardKey} armed={armed} />
              {!surfaced.length && <div className="pos-empty">No engine signals to show.</div>}
            </div>
          </div>

          <div className="panel">
            <div className="panel-h">
              Positions
              <span className={`tag broker-tag ${brokerConnected ? (tradingArmed ? 'armed' : 'conn') : ''}`}>
                {uiStateLabel(broker)}{tradingArmed ? ' · ARMED' : ''}
              </span>
            </div>
            <div className="panel-b">
              <div className="pos-head">
                <button
                  type="button"
                  className={`pos-btn ${brokerConnected ? 'deployed' : ''}`}
                  onClick={onConnect}
                  disabled={brokerBusy}
                  title={brokerConnected ? 'Disconnect the Alpaca adapter' : 'Deploy the Alpaca adapter'}
                >
                  {brokerBusy ? '… CHECKING' : brokerConnected ? '⏻ DISCONNECT' : '⚡ CONNECT'}
                </button>
                <button
                  type="button"
                  className={`pos-btn ${tradingArmed ? 'trading' : ''}`}
                  disabled={!brokerConnected}
                  onClick={() => setTradingArmed((v) => !v)}
                  title="Local arm only. This desk does not call /api/broker/order."
                >
                  {tradingArmed ? '■ STOP TRADING' : '▶ START TRADING'}
                </button>
              </div>
              <div className="broker-status">
                <div><span className="lab">State</span> {uiStateLabel(broker)}</div>
                <div><span className="lab">Mode</span> {broker?.mode || '—'}</div>
                <div><span className="lab">Equity</span> {broker?.equity != null ? px(broker.equity) : '—'}</div>
                <div><span className="lab">Trading</span> {tradingArmed ? 'armed locally · no order posted' : 'stopped'}</div>
              </div>
              {brokerMsg && <p className="fine">{brokerMsg}</p>}
              {positions.length > 0 && positions.map((pos) => (
                <p key={pos.symbol} className="fine">
                  {pos.symbol} {pos.side} {pos.qty} @ {px(pos.avg_entry_price)} · P/L {px(pos.unrealized_pl)}
                </p>
              ))}
              {!positions.length && (
                <div className="pos-empty">
                  {brokerConnected
                    ? 'No open equity positions on the Alpaca account.'
                    : 'No equity positions. Alpaca keys live in backend/.env, then Connect.'}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="col right">
          <div className="panel">
            <div className="panel-h">Meridian Dashboard <span className="tag">engine · stocks</span></div>
            <div className="dash-grid">
              <Cell k="Preset" v={presetFor(timeframe)} />
              <Cell k="Regime" v={eng && !eng.fallback ? `${eng.regime.name} ${eng.regime.adx}` : '—'} />
              <Cell k="Bias" v={eng && !eng.fallback ? eng.bias.dir : '—'} />
              <Cell k="Ribbon" v={eng && !eng.fallback ? eng.regime.ribbon : '—'} />
              <Cell k="VWAP Zone" v={eng?.vwap.zone || '—'} />
              <Cell k="Lattice L/S" v={eng && !eng.fallback ? `L ${eng.lattice.grade_l} · S ${eng.lattice.grade_s}` : '—'} />
              <Cell k="Armed" v={eng && !eng.fallback ? `${eng.gates.bull_armed ? 'L' : '—'}/${eng.gates.bear_armed ? 'S' : '—'}` : '—'} />
              <Cell k="Magnets" v={eng?.liquidity ? `${eng.liquidity.active_count}${topMag?.price != null ? ' · ' + px(topMag.price) : ''}` : '—'} />
              <Cell k="Path" v={eng?.path ? `${eng.path.side} · ${eng.path.status}` : '—'} />
              <Cell k="Signal" v={armed && eng?.signal ? `${eng.signal.side} ${eng.signal.grade}` : 'not armed'} />
              <Cell k="ATR-RS · RR" v={eng && !eng.fallback ? `${eng.regime.atr_rs} · ${eng.regime.rr}` : '—'} />
              <Cell k="Session" v={phaseLabel(phase)} />
              <div className="dash-cell full">
                <div className="l">OFI</div>
                <div className="v">{eng?.fallback ? 'yahoo chart only' : `close-to-close volume proxy · CVD ${cvd.toLocaleString()}`}</div>
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-h">3-Gate Core <span className="tag">bias · armed · zone</span></div>
            <div className="panel-b">
              <Gate n="1" ok={!!eng && !eng.fallback && (eng.gates.gate1_long || eng.gates.gate1_short)} label="Bias · regime" value={eng && !eng.fallback ? (eng.gates.gate1_long ? 'LONG' : eng.gates.gate1_short ? 'SHORT' : 'FLAT') : '—'} />
              <Gate n="2" ok={!!eng && !eng.fallback && (eng.gates.bull_armed || eng.gates.bear_armed)} label="Armed · sweep / reclaim" value={eng && !eng.fallback ? (eng.gates.bull_armed ? eng.gates.armed_type_l || 'LONG' : eng.gates.bear_armed ? eng.gates.armed_type_s || 'SHORT' : 'IDLE') : '—'} />
              <Gate n="3" ok={!!eng && !eng.fallback && ((eng.gates.in_bull_zone && eng.gates.grade_ok_l) || (eng.gates.in_bear_zone && eng.gates.grade_ok_s))} label="Zone · grade" value={eng && !eng.fallback ? ((eng.gates.in_bull_zone && eng.gates.grade_ok_l) || (eng.gates.in_bear_zone && eng.gates.grade_ok_s) ? 'PASS' : 'PENDING') : '—'} />
              <p className="fine">Engine flags from /api/state. The equity clock still decides whether a signal is armed.</p>
            </div>
          </div>

          <div className="panel">
            <div className="panel-h">Order Flow Intelligence <span className="tag">close-to-close proxy</span></div>
            <div className="panel-b">
              <div className="kpi-grid">
                <div className="kpi"><div className="l">CVD</div><div className="v" style={{ color: cvd >= 0 ? 'var(--emerald)' : 'var(--crimson)' }}>{cvd.toLocaleString()}</div><div className="s">{eng?.cvd.slope || '—'}</div></div>
                <div className="kpi"><div className="l">Source</div><div className="v">{eng?.ofi.source || 'px'}</div><div className="s">not footprint delta</div></div>
                <div className="kpi"><div className="l">Absorb</div><div className="v">{eng && !eng.fallback ? (eng.ofi.absorption_bull ? '↑' : eng.ofi.absorption_bear ? '↓' : '—') : '—'}</div><div className="s">close-to-close</div></div>
                <div className="kpi"><div className="l">Stack</div><div className="v">{eng?.ofi.stack_bull ? `↑ ${eng.ofi.stack_count}` : eng?.ofi.stack_bear ? `↓ ${eng.ofi.stack_count}` : '—'}</div><div className="s">proxy rows</div></div>
              </div>
              <div className="cvd-track">
                <div className="cvd-zero" />
                <div className={`cvd-fill ${cvd >= 0 ? 'pos' : 'neg'}`} style={{ width: `${cvdPct / 2}%` }} />
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-h">Session <span className="tag">{clock}</span></div>
            <div className="panel-b">
              <div className="sess-grid">
                <Pill label="OPEN" on={phase === 'open'} />
                <Pill label="PRE" on={phase === 'pre'} />
                <Pill label="AFTER" on={phase === 'after'} />
                <Pill label="CLOSED" on={phase === 'closed'} />
              </div>
              <div className="sess-range">
                <div className="c"><div className="l">RTH</div><div>09:30–16:00 ET</div></div>
                <div className="c"><div className="l">PREMARKET</div><div>04:00–09:30 ET</div></div>
                <div className="c"><div className="l">AFTER HOURS</div><div>16:00–20:00 ET</div></div>
                <div className="c"><div className="l">LAST BAR</div><div>{fmtEt(candles[candles.length - 1]?.t)}</div></div>
              </div>
              <p className="fine">US cash session. Signals arm only while RTH is open. Holidays are not skipped.</p>
              <p className="fine">{eng?.fallback ? 'VWAP on the fallback chart is computed in the browser from Yahoo bars.' : 'VWAP is the engine daily anchor from /api/state.'}</p>
            </div>
          </div>
        </div>
      </div>

      <div className="ticker">
        <span className="hdr">STATUS</span>
        <span>{state?.symbol || symbol}</span>
        <span>{eng && !eng.fallback ? eng.regime.name : 'equities'}</span>
        <span>last {fmtEt(candles[candles.length - 1]?.t)}</span>
        <span>{armed ? 'gate open' : 'not armed'}</span>
        <span>orders not sent</span>
        <span>{candles.length ? `${candles.length} bars` : stateError || 'loading'}</span>
      </div>
    </div>
  );
}

function Cell({ k, v }: { k: string; v: string }) {
  return <div className="dash-cell"><div className="l">{k}</div><div className="v">{v}</div></div>;
}

function Gate({ n, ok, label, value }: { n: string; ok: boolean; label: string; value: string }) {
  return (
    <div className="gate-row">
      <div className={`gate-num ${ok ? 'pass' : ''}`}>{n}</div>
      <div className="gate-lbl">{label}</div>
      <div className="gate-val">{value}</div>
    </div>
  );
}

function Pill({ label, on }: { label: string; on: boolean }) {
  return <div className={`sess-pill ${on ? 'on' : ''}`}><div className="l">{label}</div><div className="v">{on ? '●' : '—'}</div></div>;
}

function PathCards({ cards, active, onPick, armed }: { cards: PathCard[]; active: PathCard | null; onPick: (i: number) => void; armed: boolean }) {
  return (
    <>
      {cards.map((row, i) => (
        <div
          key={`${row.time}-${i}`}
          className={`path-card ${row.side === 'BUY' ? 'long' : 'short'} ${active === row ? 'on' : ''}`}
          onClick={() => onPick(i)}
        >
          <div className="ph">
            <span className="d">{row.side === 'BUY' ? 'LONG' : 'SHORT'}</span>
            <span className="g">{row.grade || '—'} · {row.regime || 'engine'}</span>
            <span className={`st ${row.status}`}>{row.status}{row.status === 'OPEN' && !armed ? ' · not armed' : ''}</span>
          </div>
          <div className="path-grid">
            <div className="path-cell"><div className="l">ENTRY</div><div className="v">{px(row.entry)}</div></div>
            <div className="path-cell SL"><div className="l">STOP</div><div className="v">{px(row.stop)}</div></div>
            <div className="path-cell T1"><div className="l">TP1</div><div className="v">{px(row.tp1)}</div></div>
            <div className="path-cell T2"><div className="l">TP2</div><div className="v">{px(row.tp2)}</div></div>
          </div>
          <div className="note">{fmtEt(row.time)} · engine signal · orders are not sent</div>
        </div>
      ))}
    </>
  );
}
