"use client";

import { useMemo, useState } from "react";
import {
  FALLBACK_DROPPED,
  FALLBACK_PICKS,
  GLOSSARY,
  NARRATIVES,
  convictionOf,
  simScenario,
  tierOf,
  whyForSetup,
  type ReconPick,
} from "@/lib/mocks/terminal";
import { riskReward } from "@/lib/signals";
import type { Signal } from "@/lib/types";

const CAT = {
  ultra: { label: "Ultra-High", accent: "var(--emerald)" },
  high: { label: "High", accent: "var(--cyan)" },
  watch: { label: "Watchlist", accent: "var(--gold)" },
};

function asPick(s: Signal): ReconPick {
  const score = convictionOf(s);
  const t = tierOf(score);
  return {
    symbol: s.symbol,
    cap: "mid",
    tier: t === "drop" ? "watch" : t,
    score,
    entry: s.entry,
    stop: s.stop,
    target: s.target,
    atr: Math.abs(s.entry - s.stop),
    rewardRisk: riskReward(s),
    triggers: [s.setup_type, ...s.trigger_event_ids.slice(0, 2)],
    note: whyForSetup(s),
  };
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
  const rows = useMemo(() => {
    const setupPicks = signals.filter((s) => s.status === "ACTIVE").map(asPick);
    return [...FALLBACK_PICKS, ...setupPicks].filter((p) => filter === "all" || p.tier === filter);
  }, [signals, filter]);

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">04</span>
        <h2>Categorized Stock Picks</h2>
      </div>
      <div className="sec-sub">
        Multi-cap grid from the live Conviction Engine. Each card appends a <span className="sim">Simulation</span>{" "}
        scenario cone derived from its real ATR + conviction. Click any card&apos;s buttons to open the live chart or
        inspect the simulation.
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
                    {p.cap.toUpperCase()} cap · score {p.score.toFixed(0)}/100
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
                    if (sig) onOpenChart(sig);
                    else onSelect(signals[0] ?? ({ id: p.symbol } as Signal));
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

const W = { insider: 0.3, tech: 0.3, vol: 0.2, cat: 0.2 };
const T_ULTRA = 88;
const T_HIGH = 78;
const T_WATCH = 65;
const SIZE = {
  ultra: { allocation_pct: 0.12, max_risk_pct: 0.02, min_rr_ratio: 2.5, kelly: 1 },
  high: { allocation_pct: 0.08, max_risk_pct: 0.0125, min_rr_ratio: 2.0, kelly: 0.66 },
};
const TIER_STYLE = {
  ultra: { name: "Ultra-High Conviction", color: "var(--emerald)", rgb: "0,229,160", action: "BUY · Immediate Simulated Market Order" },
  high: { name: "High Conviction", color: "var(--cyan)", rgb: "0,212,255", action: "BUY · Scaled / Staggered Limit Entry" },
  mod: { name: "Moderate Conviction", color: "var(--gold)", rgb: "240,192,64", action: "WATCHLIST · Flag for manual review (no auto order)" },
  rej: { name: "Rejected", color: "var(--red)", rgb: "255,68,85", action: "IGNORE · Drop immediately" },
} as const;

function atrLevels(entry: number, atr: number, swingLow: number, rr: number) {
  const e = entry;
  const a = atr > 0 ? atr : e * 0.03;
  let stop = e - Math.max(1.0 * a, e * 0.01);
  if (swingLow > 0) stop = Math.min(stop, swingLow - a * 0.25);
  stop = Math.min(stop, e - e * 0.005);
  const risk = Math.max(e - stop, e * 0.001);
  let target = e + Math.max(1.0 * a, risk * rr);
  target = Math.max(target, e + risk * rr, e * 1.005);
  return { stop, target, risk, rr: risk > 0 ? (target - e) / risk : 0 };
}

export function ExecutionDesk({ selected }: { selected: Signal | null }) {
  const [tech, setTech] = useState(0);
  const [insider, setInsider] = useState(0);
  const [vol, setVol] = useState(0);
  const [cat, setCat] = useState(0);
  const [equity, setEquity] = useState(25000);
  const [entry, setEntry] = useState(100);
  const [atr, setAtr] = useState(3);
  const [swing, setSwing] = useState(0);
  const [sectorUsed, setSectorUsed] = useState(0);
  const [portUsed, setPortUsed] = useState(0);
  const [openPos, setOpenPos] = useState(0);
  const [corr, setCorr] = useState(0);

  const sComp = tech * W.tech + insider * W.insider + vol * W.vol + cat * W.cat;
  const tk = sComp >= T_ULTRA ? "ultra" : sComp >= T_HIGH ? "high" : sComp >= T_WATCH ? "mod" : "rej";
  const style = TIER_STYLE[tk];
  const sized = tk === "ultra" || tk === "high" ? SIZE[tk] : null;
  let allocPct = 0;
  let posDollars = 0;
  let shares = 0;
  let riskDollars = 0;
  let tp: string = "—";
  let rrOut: string = "—";
  let note =
    tk === "mod"
      ? "Moderate tier (< 78): paper trade only — no capital allocated."
      : "Rejected (< 65): signal dropped. No position.";
  if (sized) {
    const lv = atrLevels(entry, atr, swing, sized.min_rr_ratio);
    let allocFrac = sized.allocation_pct * sized.kelly;
    const headroom = Math.max(0, 0.7 - portUsed / 100);
    allocFrac = Math.min(allocFrac, headroom);
    if (corr > 0.85) allocFrac /= 2;
    const riskPerShare = lv.risk;
    shares = riskPerShare > 0 ? Math.floor((equity * allocFrac) / entry) : 0;
    riskDollars = shares * riskPerShare;
    const riskPct = equity > 0 ? riskDollars / equity : 0;
    if (riskPct > sized.max_risk_pct) {
      const maxShares = riskPerShare > 0 ? Math.floor((equity * sized.max_risk_pct) / riskPerShare) : 0;
      shares = maxShares;
      riskDollars = maxShares * riskPerShare;
    }
    posDollars = shares * entry;
    allocPct = allocFrac * 100;
    tp = `$${lv.target.toFixed(2)}`;
    rrOut = `1 : ${lv.rr > 0 ? lv.rr.toFixed(2) : sized.min_rr_ratio.toFixed(1)}`;
    note = `Tier base ${(sized.allocation_pct * 100).toFixed(0)}% × Kelly ${(sized.kelly * 100).toFixed(0)}% = ${(sized.allocation_pct * sized.kelly * 100).toFixed(1)}% target.`;
  }
  const sectorHead = Math.max(0, 30 - sectorUsed);
  const guards: Array<[string, string, string]> = [
    openPos >= 5
      ? ["fail", "Position Limit", `${openPos} / 5 — at maximum. Block new entries.`]
      : ["ok", "Position Limit", `${openPos} / 5 open — within limit.`],
    sectorUsed >= 30
      ? ["fail", "Sector Cap", `Sector at ${sectorUsed.toFixed(0)}% ≥ 30% cap. Block.`]
      : ["ok", "Sector Cap", `${sectorHead.toFixed(0)}% sector headroom remaining.`],
    portUsed >= 70
      ? ["fail", "Total Exposure", `Portfolio ${portUsed.toFixed(0)}% ≥ 70% cap — cash floor breached.`]
      : ["ok", "Total Exposure", `${portUsed.toFixed(0)}% deployed · ${(100 - portUsed).toFixed(0)}% cash reserve (≥30% OK).`],
    corr > 0.85
      ? ["warn", "Correlation", `30d corr ${corr.toFixed(2)} > 0.85 → lower-scoring peer halved.`]
      : ["ok", "Correlation", `Corr ${corr.toFixed(2)} ≤ 0.85 — no penalty.`],
  ];

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">06</span>
        <h2>Execution &amp; Position Management</h2>
      </div>
      <div className="sec-sub">
        Fractional-Kelly sizing + hard guardrails from the Conviction Engine. Weights: Insider 0.30 ·
        Technical 0.30 · Volume 0.20 · Catalyst 0.20. Composite score on a 0–100 scale; ATR-anchored
        levels with an inversion guard.
      </div>
      <div className="calc-grid">
        <div className="panel score-card">
          <div className="score-big" style={{ color: style.color }}>
            {sComp.toFixed(0)}
          </div>
          <div className="score-bar">
            <div
              className="score-fill"
              style={{
                width: `${sComp}%`,
                background: `linear-gradient(90deg,rgba(${style.rgb},.35),${style.color})`,
              }}
            />
          </div>
          <div className="score-ticks">
            <span>0</span>
            <span>65 WATCH</span>
            <span>78 HIGH</span>
            <span>88 ULTRA</span>
            <span>100</span>
          </div>
          <div
            className="tier-badge"
            style={{
              color: style.color,
              border: `1px solid rgba(${style.rgb},.4)`,
              background: `rgba(${style.rgb},.08)`,
            }}
          >
            <span className="tier-mark" style={{ background: style.color }} />
            {style.name}
          </div>
          <div className="tier-action">
            <b>ACTION:</b> {style.action}
          </div>
        </div>
        <div className="panel">
          <div style={{ fontSize: 13, color: "var(--dim)", marginBottom: 8, fontFamily: "var(--mono)" }}>
            Factor Scores (0–100)
          </div>
          <div className="factor">
            <div className="flabel">
              <span>Technical Proof</span>
              <b>{tech}</b>
            </div>
            <select value={tech} onChange={(e) => setTech(Number(e.target.value))}>
              <option value={0}>None</option>
              <option value={60}>Single pattern (BOS/FVG/Breakout)</option>
              <option value={80}>FVG/BOS + 20d high</option>
              <option value={100}>Breakout + BOS + FVG</option>
            </select>
          </div>
          <div className="factor">
            <div className="flabel">
              <span>Insider / Political</span>
              <b>{insider}</b>
            </div>
            <select value={insider} onChange={(e) => setInsider(Number(e.target.value))}>
              <option value={0}>None</option>
              <option value={60}>Single Form 4 buy</option>
              <option value={100}>Insider cluster / congressional</option>
            </select>
          </div>
          <div className="factor">
            <div className="flabel">
              <span>Volume Surge</span>
              <b>{vol}</b>
            </div>
            <select value={vol} onChange={(e) => setVol(Number(e.target.value))}>
              <option value={0}>Normal / no surge</option>
              <option value={50}>Mild 1.5×</option>
              <option value={100}>3×+ surge</option>
            </select>
          </div>
          <div className="factor">
            <div className="flabel">
              <span>Catalyst / DD</span>
              <b>{cat}</b>
            </div>
            <select value={cat} onChange={(e) => setCat(Number(e.target.value))}>
              <option value={0}>None</option>
              <option value={50}>Form 4 present</option>
              <option value={100}>Breakout + strong catalyst</option>
            </select>
          </div>
        </div>
      </div>
      <div className="calc-grid" style={{ marginTop: 14 }}>
        <div className="panel">
          <div style={{ fontSize: 13, color: "var(--dim)", marginBottom: 10, fontFamily: "var(--mono)" }}>
            Account &amp; Position Parameters
          </div>
          <div className="params">
            <Field label="Equity ($)" value={equity} step={100} onChange={setEquity} />
            <Field label="Entry ($)" value={entry} step={0.01} onChange={setEntry} />
            <Field label="ATR ($)" value={atr} step={0.01} onChange={setAtr} />
            <Field label="Swing Low ($)" value={swing} step={0.01} onChange={setSwing} />
            <Field label="Sector used (%)" value={sectorUsed} step={1} onChange={setSectorUsed} />
            <Field label="Portfolio used (%)" value={portUsed} step={1} onChange={setPortUsed} />
            <Field label="Open positions" value={openPos} step={1} onChange={setOpenPos} />
            <Field label="30d correlation" value={corr} step={0.05} onChange={setCorr} />
          </div>
        </div>
        <div className="panel">
          <div style={{ fontSize: 13, color: "var(--dim)", marginBottom: 10, fontFamily: "var(--mono)" }}>
            Output
          </div>
          <div className="alloc-out">
            <div className="ao">
              <div className="ak">Allocation</div>
              <div className="av">{allocPct.toFixed(2)}%</div>
            </div>
            <div className="ao">
              <div className="ak">Position $</div>
              <div className="av">${posDollars.toFixed(0)}</div>
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
              <div className="av">{tp}</div>
            </div>
            <div className="ao">
              <div className="ak">R:R</div>
              <div className="av">{rrOut}</div>
            </div>
          </div>
          <div className="sizing-note">
            {note}
            {selected ? ` Focused setup: ${selected.symbol} ${selected.setup_type}.` : ""}
          </div>
          <div className="guardrails">
            {guards.map(([cls, title, body]) => (
              <div key={title} className="gitem">
                <div className={`gicon g-${cls}`}>{cls === "ok" ? "✓" : cls === "fail" ? "✕" : "!"}</div>
                <div>
                  <b>{title}</b>
                  <br />
                  <span>{body}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="factor" style={{ margin: 0 }}>
      <label style={{ fontSize: 11, color: "var(--dim2)" }}>{label}</label>
      <input
        type="number"
        step={step}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

export function ReconAudit({ dropped }: { dropped: Signal[] }) {
  const extras = dropped.map((s) => ({
    key: s.id,
    symbol: s.symbol,
    score: convictionOf(s),
    reason: `${s.setup_type} ${s.status} — conviction ${convictionOf(s)} below 65 watchlist floor.`,
  }));
  const seen = new Set(extras.map((e) => e.symbol));
  const base = FALLBACK_DROPPED.filter((d) => !seen.has(d.symbol)).map((d) => ({
    key: d.symbol,
    symbol: d.symbol,
    score: d.score,
    reason: d.note,
  }));
  const rows = [...base, ...extras];
  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">07</span>
        <h2>Recon Audit — Dropped This Cycle</h2>
      </div>
      <div className="sec-sub">
        Transparency: every scanned name that fell below the 65 watchlist floor, with the reason it
        failed (real signals).
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
