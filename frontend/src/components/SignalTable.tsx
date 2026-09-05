"use client";

import { useEffect, useMemo, useState } from "react";
import { SETUP_TYPES, SIGNAL_STATUSES, SYMBOLS } from "@/lib/constants";
import { isMockMode } from "@/lib/env";
import { fetchSignals } from "@/lib/http";
import { outcomeLabel, realizedMultiple, zoneLabel } from "@/lib/signals";
import type { SetupType, Signal, SignalStatus } from "@/lib/types";

function utcStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

function dayStart(iso: string): number | null {
  if (!iso) return null;
  const t = Date.parse(`${iso}T00:00:00.000Z`);
  return Number.isFinite(t) ? t : null;
}

function dayEnd(iso: string): number | null {
  if (!iso) return null;
  const t = Date.parse(`${iso}T23:59:59.999Z`);
  return Number.isFinite(t) ? t : null;
}

function toCsv(rows: Signal[]): string {
  const header = [
    "ts_ms",
    "symbol",
    "setup_type",
    "side",
    "entry",
    "stop",
    "target",
    "status",
    "realized_r",
    "exit_price",
    "closed_ts_ms",
    "confidence",
    "trigger_event_ids",
  ];
  const lines = rows.map((r) =>
    [
      r.ts_ms,
      r.symbol,
      r.setup_type,
      r.side,
      r.entry,
      r.stop,
      r.target,
      r.status,
      r.realized_r ?? "",
      r.exit_price ?? "",
      r.closed_ts_ms ?? "",
      r.confidence,
      r.trigger_event_ids.join("|"),
    ].join(","),
  );
  return [header.join(","), ...lines].join("\n");
}

export function SignalTable({
  rows,
  selectedId,
  onSelect,
  soundOn,
  onToggleSound,
}: {
  rows: Signal[];
  selectedId: string | null;
  onSelect: (signal: Signal) => void;
  soundOn: boolean;
  onToggleSound: () => void;
}) {
  const mocks = isMockMode();
  const [typeFilter, setTypeFilter] = useState<SetupType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<SignalStatus | "all">("all");
  const [symbolFilter, setSymbolFilter] = useState("all");
  const [fromDay, setFromDay] = useState("");
  const [toDay, setToDay] = useState("");
  const [liveRows, setLiveRows] = useState<Signal[] | null>(null);

  useEffect(() => {
    if (mocks) return;
    let alive = true;
    fetchSignals({
      symbol: symbolFilter === "all" ? undefined : symbolFilter,
      setup_type: typeFilter === "all" ? undefined : typeFilter,
      status: statusFilter === "all" ? undefined : statusFilter,
      from_ts: dayStart(fromDay) ?? undefined,
      to_ts: dayEnd(toDay) ?? undefined,
      limit: 80,
    }).then((list) => {
      if (!alive || !list) return;
      setLiveRows(list.items);
    });
    return () => {
      alive = false;
    };
  }, [mocks, symbolFilter, typeFilter, statusFilter, fromDay, toDay]);

  const filtered = useMemo(() => {
    const source = !mocks && liveRows ? liveRows : rows;
    if (!mocks && liveRows) return source;
    const from = dayStart(fromDay);
    const to = dayEnd(toDay);
    return source.filter((r) => {
      if (typeFilter !== "all" && r.setup_type !== typeFilter) return false;
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      if (symbolFilter !== "all" && r.symbol !== symbolFilter) return false;
      if (from != null && r.ts_ms < from) return false;
      if (to != null && r.ts_ms > to) return false;
      return true;
    });
  }, [mocks, rows, liveRows, typeFilter, statusFilter, symbolFilter, fromDay, toDay]);

  const download = () => {
    const blob = new Blob([toCsv(filtered)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "signals.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="sec" aria-label="Signal history">
      <div className="sec-head">
        <span className="ix">P2</span>
        <h2>Signal History</h2>
        <span className="sim">GET /signals</span>
      </div>
      <div className="sec-sub">
        Same <code>GET /signals</code> as the live table (<code>from_ts</code>/<code>to_ts</code>,{" "}
        <code>status</code>, <code>setup_type</code>, <code>symbol</code>). Close fields{" "}
        <code>realized_r</code>, <code>exit_price</code>, <code>closed_ts_ms</code> come from Quant
        PR #2 (null on ACTIVE/CANCELLED; set on TP_HIT/SL_HIT). Not computed here.
      </div>
      <div className="table-tools" style={{ marginBottom: 10 }}>
        <select value={symbolFilter} onChange={(e) => setSymbolFilter(e.target.value)}>
          <option value="all">all symbol</option>
          {SYMBOLS.map((s) => (
            <option key={s.symbol} value={s.symbol}>
              {s.symbol}
            </option>
          ))}
        </select>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as SetupType | "all")}>
          <option value="all">all setup_type</option>
          {SETUP_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as SignalStatus | "all")}
        >
          <option value="all">all status</option>
          {SIGNAL_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <label className="hist-date">
          from
          <input type="date" value={fromDay} onChange={(e) => setFromDay(e.target.value)} />
        </label>
        <label className="hist-date">
          to
          <input type="date" value={toDay} onChange={(e) => setToDay(e.target.value)} />
        </label>
        <button type="button" onClick={download}>
          CSV
        </button>
        <button type="button" onClick={onToggleSound}>
          sound {soundOn ? "on" : "off"}
        </button>
        <span className="qep-name">{filtered.length} rows</span>
      </div>
      <div className="qep-wrap">
        <table className="qep-table hist-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Symbol</th>
              <th>Pattern Type</th>
              <th>Direction</th>
              <th>Zone</th>
              <th>Outcome</th>
              <th>realized_r</th>
              <th>exit_price</th>
              <th>closed_ts_ms</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="note">
                  Waiting for Signal frames…
                </td>
              </tr>
            )}
            {filtered.map((row) => {
              const rMult = realizedMultiple(row);
              return (
                <tr
                  key={row.id}
                  className={`qep-row${selectedId === row.id ? " sel" : ""}`}
                  onClick={() => onSelect(row)}
                >
                  <td className="mono">{utcStamp(row.ts_ms)}</td>
                  <td className="qep-tk">{row.symbol}</td>
                  <td className="mono">{row.setup_type}</td>
                  <td>
                    <span className={`qep-sig ${row.side === "long" ? "buy" : "sell"}`}>
                      {row.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="mono zone-cell">{zoneLabel(row)}</td>
                  <td>
                    <span className={`badge badge-${row.status}`}>{outcomeLabel(row)}</span>
                  </td>
                  <td className="mono" data-field="realized_r">
                    {rMult != null ? rMult.toFixed(2) : "—"}
                  </td>
                  <td className="mono" data-field="exit_price">
                    {row.exit_price != null ? row.exit_price.toFixed(2) : "—"}
                  </td>
                  <td className="mono" data-field="closed_ts_ms">
                    {row.closed_ts_ms != null ? utcStamp(row.closed_ts_ms) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
