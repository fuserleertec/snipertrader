"use client";

import { PERFORMANCE_SETUP_KEYS } from "@/lib/constants";
import type { PerformanceSetupStats, PerformanceSummary } from "@/lib/types";

function pct(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const v = n > 1 ? n : n * 100;
  return `${v.toFixed(0)}%`;
}

function num(n: number | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function count(n: number | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return String(n);
}

export function PerformanceTracker({ summary }: { summary: PerformanceSummary }) {
  const o = summary.overall;
  return (
    <div className="panel perf-panel">
      <div className="perf-head">
        <b>Performance tracker</b>
        <span className="sim">
          {summary.source === "live" ? "LIVE :8001" : "MOCK FALLBACK"}
        </span>
      </div>
      <div className="sec-sub" style={{ marginBottom: 10 }}>
        Quant PR #2 <code>GET /performance/summary</code>. <code>by_setup</code> keys are product
        strings. Counts use <code>n_signals</code>.
      </div>
      <div className="qstats" style={{ marginBottom: 12 }}>
        <div className="qstat">
          <div className="ql">win_rate</div>
          <div className="qv pos">{pct(o.win_rate)}</div>
        </div>
        <div className="qstat">
          <div className="ql">average_rr</div>
          <div className="qv cy">{num(o.average_rr)}</div>
        </div>
        <div className="qstat">
          <div className="ql">sharpe_ratio</div>
          <div className="qv gold">{num(o.sharpe_ratio)}</div>
        </div>
        <div className="qstat">
          <div className="ql">max_drawdown_pct</div>
          <div className="qv">{num(o.max_drawdown_pct, 1)}%</div>
        </div>
        <div className="qstat">
          <div className="ql">signals today / week</div>
          <div className="qv">
            {count(o.signals_today)}
            <span style={{ color: "var(--dim2)", fontSize: 13 }}> / {count(o.signals_week)}</span>
          </div>
        </div>
      </div>
      <div className="qep-wrap">
        <table className="qep-table perf-table">
          <thead>
            <tr>
              <th>setup</th>
              <th>win_rate</th>
              <th>average_rr</th>
              <th>signals</th>
            </tr>
          </thead>
          <tbody>
            {PERFORMANCE_SETUP_KEYS.map((key) => {
              const row: PerformanceSetupStats | undefined = summary.by_setup[key];
              return (
                <tr key={key} className="qep-row">
                  <td>
                    <div className="qep-tk">{key}</div>
                  </td>
                  <td className="qep-price">{pct(row?.win_rate)}</td>
                  <td className="qep-price">{num(row?.average_rr)}</td>
                  <td className="qep-price">{count(row?.signals)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
