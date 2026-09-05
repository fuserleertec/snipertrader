"use client";

import { useMemo, useState } from "react";
import { SETUP_TYPES, SIGNAL_STATUSES } from "@/lib/constants";
import { riskReward, zoneLabel } from "@/lib/signals";
import type { SetupType, Signal, SignalStatus } from "@/lib/types";

function utcStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
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
  const [typeFilter, setTypeFilter] = useState<SetupType | "all">("all");
  const [statusFilter, setStatusFilter] = useState<SignalStatus | "all">("all");

  const filtered = useMemo(
    () =>
      rows.filter(
        (r) =>
          (typeFilter === "all" || r.setup_type === typeFilter) &&
          (statusFilter === "all" || r.status === statusFilter),
      ),
    [rows, typeFilter, statusFilter],
  );

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
    <section className="signal-panel">
      <header>
        <h3>Signal history</h3>
        <div className="table-tools">
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
          <button type="button" onClick={download}>
            CSV
          </button>
          <button type="button" onClick={onToggleSound}>
            sound {soundOn ? "on" : "off"}
          </button>
          <span>{filtered.length} rows</span>
        </div>
      </header>
      <div className="signal-scroll">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Symbol</th>
              <th>Pattern Type</th>
              <th>Direction</th>
              <th>Zone</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  Waiting for Signal frames…
                </td>
              </tr>
            )}
            {filtered.map((row) => (
              <tr
                key={row.id}
                className={selectedId === row.id ? "row-selected" : ""}
                onClick={() => onSelect(row)}
              >
                <td className="mono">{utcStamp(row.ts_ms)}</td>
                <td className="mono">{row.symbol}</td>
                <td className="mono">{row.setup_type}</td>
                <td className={row.side === "long" ? "dir-up" : "dir-down"}>{row.side}</td>
                <td className="mono zone-cell">
                  {zoneLabel(row)} · R {riskReward(row).toFixed(2)}
                </td>
                <td>
                  <span className={`badge badge-${row.status}`}>{row.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
