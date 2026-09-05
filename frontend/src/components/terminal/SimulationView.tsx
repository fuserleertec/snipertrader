"use client";

import { OVERLAY_PRESETS, TIMEFRAMES } from "@/lib/constants";
import type { Theme } from "@/hooks/useTheme";
import { convictionOf, scenarioCones, swarmCells } from "@/lib/mocks/terminal";
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
  lastPrice,
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
  const ranked = [...signals].sort((a, b) => b.confidence - a.confidence).slice(0, 8);
  const focus = selected ?? ranked[0] ?? null;
  const conv = focus ? convictionOf(focus) : 50;
  const cones = scenarioCones(conv, focus?.side ?? "long");
  const cells = swarmCells(focus?.id ?? symbol, focus?.side === "short" ? -0.25 : 0.2);
  const bullN = cells.filter((c) => c === "bull").length;
  const bearN = cells.filter((c) => c === "bear").length;
  const bias = bullN === bearN ? "neutral" : bullN > bearN ? "bullish" : "bearish";

  return (
    <section className="sec">
      <div className="sec-head">
        <span className="ix">03</span>
        <h2>Live Market Simulation View</h2>
        <span className="sim">Simulation</span>
      </div>
      <div className="sec-sub">
        Setup candidates flow through Kronos pattern detection + MiroFish swarm consensus and are
        ranked by conviction. Click a row to join chart overlays via <code>trigger_event_ids</code>.
      </div>

      <div className="panel" style={{ padding: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 18 }}>📊</span>
          <b>Conviction &amp; Velocity Leaderboard</b>
          <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11, color: "var(--dim)" }}>
            {ranked.length} names
          </span>
        </div>
        <div className="lead">
          {ranked.map((s, i) => (
            <button
              key={s.id}
              type="button"
              className="lead-row"
              style={{ ["--accent" as string]: s.side === "long" ? "var(--emerald)" : "var(--red)" }}
              onClick={() => onSelect(s)}
            >
              <div className="lead-rank">{i + 1}</div>
              <div className="lead-main">
                <div className="lead-sym">
                  {s.symbol}
                  <span className={`lead-pill ${s.side === "long" ? "up" : "down"}`}>{s.side.toUpperCase()}</span>
                  <span className="lead-pill up">{s.setup_type}</span>
                </div>
                <div className="lead-meta">{s.trigger_event_ids.join(" · ") || "no trigger ids"}</div>
              </div>
              <div>
                <div className={`lead-score ${s.side === "long" ? "up" : "down"}`}>{convictionOf(s)}</div>
                <div className="lead-sub">conviction</div>
              </div>
            </button>
          ))}
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
          <div className="ssig">
            <span className="ic">🐟</span>
            <span className="nm">Swarm Bias</span>
            <span className="vl">{bias}</span>
          </div>
        </div>
        <div className="panel">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>📈</span>
            <b>
              Kronos Structural K-Line — <span>{symbol}</span>
            </b>
          </div>
          <div className="symbol-row">
            <select value={symbol} onChange={(e) => onSymbol(e.target.value)}>
              <option>BTCUSDT</option>
              <option>ETHUSDT</option>
              <option>AAPL</option>
              <option>ES</option>
            </select>
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                type="button"
                className={`ftab${tf === timeframe ? " active" : ""}`}
                onClick={() => onTimeframe(tf)}
              >
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
          <div className="kline-note">
            FVG / OB zones, sweep arrows, and MSS levels are Rev 1.1 primitives. Last {lastPrice ?? "—"}.
          </div>
          <div>
            <div className="pat-row">
              <span className="pn">Bull</span>
              <div className="pt">
                <div className="pf" style={{ width: `${cones.bull}%` }} />
              </div>
              <span className="pv">{cones.bull}%</span>
            </div>
            <div className="pat-row">
              <span className="pn">Base</span>
              <div className="pt">
                <div className="pf" style={{ width: `${cones.base}%`, background: "linear-gradient(90deg,var(--gold),#b8902a)" }} />
              </div>
              <span className="pv">{cones.base}%</span>
            </div>
            <div className="pat-row">
              <span className="pn">Bear</span>
              <div className="pt">
                <div className="pf" style={{ width: `${cones.bear}%`, background: "linear-gradient(90deg,var(--red),#b8202f)" }} />
              </div>
              <span className="pv">{cones.bear}%</span>
            </div>
            <div className="kline-note">Scenario cone probabilities (simulated Monte-Carlo, 1,000 passes).</div>
          </div>
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
            <div className="sp">{cones.bull}%</div>
            <div className="sr">{focus ? (focus.side === "long" ? focus.target : focus.stop).toFixed(1) : "—"}</div>
          </div>
          <div className="sc base">
            <div className="sl">Base</div>
            <div className="sp">{cones.base}%</div>
            <div className="sr">{focus ? focus.entry.toFixed(1) : "—"}</div>
          </div>
          <div className="sc bear">
            <div className="sl">Bear</div>
            <div className="sp">{cones.bear}%</div>
            <div className="sr">{focus ? (focus.side === "short" ? focus.target : focus.stop).toFixed(1) : "—"}</div>
          </div>
        </div>
      </div>
    </section>
  );
}
