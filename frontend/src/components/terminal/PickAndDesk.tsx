"use client";

import { useMemo, useState } from "react";
import { RECON_AUDIT_LIMIT } from "@/lib/constants";
import { capReconAudit } from "@/lib/desk";
import {
  GLOSSARY,
  NARRATIVES,
  convictionOf,
  reconFromCategorized,
  simScenario,
} from "@/lib/mocks/terminal";
import type { CategorizedPickItem, PerformanceSummary, Signal } from "@/lib/types";
import { PerformanceTracker } from "./PerformanceTracker";

const CAT = {
  ultra: { label: "Ultra-High", accent: "var(--emerald)" },
  high: { label: "High", accent: "var(--cyan)" },
  watch: { label: "Watchlist", accent: "var(--gold)" },
};

export function PickGrid({
  signals,
  selectedId,
  onSelect,
  onOpenChart,
  onSelectSymbol,
  categorized,
}: {
  signals: Signal[];
  selectedId: string | null;
  onSelect: (s: Signal) => void;
  onOpenChart: (s: Signal) => void;
  onSelectSymbol?: (symbol: string) => void;
  categorized: CategorizedPickItem[];
}) {
  const [filter, setFilter] = useState<"all" | "ultra" | "high" | "watch">("all");
  const rows = useMemo(() => {
    const fromApi = categorized.slice(0, 20).map(reconFromCategorized);
    return fromApi.filter((p) => filter === "all" || p.tier === filter);
  }, [categorized, filter]);

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">04</span>
        <h2>Categorized Stock Picks</h2>
      </div>
      <div className="sec-sub">
        Multi-cap grid from <code>GET /picks/categorized</code> (≤20 symbols, no asset-class cap). Each card
        appends a <span className="sim">Simulation</span> scenario cone derived from ATR + conviction. Click
        CHART to plot that symbol.
      </div>
      <div className="filters">
        {(["all", "ultra", "high", "watch"] as const).map((f) => (
          <button key={f} type="button" className={`ftab${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>
            {f === "all" ? "All" : f === "ultra" ? "Ultra-High" : f === "high" ? "High" : "Watchlist"}
          </button>
        ))}
      </div>
      <div className="pick-grid">
        {rows.map((p, i) => {
          const c = CAT[p.tier];
          const sc = simScenario(p.score, p.atr, p.entry);
          const sig = signals.find((s) => s.id === p.note || (s.symbol === p.symbol && s.status === "ACTIVE"));
          return (
            <div key={`${p.symbol}-${i}`} className={`pick${selectedId && sig?.id === selectedId ? " selected" : ""}`} style={{ ["--accent" as string]: c.accent }}>
              <div className="pick-top">
                <div>
                  <div className="pick-tk">{p.symbol}</div>
                  <div className="pick-name">
                    {p.cap.toUpperCase()} · score {p.score.toFixed(0)}/100
                  </div>
                </div>
                <div className="pick-cat">{c.label}</div>
              </div>
              <div className="pick-thesis">{p.note}</div>
              <div className="pick-tags">
                {p.triggers.map((t) => (
                  <span key={t} className="ptag">
                    {t}
                  </span>
                ))}
              </div>
              <div className="scen-mini">
                <div className="sm bull">
                  <div className="sl">Bull {sc.bull.p}%</div>
                  <div className="sv">+{sc.bull.r.toFixed(1)}%</div>
                </div>
                <div className="sm">
                  <div className="sl">Base {sc.base.p}%</div>
                  <div className="sv">+{sc.base.r.toFixed(1)}%</div>
                </div>
                <div className="sm bear">
                  <div className="sl">Bear {sc.bear.p}%</div>
                  <div className="sv">{sc.bear.r.toFixed(1)}%</div>
                </div>
              </div>
              <div className="pick-metrics">
                <div className="pm">
                  <div className="pk">Entry</div>
                  <div className="pv cy">${p.entry.toFixed(2)}</div>
                </div>
                <div className="pm">
                  <div className="pk">Target</div>
                  <div className="pv pos">${p.target.toFixed(2)}</div>
                </div>
                <div className="pm">
                  <div className="pk">Stop</div>
                  <div className="pv neu">${p.stop.toFixed(2)}</div>
                </div>
                <div className="pm">
                  <div className="pk">R:R</div>
                  <div className="pv" style={{ color: c.accent }}>
                    {p.rewardRisk.toFixed(1)}
                  </div>
                </div>
              </div>
              <div className="pick-btns">
                <button
                  type="button"
                  className="tv-btn"
                  onClick={() => {
                    onSelectSymbol?.(p.symbol);
                    if (sig) onOpenChart(sig);
                  }}
                >
                  📈 CHART
                </button>
                <button type="button" className="sim-btn" onClick={() => sig && onSelect(sig)}>
                  🎲 SIMULATE
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function Narratives() {
  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">05</span>
        <h2>Narrative &amp; Volatility Injectors</h2>
        <span className="sim">Illustrative</span>
      </div>
      <div className="sec-sub">
        Example macro narratives that would shift swarm behavior. <b>Static/illustrative</b> — not a live
        news feed.
      </div>
      <div className="narr">
        {NARRATIVES.map((n) => (
          <div key={n.title} className="ncard">
            <div className="nh">
              <span className="ni">{n.icon}</span>
              {n.title}
            </div>
            <div className="nr">
              <b>{n.impact}</b>
              <div>{n.body}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}


export function ReconAudit({
  dropped,
  audit,
}: {
  dropped: Signal[];
  audit?: CategorizedPickItem[];
}) {
  const extras = dropped.map((s) => ({
    key: s.id,
    symbol: s.symbol,
    score: convictionOf(s),
    reason: `${s.setup_type} ${s.status} — conviction ${convictionOf(s)} below 65 watchlist floor.`,
  }));
  const seen = new Set(extras.map((e) => e.symbol));
  const base = (audit ?? []).filter((d) => !seen.has(d.symbol)).map((d) => ({
    key: d.symbol,
    symbol: d.symbol,
    score: d.score,
    reason: reconFromCategorized(d).note,
  }));
  const rows = capReconAudit([...base, ...extras]);
  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">07</span>
        <h2>Recon Audit — Dropped This Cycle</h2>
      </div>
      <div className="sec-sub">
        Transparency: scanned names below the 65 watchlist floor this cycle (max {RECON_AUDIT_LIMIT}
        symbols).
      </div>
      <div className="recon-grid">
        {rows.length === 0 && <div className="note">No drops this cycle.</div>}
        {rows.map((s) => (
          <div key={s.key} className="drop">
            <div className="dt">
              <div className="dsym">{s.symbol}</div>
              <div className="dbull">{s.score}</div>
            </div>
            <div className="dreason">{s.reason}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function EngineGlossary({ performance }: { performance: PerformanceSummary }) {
  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">08</span>
        <h2>Understanding the Engine</h2>
      </div>
      <div className="sec-sub">
        Built-in glossary and a performance tracker wired to Quant{" "}
        <code>GET /performance/summary</code> (<code>:8001</code>) with mock fallback.
      </div>
      <PerformanceTracker summary={performance} />
      <div className="edu-grid" style={{ marginTop: 14 }}>
        {GLOSSARY.map((g) => (
          <div key={g.title} className="edu">
            <h4>{g.title}</h4>
            <p>{g.body}</p>
            <div className="perf">
              <b>{g.perf}</b>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
