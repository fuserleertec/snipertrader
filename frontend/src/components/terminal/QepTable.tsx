"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  ENGINE_META,
  ENGINE_ORDER,
  ENSEMBLE_PICKS,
  QEP_CATS,
  convictionOf,
  enginesForSetup,
  whyForSetup,
  type EnsemblePick,
  type QepMode,
} from "@/lib/mocks/terminal";
import { realizedMultiple } from "@/lib/signals";
import type { Signal, SignalStatus, SetupType } from "@/lib/types";
import { SETUP_TYPES, SIGNAL_STATUSES, SYMBOLS } from "@/lib/constants";

function convColor(c: number): string {
  return c >= 70 ? "var(--emerald)" : c >= 50 ? "var(--gold)" : "var(--red)";
}

function fmtPx(n: number): string {
  return n >= 1000 ? n.toFixed(1) : n.toFixed(2);
}

export function QepTable({
  signals,
  lastPrice,
  selectedId,
  onSelectSignal,
  soundOn,
  onToggleSound,
  initialMode,
  cards,
  onSetupFilter,
}: {
  signals: Signal[];
  lastPrice: number | null;
  selectedId: string | null;
  onSelectSignal: (signal: Signal) => void;
  soundOn: boolean;
  onToggleSound: () => void;
  initialMode?: QepMode;
  cards?: ReactNode;
  onSetupFilter?: (setup: SetupType | "all") => void;
}) {
  const startMode: QepMode = initialMode === "setups" || initialMode === "activity" ? initialMode : "market";
  const [mode, setMode] = useState<QepMode>(startMode);
  const [cat, setCat] = useState(startMode === "setups" ? "Setups" : QEP_CATS[startMode][0]);
  const [sub, setSub] = useState<"All" | "Buy" | "Sell" | "Hold">("All");
  const [typeFilter, setTypeFilter] = useState<SetupType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<SignalStatus | "all">("all");
  const [symbolFilter, setSymbolFilter] = useState("all");

  const cats = mode === "setups" ? ["Setups"] : QEP_CATS[mode];

  const ensemble = useMemo(
    () =>
      ENSEMBLE_PICKS.filter(
        (p) => p.mode === mode && p.category === cat && (sub === "All" || p.signal === sub),
      ),
    [mode, cat, sub],
  );

  const setupRows = useMemo(
    () =>
      signals.filter((s) => {
        if (typeFilter !== "all" && s.setup_type !== typeFilter) return false;
        if (statusFilter !== "all" && s.status !== statusFilter) return false;
        if (symbolFilter !== "all" && s.symbol !== symbolFilter) return false;
        if (sub === "Buy" && s.side !== "long") return false;
        if (sub === "Sell" && s.side !== "short") return false;
        return true;
      }),
    [signals, typeFilter, statusFilter, symbolFilter, sub],
  );

  const download = () => {
    const header = "ts_ms,symbol,setup_type,side,entry,stop,target,status,realized_r,exit_price,closed_ts_ms,confidence,trigger_event_ids";
    const lines = setupRows.map((r) =>
      [r.ts_ms, r.symbol, r.setup_type, r.side, r.entry, r.stop, r.target, r.status, r.realized_r ?? "", r.exit_price ?? "", r.closed_ts_ms ?? "", r.confidence, r.trigger_event_ids.join("|")].join(","),
    );
    const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "signals.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">02</span>
        <h2>Quantum Ensemble Picks</h2>
        <span className="sim">Synthetic Demo</span>
      </div>
      <div className="sec-sub">
        Five engines — Kronos (temporal), SNN (spike/regime), MiroFish (pattern), Fundamental
        (filings), Quantum (weighted resolver) — vote into a single 0–100 conviction, then rank
        into a provenance-tagged table. Setup cards pin by <code>signal.id</code> (one ACTIVE per
        locked setup 1–6). Click joins overlays via <code>trigger_event_ids</code>.
      </div>
      {cards}

      <div className="qep-bar">
        <div className="qep-toggle">
          {(
            [
              ["market", "Market Signals"],
              ["activity", "Smart Money Activity"],
              ["setups", "Setup Signals"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={mode === id ? "active" : ""}
              data-qep={id}
              onClick={() => {
                setMode(id);
                setCat(id === "setups" ? "Setups" : QEP_CATS[id][0]);
                setSub("All");
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="qep-legend">
          {ENGINE_ORDER.map((k) => (
            <span key={k}>
              <b style={{ color: ENGINE_META[k].color }}>{k}</b> {ENGINE_META[k].label}
            </span>
          ))}
        </div>
      </div>

      <div className="qep-tabs">
        <div className="qep-cats">
          {cats.map((c) => (
            <button key={c} type="button" className={cat === c ? "active" : ""} onClick={() => setCat(c)}>
              {c}
            </button>
          ))}
        </div>
        <div className="qep-subs">
          {(["All", "Buy", "Sell", "Hold"] as const).map((s) => (
            <button
              key={s}
              type="button"
              data-sub={s}
              className={sub === s ? "active" : ""}
              onClick={() => setSub(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {mode === "setups" && (
        <div className="table-tools" style={{ marginBottom: 10 }}>
          <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
            <option value="all">all symbol</option>
            {SYMBOLS.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol}
              </option>
            ))}
          </select>
          <select
            value={typeFilter}
            onChange={(e) => {
              const next = e.target.value as SetupType | "all";
              setTypeFilter(next);
              onSetupFilter?.(next);
            }}
          >
            <option value="all">all setup_type</option>
            {SETUP_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as SignalStatus | "all")}>
            <option value="all">all status</option>
            {SIGNAL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button type="button" onClick={download}>
            CSV
          </button>
          <button type="button" onClick={onToggleSound}>
            sound {soundOn ? "on" : "off"}
          </button>
          <span className="qep-name">{setupRows.length} rows</span>
        </div>
      )}

      <div className="qep-wrap">
        <table className="qep-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Asset</th>
              <th>Signal</th>
              <th>Last / Chg</th>
              <th>Target</th>
              <th>Conviction</th>
              <th>Engines</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {mode === "setups"
              ? setupRows.map((s, i) => (
                  <SetupRow
                    key={s.id}
                    rank={i + 1}
                    signal={s}
                    lastPrice={lastPrice}
                    selected={selectedId === s.id}
                    onSelect={() => onSelectSignal(s)}
                  />
                ))
              : ensemble.map((p, i) => <EnsembleRow key={`${p.mode}:${p.ticker}:${p.category}`} rank={i + 1} pick={p} />)}
            {mode === "setups" && setupRows.length === 0 && (
              <tr>
                <td colSpan={8} className="note">
                  Waiting for setup_signals…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EngineChips({ engines }: { engines: Record<string, string> }) {
  return (
    <div className="qep-chips">
      {ENGINE_ORDER.map((k) => (
        <span key={k} className="qep-chip" title={`${ENGINE_META[k].label}: ${engines[k]}`} style={{ color: ENGINE_META[k].color }}>
          {k}
        </span>
      ))}
    </div>
  );
}

function SetupRow({
  rank,
  signal,
  lastPrice,
  selected,
  onSelect,
}: {
  rank: number;
  signal: Signal;
  lastPrice: number | null;
  selected: boolean;
  onSelect: () => void;
}) {
  const conv = convictionOf(signal);
  const engines = enginesForSetup(signal);
  const chg = lastPrice != null ? (((lastPrice - signal.entry) / signal.entry) * 100).toFixed(2) : "0.00";
  const up = Number(chg) >= 0;
  return (
    <tr className={`qep-row${selected ? " sel" : ""}`} onClick={onSelect}>
      <td className="qep-rank">{rank}</td>
      <td>
        <div className="qep-tk">{signal.symbol}</div>
        <div className="qep-name">{signal.setup_type}</div>
      </td>
      <td>
        <span className={`qep-sig ${signal.side === "long" ? "buy" : "sell"}`}>
          {signal.side === "long" ? "BUY" : "SELL"}
        </span>
      </td>
      <td className="qep-price">
        {fmtPx(lastPrice ?? signal.entry)}
        <br />
        <span className={up ? "qep-chg-up" : "qep-chg-down"}>
          {up ? "+" : ""}
          {chg}%
        </span>
      </td>
      <td className="qep-target">{fmtPx(signal.target)}</td>
      <td>
        <div className="qep-conv">
          <div className="qep-track">
            <div className="qep-fill" style={{ width: `${conv}%`, background: convColor(conv) }} />
          </div>
          <div className="qep-num">{conv}</div>
        </div>
      </td>
      <td>
        <EngineChips engines={engines} />
      </td>
      <td className="qep-reason">
        {whyForSetup(signal)}
        {realizedMultiple(signal) != null ? ` · realized_r ${realizedMultiple(signal)!.toFixed(2)}` : ""}
      </td>
    </tr>
  );
}

function EnsembleRow({ rank, pick }: { rank: number; pick: EnsemblePick }) {
  const up = pick.chg.trim().startsWith("+");
  return (
    <tr className="qep-row">
      <td className="qep-rank">{rank}</td>
      <td>
        <div className="qep-tk">{pick.ticker}</div>
        <div className="qep-name">{pick.company}</div>
      </td>
      <td>
        <span className={`qep-sig ${pick.signal === "Buy" ? "buy" : pick.signal === "Sell" ? "sell" : "hold"}`}>
          {pick.signal.toUpperCase()}
        </span>
      </td>
      <td className="qep-price">
        {pick.last}
        <br />
        <span className={up ? "qep-chg-up" : "qep-chg-down"}>{pick.chg}</span>
      </td>
      <td className="qep-target">{pick.target}</td>
      <td>
        <div className="qep-conv">
          <div className="qep-track">
            <div className="qep-fill" style={{ width: `${pick.conviction}%`, background: convColor(pick.conviction) }} />
          </div>
          <div className="qep-num">{pick.conviction}</div>
        </div>
      </td>
      <td>
        <EngineChips engines={pick.engines} />
      </td>
      <td className="qep-reason">{pick.reason}</td>
    </tr>
  );
}
