"use client";

import { zoneLabel } from "@/lib/signals";
import type { Signal } from "@/lib/types";

function utcStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

export function SignalTable({ rows }: { rows: Signal[] }) {
  return (
    <section className="signal-panel">
      <header>
        <h3>Signals</h3>
        <span>{rows.length} live</span>
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
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  Waiting for Signal frames…
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="mono">{utcStamp(row.ts_ms)}</td>
                <td className="mono">{row.symbol}</td>
                <td className="mono">{row.setup_type}</td>
                <td className={row.side === "long" ? "dir-up" : "dir-down"}>{row.side}</td>
                <td className="mono zone-cell">{zoneLabel(row)}</td>
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
