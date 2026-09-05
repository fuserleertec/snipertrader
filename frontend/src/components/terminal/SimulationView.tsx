"use client";

import { useState } from "react";
import { OVERLAY_PRESETS, TIMEFRAMES } from "@/lib/constants";
import type { Theme } from "@/hooks/useTheme";
import {
  FALLBACK_DROPPED,
  FALLBACK_PICKS,
  scoreLeaderboard,
  simScenario,
  swarmCells,
} from "@/lib/mocks/terminal";
import type {
  OHLCVBar,
  OverlayPreset,
  PatternBook,
  SessionLevels,
  SessionType,
  Signal,
  Timeframe,
  VWAPValues,
} from "@/lib/types";
import { PriceChart } from "../PriceChart";

export function SimulationView({
  signals,
  selected,
  onSelect,
  symbol,
  onSymbol,
  timeframe,
  onTimeframe,
  overlayPreset,
  onOverlayPreset,
  bars,
  historyKey,
  lastBar,
  vwap,
  sessions,
  visibleSessions,
  theme,
  patterns,
}: {
  signals: Signal[];
  selected: Signal | null;
  onSelect: (signal: Signal) => void;
  symbol: string;
  onSymbol: (s: string) => void;
  timeframe: Timeframe;
  onTimeframe: (tf: Timeframe) => void;
  overlayPreset: OverlayPreset;
  onOverlayPreset: (p: OverlayPreset) => void;
  bars: OHLCVBar[];
  historyKey: string;
  lastBar: OHLCVBar | null;
  vwap: VWAPValues | null;
  sessions: SessionLevels[];
  visibleSessions: SessionType[];
  theme: Theme;
  patterns: PatternBook;
  lastPrice: number | null;
}) {
  const [bias, setBias] = useState(0);
  const ranked = scoreLeaderboard(FALLBACK_PICKS, FALLBACK_DROPPED);
  const focus = ranked.find((r) => r.symbol === symbol) ?? ranked[0];
  const sc = focus ? simScenario(focus.score, focus.atr, focus.entry, bias) : simScenario(70, 3, 100, bias);
  const cells = swarmCells(focus?.symbol ?? symbol, bias);
  const segs = ["Tech", "Defensive", "Cyclical", "Crypto", "Energy"];
  const droppedN = ranked.filter((r) => r.dropped).length;
  const biasLbl = bias > 0.1 ? "bullish" : bias < -0.1 ? "bearish" : "neutral";

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">03</span>
        <h2>Live Market Simulation View</h2>
        <span className="sim">Simulation</span>
      </div>
      <div className="sec-sub">
        The Recon Audit (Section 07) candidates flow through Kronos pattern detection + MiroFish swarm
        consensus and are ranked by <b>net velocity</b> — highest run-up potential at the top, highest
        dump risk at the bottom. Swarm heatmap + scenario cones are the supporting panels, driven by
        the focused ticker.
      </div>

      <div className="panel" style={{ padding: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 18 }}>📊</span>
          <b>Conviction &amp; Velocity Leaderboard</b>
          <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11, color: "var(--dim)" }}>
            {ranked.length} ranked · {droppedN} dropped
          </span>
        </div>
        <div className="lead">
          {ranked.map((it, i) => {
            const up = it.netBias >= 0;
            const accent = it.dropped ? "var(--dim2)" : up ? "var(--emerald)" : "var(--red)";
            const sig = signals.find((s) => s.symbol === it.symbol && s.status === "ACTIVE");
            return (
              <button
                key={`${it.symbol}-${i}`}
                type="button"
                className="lead-row"
                style={{ ["--accent" as string]: accent }}
                onClick={() => {
                  onSymbol(it.symbol);
                  if (sig) onSelect(sig);
                }}
              >
                <div className="lead-rank">#{i + 1}</div>
                <div className="lead-main">
                  <div className="lead-sym">
                    {it.symbol}
                    {it.dropped ? (
                      <span className="lead-pill down">DROPPED</span>
                    ) : (
                      <span className={`lead-pill ${up ? "up" : "down"}`}>
                        {up ? `RUN-UP ${it.runUpScore}` : `DUMP ${it.dumpScore}`}
                      </span>
                    )}
                  </div>
                  <div className="lead-meta">
                    {it.pattern} · Δ {it.delta.toFixed(0)}% ·{" "}
                    {it.dropped ? "no conviction · audit — no live levels" : `ATR $${it.stop.toFixed(2)} → $${it.target.toFixed(2)}`}
                  </div>
                </div>
                <div className="lead-bars">
                  <div className="lead-pbtxt">
                    <span className="b">Bull {it.sc.bull.p}%</span>
                    <span className="r">Bear {it.sc.bear.p}%</span>
                  </div>
                  <div className="lead-pbar">
                    <div className="bb" style={{ width: `${it.sc.bull.p}%` }} />
                    <div className="bn" style={{ width: `${it.sc.base.p}%` }} />
                    <div className="br" style={{ width: `${it.sc.bear.p}%` }} />
                  </div>
                </div>
                <div>
                  <div className={`lead-score ${up ? "up" : "down"}`}>
                    {up ? "+" : ""}
                    {it.netBias}
                  </div>
                  <div className="lead-sub">velocity</div>
                </div>
                <span className="tv-link" aria-hidden>
                  📈
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 14 }}>
        <div className="panel">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>🔴</span>
            <b>MiroFish Agent Swarm Activity</b>
          </div>
          <div className="heatmap" style={{ marginTop: 12 }}>
            {cells.map((c, i) => (
              <div key={i} className={`cell ${c}`} />
            ))}
          </div>
          <div className="legend">
            <span>
              <i style={{ background: "var(--emerald)" }} />
              Bullish
            </span>
            <span>
              <i style={{ background: "var(--gold)" }} />
              Neutral
            </span>
            <span>
              <i style={{ background: "var(--red)" }} />
              Bearish
            </span>
          </div>
          {segs.map((s, i) => {
            const slice = cells.filter((_, j) => j % segs.length === i);
            const pct = Math.round((slice.filter((c) => c === "bull").length / slice.length) * 100);
            return (
              <div key={s} className="ssig">
                <span className="ic">⚡</span>
                <span className="nm">{s} Sector</span>
                <span className="vl">
                  {pct}% Bullish ({slice.length} agents)
                </span>
              </div>
            );
          })}
          <div className="ssig">
            <span className="ic">📊</span>
            <span className="nm">Volume Imbalance</span>
            <span className="vl">1.7M @ ask</span>
          </div>
        </div>
        <div className="panel">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>📈</span>
            <b>
              Kronos Structural K-Line — <span>{focus?.symbol ?? symbol}</span>
            </b>
          </div>
          <div className="kr-pair" style={{ marginTop: 12 }}>
            <div>
              <div className="pat-bar">
                {(focus?.triggers.length ? focus.triggers.slice(0, 2) : ["BOS", "FVG"]).map((t, i) => {
                  const v = t.includes("BOS") ? 92 : t.includes("FVG") ? 76 : 87;
                  return (
                    <div key={`${t}-${i}`} className="pat-row">
                      <span className="pn">{t}</span>
                      <div className="pt">
                        <div className="pf" style={{ width: `${v}%` }} />
                      </div>
                      <span className="pv">{v}%</span>
                    </div>
                  );
                })}
              </div>
              <div className="kline-note">
                Next key level ≈ ${focus ? focus.target.toFixed(2) : "—"} (target zone, ATR-anchored). Scenario
                cone probabilities (simulated Monte-Carlo, 1,000 passes).
              </div>
            </div>
            <div>
              <div className="pat-row">
                <span className="pn">Bull</span>
                <div className="pt">
                  <div className="pf" style={{ width: `${sc.bull.p}%` }} />
                </div>
                <span className="pv">{sc.bull.p}%</span>
              </div>
              <div className="pat-row">
                <span className="pn">Base</span>
                <div className="pt">
                  <div className="pf" style={{ width: `${sc.base.p}%`, background: "linear-gradient(90deg,var(--gold),#b8902a)" }} />
                </div>
                <span className="pv">{sc.base.p}%</span>
              </div>
              <div className="pat-row">
                <span className="pn">Bear</span>
                <div className="pt">
                  <div className="pf" style={{ width: `${sc.bear.p}%`, background: "linear-gradient(90deg,var(--red),#b8202f)" }} />
                </div>
                <span className="pv">{sc.bear.p}%</span>
              </div>
            </div>
          </div>
          <div className="slider" style={{ marginTop: 10 }}>
            <div style={{ fontSize: 11, color: "var(--dim2)", fontFamily: "var(--mono)", display: "flex", justifyContent: "space-between" }}>
              <span>Swarm Bias</span>
              <span>{biasLbl}</span>
            </div>
            <input type="range" min={-1} max={1} step={0.05} value={bias} onChange={(e) => setBias(Number(e.target.value))} />
          </div>
          <div className="symbol-row">
            <select value={["BTCUSDT", "ETHUSDT", "AAPL", "ES"].includes(symbol) ? symbol : "BTCUSDT"} onChange={(e) => onSymbol(e.target.value)}>
              <option>BTCUSDT</option>
              <option>ETHUSDT</option>
              <option>AAPL</option>
              <option>ES</option>
            </select>
            {TIMEFRAMES.map((tf) => (
              <button key={tf} type="button" className={`ftab${tf === timeframe ? " active" : ""}`} onClick={() => onTimeframe(tf)}>
                {tf}
              </button>
            ))}
          </div>
          <div className="filters" style={{ marginTop: 10 }}>
            {OVERLAY_PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`ftab${overlayPreset === p.id ? " active" : ""}`}
                onClick={() => onOverlayPreset(p.id)}
              >
                {p.label}
              </button>
            ))}
          </div>
          <PriceChart
            bars={bars}
            historyKey={historyKey}
            lastBar={lastBar}
            vwap={vwap}
            sessions={sessions}
            visibleSessions={visibleSessions}
            timeframe={timeframe}
            theme={theme}
            patterns={patterns}
            overlayPreset={overlayPreset}
            selected={selected}
          />
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>🎲</span>
          <b>Scenario Probability Matrix — {focus?.symbol ?? "focus"}</b>
          <span className="sim">Simulation</span>
        </div>
        <div className="scen" style={{ marginTop: 12 }}>
          <div className="sc bull">
            <div className="sl">Bull</div>
            <div className="sp">+{sc.bull.r.toFixed(1)}%</div>
            <div className="sr">{sc.bull.p}% prob</div>
            <div className="sd">Upside cone</div>
          </div>
          <div className="sc base">
            <div className="sl">Base</div>
            <div className="sp">+{sc.base.r.toFixed(1)}%</div>
            <div className="sr">{sc.base.p}% prob</div>
            <div className="sd">Expected path</div>
          </div>
          <div className="sc bear">
            <div className="sl">Bear</div>
            <div className="sp">{sc.bear.r.toFixed(1)}%</div>
            <div className="sr">{sc.bear.p}% prob</div>
            <div className="sd">Downside cone</div>
          </div>
        </div>
        <div className="drivers" style={{ marginTop: 12 }}>
          <div className="drv">
            <span className="dt" style={{ background: "var(--emerald)" }} />
            Earnings beat
            <span className="dl">{Math.round(sc.bull.p * 0.7)}%</span>
          </div>
          <div className="drv">
            <span className="dt" style={{ background: "var(--gold)" }} />
            Macro headwinds
            <span className="dl">{Math.round(sc.base.p * 0.5)}%</span>
          </div>
          <div className="drv">
            <span className="dt" style={{ background: "var(--red)" }} />
            Whale sell-off
            <span className="dl">{Math.round(sc.bear.p * 0.6)}%</span>
          </div>
        </div>
      </div>
    </section>
  );
}
