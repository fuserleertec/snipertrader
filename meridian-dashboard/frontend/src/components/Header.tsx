import { useEffect, useState } from 'react';
import { TIMEFRAMES, type Feed, type ThemeName, type Timeframe } from '../types';
import { describeSession } from '../lib/session';

interface HeaderProps {
  draft: string;
  onDraft: (value: string) => void;
  onSubmitSymbol: () => void;
  timeframe: Timeframe;
  onTimeframe: (timeframe: Timeframe) => void;
  extended: boolean;
  onExtended: () => void;
  theme: ThemeName;
  onTheme: () => void;
  feed: Feed;
}

export function Header({
  draft,
  onDraft,
  onSubmitSymbol,
  timeframe,
  onTimeframe,
  extended,
  onExtended,
  theme,
  onTheme,
  feed,
}: HeaderProps) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const session = describeSession(now);
  const feedLabel = feed === 'alpaca' ? 'ALPACA · IEX' : feed === 'yahoo' ? 'YAHOO · DELAYED' : 'OFFLINE';

  return (
    <header className="desk-header">
      <div className="brand">
        <span className="brand-mark">MERIDIAN</span>
        <span className="brand-sub">EQUITIES</span>
      </div>

      <form
        className="symbol-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmitSymbol();
        }}
      >
        <label className="sr" htmlFor="symbol">
          Symbol
        </label>
        <input
          id="symbol"
          value={draft}
          spellCheck={false}
          autoCapitalize="characters"
          placeholder="SPY"
          onChange={(event) => onDraft(event.target.value.toUpperCase())}
        />
      </form>

      <div className="tf-row" role="group" aria-label="Timeframe">
        {TIMEFRAMES.map((tf) => (
          <button key={tf} type="button" className={tf === timeframe ? 'tf on' : 'tf'} onClick={() => onTimeframe(tf)}>
            {tf === '1d' ? '1D' : tf}
          </button>
        ))}
        <button type="button" className={extended ? 'tf on' : 'tf'} onClick={onExtended} aria-pressed={extended}>
          EXT
        </button>
      </div>

      <div className="header-right">
        <div className={`session pill ${session.name === 'RTH' ? 'up' : session.name === 'CLOSED' ? 'dim' : 'amber'}`}>
          <span className="live-dot" />
          <span>{session.name}</span>
          <span className="clock">{session.clock}</span>
        </div>
        <div className="cue">{session.cue}</div>
        <div className={`pill feed ${feed === 'offline' ? 'down' : feed === 'alpaca' ? 'up' : ''}`}>{feedLabel}</div>
        <button type="button" className="theme-btn" onClick={onTheme}>
          {theme === 'dark' ? 'LIGHT' : 'DARK'}
        </button>
      </div>
    </header>
  );
}
