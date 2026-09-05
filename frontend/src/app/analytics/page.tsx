"use client";

import { useMemo, useRef, useState } from "react";
import { PageShell } from "@/components/terminal/PageShell";
import { PerformanceTracker } from "@/components/terminal/PerformanceTracker";
import { usePerformance } from "@/hooks/usePerformance";
import { PERFORMANCE_SETUP_KEYS } from "@/lib/constants";

type Window = "daily" | "weekly" | "monthly";

function winPct(n: number): number {
  return n > 1 ? n : n * 100;
}

export default function AnalyticsPage() {
  const summary = usePerformance();
  const [window, setWindow] = useState<Window>("weekly");
  const chartRef = useRef<HTMLDivElement>(null);
  const rows = PERFORMANCE_SETUP_KEYS.map((key) => ({
    key,
    m: summary.by_setup[key],
  }));
  const maxSignals = Math.max(1, ...rows.map((r) => (window === "daily" ? r.m?.signals_today : r.m?.signals_week) ?? 0));
  const pnl = useMemo(() => stubPnl(window), [window]);

  const exportCsv = () => {
    const header = "setup,win_rate,average_rr,sharpe_ratio,max_drawdown_pct,signals_today,signals_week";
    const lines = rows.map((r) =>
      [
        r.key,
        r.m?.win_rate ?? "",
        r.m?.average_rr ?? "",
        r.m?.sharpe_ratio ?? "",
        r.m?.max_drawdown_pct ?? "",
        r.m?.signals_today ?? "",
        r.m?.signals_week ?? "",
      ].join(","),
    );
    const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "performance_summary.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const exportPng = async () => {
    const node = chartRef.current;
    if (!node) return;
    const svg = node.querySelector("svg");
    if (!svg) return;
    const blob = new Blob([new XMLSerializer().serializeToString(svg)], { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "performance_charts.svg";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <PageShell>
      <div className="hero">
        <h1>
          Performance <span className="tag">Analytics</span>
        </h1>
        <p className="hero-sub">
          GET /performance/summary — indexed by product keys. Time window filters scale the mock P&amp;L
          stub only; the API has no equity-curve field.
        </p>
      </div>
      <div className="filters">
        {(["daily", "weekly", "monthly"] as const).map((w) => (
          <button key={w} type="button" className={`ftab${window === w ? " active" : ""}`} onClick={() => setWindow(w)}>
            {w}
          </button>
        ))}
        <button type="button" className="btn" onClick={exportCsv}>
          CSV
        </button>
        <button type="button" className="btn" onClick={exportPng}>
          PNG/SVG
        </button>
      </div>
      <div className="qstats">
        <div className="qstat">
          <div className="ql">win_rate</div>
          <div className="qv pos">{winPct(summary.overall.win_rate).toFixed(0)}%</div>
        </div>
        <div className="qstat">
          <div className="ql">average_rr</div>
          <div className="qv cy">{summary.overall.average_rr.toFixed(2)}</div>
        </div>
        <div className="qstat">
          <div className="ql">sharpe_ratio</div>
          <div className="qv gold">{summary.overall.sharpe_ratio.toFixed(2)}</div>
        </div>
        <div className="qstat">
          <div className="ql">max_drawdown_pct</div>
          <div className="qv">{summary.overall.max_drawdown_pct.toFixed(1)}%</div>
        </div>
      </div>
      <div className="grid-2" ref={chartRef}>
        <div className="panel">
          <b>signals per setup</b>
          <div className="bar-list">
            {rows.map((r) => {
              const n = (window === "daily" ? r.m?.signals_today : r.m?.signals_week) ?? 0;
              return (
                <div key={r.key} className="bar-row">
                  <span className="bar-lab">{r.key}</span>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${(n / maxSignals) * 100}%` }} />
                  </div>
                  <span className="bar-n">{n}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="panel">
          <b>win_rate by setup</b>
          <div className="bar-list">
            {rows.map((r) => {
              const n = winPct(r.m?.win_rate ?? 0);
              return (
                <div key={r.key} className="bar-row">
                  <span className="bar-lab">{r.key}</span>
                  <div className="bar-track">
                    <div className="bar-fill gold" style={{ width: `${n}%` }} />
                  </div>
                  <span className="bar-n">{n.toFixed(0)}%</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 14 }}>
        <PerformanceTracker summary={summary} />
      </div>
      <div className="panel" style={{ marginTop: 14 }}>
        <b>Cumulative P&amp;L</b>
        <span className="sim">stub — not an API field</span>
        <svg viewBox="0 0 320 80" className="pnl-svg" role="img" aria-label="stub pnl">
          <polyline fill="none" stroke="var(--emerald)" strokeWidth="2" points={pnl} />
        </svg>
      </div>
    </PageShell>
  );
}

function stubPnl(window: Window): string {
  const seed = window === "daily" ? 8 : window === "weekly" ? 16 : 28;
  const pts: string[] = [];
  let y = 50;
  for (let i = 0; i < seed; i++) {
    y -= (i % 3 === 0 ? -4 : 3) * (window === "monthly" ? 0.6 : 1);
    pts.push(`${(i / (seed - 1)) * 320},${Math.min(70, Math.max(10, y))}`);
  }
  return pts.join(" ");
}
