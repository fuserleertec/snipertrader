"use client";

import { useMemo, useState } from "react";
import { GLOSSARY, NARRATIVES, convictionOf, scenarioCones, tierOf, whyForSetup } from "@/lib/mocks/terminal";
import { riskReward } from "@/lib/signals";
import type { Signal } from "@/lib/types";

function fmt(n: number): string {
  return n >= 1000 ? n.toFixed(1) : n.toFixed(2);
}

export function PickGrid({
  signals,
  selectedId,
  onSelect,
  onOpenChart,
}: {
  signals: Signal[];
  selectedId: string | null;
  onSelect: (s: Signal) => void;
  onOpenChart: (s: Signal) => void;
}) {
  const [filter, setFilter] = useState<"all" | "ultra" | "high" | "watch">("all");
  const rows = useMemo(
    () =>
      signals.filter((s) => {
        const t = tierOf(convictionOf(s));
        if (t === "drop") return false;
        return filter === "all" || t === filter;
      }),
    [signals, filter],
  );

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">04</span>
        <h2>Categorized Stock Picks</h2>
      </div>
      <div className="sec-sub">
        Multi-cap grid from the Conviction Engine. Each card appends a <span className="sim">Simulation</span>{" "}
        scenario cone. Click a card to open the Kronos chart and highlight overlays.
      </div>
      <div className="filters">
        {(["all", "ultra", "high", "watch"] as const).map((f) => (
          <button key={f} type="button" className={`ftab${filter === f ? " active" : ""}`} onClick={() => setFilter(f)}>
            {f === "all" ? "All" : f === "ultra" ? "Ultra-High" : f === "high" ? "High" : "Watchlist"}
          </button>
        ))}
      </div>
      <div className="pick-grid">
        {rows.map((s) => {
          const conv = convictionOf(s);
          const cones = scenarioCones(conv, s.side);
          const accent = s.side === "long" ? "var(--emerald)" : "var(--red)";
          return (
            <button
              key={s.id}
              type="button"
              className={`pick${selectedId === s.id ? " selected" : ""}`}
              style={{ ["--accent" as string]: accent }}
              onClick={() => onSelect(s)}
            >
              <div className="pick-top">
                <div>
                  <div className="pick-tk">{s.symbol}</div>
                  <div className="pick-name">{s.setup_type}</div>
                </div>
                <div className="pick-cat">{tierOf(conv).toUpperCase()}</div>
              </div>
              <div className="pick-thesis">{whyForSetup(s)}</div>
              <div className="pick-tags">
                <span className="ptag">{s.side.toUpperCase()}</span>
                <span className="ptag">{s.status}</span>
                <span className="ptag">{conv}% conv</span>
              </div>
              <div className="pick-metrics">
                <div className="pm">
                  <div className="pk">entry</div>
                  <div className="pv">{fmt(s.entry)}</div>
                </div>
                <div className="pm">
                  <div className="pk">stop</div>
                  <div className="pv">{fmt(s.stop)}</div>
                </div>
                <div className="pm">
                  <div className="pk">target</div>
                  <div className="pv">{fmt(s.target)}</div>
                </div>
                <div className="pm">
                  <div className="pk">R:R</div>
                  <div className="pv">{riskReward(s).toFixed(2)}</div>
                </div>
              </div>
              <div className="scen-mini">
                <div className="sm bull">
                  <div className="sl">Bull</div>
                  <div className="sv">{cones.bull}%</div>
                </div>
                <div className="sm">
                  <div className="sl">Base</div>
                  <div className="sv">{cones.base}%</div>
                </div>
                <div className="sm bear">
                  <div className="sl">Bear</div>
                  <div className="sv">{cones.bear}%</div>
                </div>
              </div>
              <div className="pick-btns">
                <span
                  className="tv-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenChart(s);
                  }}
                >
                  📈 CHART
                </span>
                <span className="sim-btn">🎲 SIM</span>
              </div>
            </button>
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

export function ExecutionDesk({ selected }: { selected: Signal | null }) {
  const conv = selected ? convictionOf(selected) : 0;
  const equity = 25000;
  const risk = selected ? Math.abs(selected.entry - selected.stop) : 0;
  const rr = selected ? riskReward(selected) : 0;
  const alloc = Math.min(12, conv / 10);
  const pos = (equity * alloc) / 100;
  const shares = selected && selected.entry ? Math.floor(pos / selected.entry) : 0;
  const riskDollars = shares * risk;
  const tier = conv >= 88 ? "ULTRA" : conv >= 78 ? "HIGH" : conv >= 65 ? "WATCH" : "—";
  const tech = selected ? (selected.setup_type.includes("fvg") || selected.setup_type.includes("ob") ? 80 : 60) : 0;
  const vol = selected && selected.confidence > 0.8 ? 100 : 50;
  const cat = selected ? 50 : 0;
  const insider = 0;

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">06</span>
        <h2>Execution &amp; Position Management</h2>
      </div>
      <div className="sec-sub">
        Fractional-Kelly sizing + hard guardrails from the Conviction Engine. Weights: Insider 0.30 ·
        Technical 0.30 · Volume 0.20 · Catalyst 0.20.
      </div>
      <div className="calc-grid">
        <div className="panel score-card">
          <div className="score-big">{conv}</div>
          <div className="score-bar">
            <div className="score-fill" style={{ width: `${conv}%`, background: "linear-gradient(90deg,var(--gold),var(--emerald))" }} />
          </div>
          <div className="score-ticks">
            <span>0</span>
            <span>65 WATCH</span>
            <span>78 HIGH</span>
            <span>88 ULTRA</span>
            <span>100</span>
          </div>
          <div className="tier-badge">{tier}</div>
        </div>
        <div className="panel">
          <div className="factor">
            <div className="flabel">
              <span>Technical Proof</span>
              <b>{tech}</b>
            </div>
          </div>
          <div className="factor">
            <div className="flabel">
              <span>Insider / Political</span>
              <b>{insider}</b>
            </div>
          </div>
          <div className="factor">
            <div className="flabel">
              <span>Volume Surge</span>
              <b>{vol}</b>
            </div>
          </div>
          <div className="factor">
            <div className="flabel">
              <span>Catalyst / DD</span>
              <b>{cat}</b>
            </div>
          </div>
          <div className="params">
            <div className="factor" style={{ margin: 0 }}>
              <label style={{ fontSize: 11, color: "var(--dim2)" }}>Equity ($)</label>
              <input readOnly value={equity} />
            </div>
            <div className="factor" style={{ margin: 0 }}>
              <label style={{ fontSize: 11, color: "var(--dim2)" }}>Entry ($)</label>
              <input readOnly value={selected ? fmt(selected.entry) : "—"} />
            </div>
          </div>
          <div className="alloc-out">
            <div className="ao">
              <div className="ak">Allocation</div>
              <div className="av">{alloc.toFixed(1)}%</div>
            </div>
            <div className="ao">
              <div className="ak">Position $</div>
              <div className="av">${pos.toFixed(0)}</div>
            </div>
            <div className="ao">
              <div className="ak">Shares</div>
              <div className="av">{shares}</div>
            </div>
            <div className="ao">
              <div className="ak">Risk $</div>
              <div className="av">${riskDollars.toFixed(0)}</div>
            </div>
            <div className="ao">
              <div className="ak">Target</div>
              <div className="av">{selected ? fmt(selected.target) : "—"}</div>
            </div>
            <div className="ao">
              <div className="ak">R:R</div>
              <div className="av">{rr ? rr.toFixed(2) : "—"}</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function ReconAudit({ dropped }: { dropped: Signal[] }) {
  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">07</span>
        <h2>Recon Audit — Dropped This Cycle</h2>
      </div>
      <div className="sec-sub">
        Transparency: every scanned name that fell below the 65 watchlist floor, with the reason it
        failed.
      </div>
      <div className="recon-grid">
        {dropped.length === 0 && <div className="note">No drops this cycle.</div>}
        {dropped.map((s) => (
          <div key={s.id} className="drop">
            <div className="dt">
              <div className="dsym">{s.symbol}</div>
              <div className="dbull">{convictionOf(s)}</div>
            </div>
            <div className="dreason">
              {s.setup_type} {s.status} — conviction {convictionOf(s)} below 65 watchlist floor.
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function EngineGlossary() {
  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">08</span>
        <h2>Understanding the Engine</h2>
      </div>
      <div className="sec-sub">
        Built-in glossary and an illustrative performance tracker. Tracker figures are
        example/backtest-style placeholders, not verified live results.
      </div>
      <div className="edu-grid">
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
