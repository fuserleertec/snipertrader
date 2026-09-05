"use client";

import { PERFORMANCE_SETUP_KEYS } from "@/lib/constants";
import type { PerformanceMetrics, PerformanceSummary } from "@/lib/types";

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

function cells(m: Partial<PerformanceMetrics> | undefined) {
  return {
    win: pct(m?.win_rate),
    rr: num(m?.average_rr),
    sharpe: num(m?.sharpe_ratio),
    dd: m?.max_drawdown_pct != null ? `${num(m.max_drawdown_pct, 1)}%` : "—",
    today: count(m?.signals_today),
    week: count(m?.signals_week),
  };
}

export function PerformanceTracker({ summary }: { summary: PerformanceSummary }) {
  const overall = cells(summary.overall);
  return (
    <div className="panel perf-panel">
      <div className="perf-head">
        <b>Performance tracker</b>
        <span className="sim">GET /performance/summary</span>
      </div>
      <div className="sec-sub" style={{ marginBottom: 10 }}>
        Mock until Quant confirms the live path. <code>by_setup</code> keys are shown as-is — no
        invented labels for <code>3</code>–<code>6</code>.
      </div>
      <div className="qep-wrap">
        <table className="qep-table perf-table">
          <thead>
            <tr>
              <th>setup</th>
              <th>win_rate</th>
              <th>average_rr</th>
              <th>sharpe_ratio</th>
              <th>max_drawdown_pct</th>
              <th>signals_today</th>
              <th>signals_week</th>
            </tr>
          </thead>
          <tbody>
            <tr className="qep-row">
              <td>
                <div className="qep-tk">overall</div>
              </td>
              <td className="qep-price">{overall.win}</td>
              <td className="qep-price">{overall.rr}</td>
              <td className="qep-price">{overall.sharpe}</td>
              <td className="qep-price">{overall.dd}</td>
              <td className="qep-price">{overall.today}</td>
              <td className="qep-price">{overall.week}</td>
            </tr>
            {PERFORMANCE_SETUP_KEYS.map((key) => {
              const row = cells(summary.by_setup[key]);
              return (
                <tr key={key} className="qep-row">
                  <td>
                    <div className="qep-tk">{key}</div>
                  </td>
                  <td className="qep-price">{row.win}</td>
                  <td className="qep-price">{row.rr}</td>
                  <td className="qep-price">{row.sharpe}</td>
                  <td className="qep-price">{row.dd}</td>
                  <td className="qep-price">{row.today}</td>
                  <td className="qep-price">{row.week}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
