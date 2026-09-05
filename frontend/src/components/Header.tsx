"use client";

import { useState } from "react";
import { SYMBOLS, TIMEFRAMES, normalizeSymbol } from "@/lib/constants";
import type { ConnectionStatus, Timeframe } from "@/lib/types";
import type { Theme } from "@/hooks/useTheme";

export function Header({
  symbol,
  onSymbol,
  timeframe,
  onTimeframe,
  status,
  theme,
  onToggleTheme,
  lastPrice,
}: {
  symbol: string;
  onSymbol: (symbol: string) => void;
  timeframe: Timeframe;
  onTimeframe: (tf: Timeframe) => void;
  status: ConnectionStatus;
  theme: Theme;
  onToggleTheme: () => void;
  lastPrice: number | null;
}) {
  const [draft, setDraft] = useState("");

  const submit = () => {
    const next = normalizeSymbol(draft || symbol);
    if (next) onSymbol(next);
    setDraft("");
  };

  return (
    <header className="dash-header">
      <div className="brand">
        SNIPER<span>TRADER</span>
      </div>
      <div className="header-controls">
        <label className="field">
          <span>Symbol</span>
          <select
            value={SYMBOLS.some((s) => s.symbol === symbol) ? symbol : "__custom"}
            onChange={(e) => {
              if (e.target.value !== "__custom") onSymbol(e.target.value);
            }}
          >
            {SYMBOLS.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.label}
              </option>
            ))}
            {!SYMBOLS.some((s) => s.symbol === symbol) && (
              <option value="__custom">{symbol}</option>
            )}
          </select>
        </label>
        <form
          className="symbol-entry"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <input
            aria-label="Custom symbol"
            placeholder="BTCUSDT"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
          />
        </form>
        <div className="tf-group" role="group" aria-label="Timeframe">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              type="button"
              className={tf === timeframe ? "active" : ""}
              onClick={() => onTimeframe(tf)}
            >
              {tf}
            </button>
          ))}
        </div>
        {lastPrice != null && (
          <div className="last-px">
            {lastPrice >= 1000 ? lastPrice.toFixed(1) : lastPrice.toFixed(2)}
          </div>
        )}
      </div>
      <div className="header-right">
        <span className={`status-pill status-${status}`}>{status}</span>
        <button type="button" className="theme-btn" onClick={onToggleTheme}>
          {theme === "dark" ? "LIGHT" : "DARK"}
        </button>
      </div>
    </header>
  );
}
