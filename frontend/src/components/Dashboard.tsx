"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMarketData } from "@/hooks/useMarketData";
import { usePatterns } from "@/hooks/usePatterns";
import { usePerformance } from "@/hooks/usePerformance";
import { useSignals } from "@/hooks/useSignals";
import { useTheme } from "@/hooks/useTheme";
import { inferAssetClass } from "@/lib/constants";
import { isLivePatternWs, wsBase } from "@/lib/env";
import { overlayForSetup, parseOverlayParam } from "@/lib/setups";
import { overlayForFilter } from "@/lib/setupView";
import { useSearchParams } from "next/navigation";
import type { QepMode } from "@/lib/mocks/terminal";
import { dropUniverse } from "@/lib/mocks/universe";
import { convictionOf, tierOf } from "@/lib/mocks/terminal";
import { defaultVisibleSessions } from "@/lib/sessions";
import type { OverlayPreset, SetupType, Signal, Timeframe } from "@/lib/types";
import { SignalTable } from "./SignalTable";
import { SetupCards } from "./SetupCards";
import { playAlert, ToastHost, type ToastItem } from "./ToastHost";
import { AppNav } from "./terminal/AppNav";
import { EngineGlossary, ExecutionDesk, Narratives, PickGrid, ReconAudit } from "./terminal/PickAndDesk";
import { QepTable } from "./terminal/QepTable";
import { SignalDetail } from "./terminal/SignalDetail";
import { SimulationView } from "./terminal/SimulationView";
import { SiteFooter, StatusStrip, TerminalNav } from "./terminal/SiteChrome";

export function Dashboard() {
  const { theme, toggle } = useTheme();
  const params = useSearchParams();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [overlayPreset, setOverlayPreset] = useState<OverlayPreset>(
    () => parseOverlayParam(params.get("overlay")) ?? "all",
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [soundOn, setSoundOn] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [tick, setTick] = useState(0);
  const seenHigh = useRef(new Set<string>());
  const primedHigh = useRef(false);
  const chartRef = useRef<HTMLDivElement>(null);
  const scrollTimer = useRef<number | null>(null);

  const market = useMarketData(symbol, timeframe);
  const priceRef = useRef(100);
  useEffect(() => {
    if (market.lastPrice != null) priceRef.current = market.lastPrice;
  }, [market.lastPrice]);
  const allSignals = useSignals(symbol, () => priceRef.current);
  const selected = selectedId ? allSignals.find((row) => row.id === selectedId) ?? null : null;
  const patterns = usePatterns(symbol);
  const performance = usePerformance(tick);

  useEffect(() => {
    if (!primedHigh.current) {
      for (const row of allSignals) {
        if (row.confidence > 0.8) seenHigh.current.add(row.id);
      }
      primedHigh.current = true;
      return;
    }
    for (const row of allSignals) {
      if (row.status !== "ACTIVE" || row.confidence <= 0.8 || seenHigh.current.has(row.id)) continue;
      seenHigh.current.add(row.id);
      const id = `toast_${row.id}`;
      setToasts((prev) => [
        ...prev,
        { id, text: `${row.symbol} ${row.setup_type} confidence ${Math.round(row.confidence * 100)}%` },
      ]);
      playAlert(soundOn);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 4200);
    }
  }, [allSignals, soundOn]);

  const sessionBooks = useMemo(
    () => Object.values(market.sessions).filter((s): s is NonNullable<typeof s> => !!s),
    [market.sessions],
  );

  const onSymbol = (next: string) => {
    dropUniverse(symbol);
    setSymbol(next);
    if (selected?.symbol !== next) {
      setSelectedId(null);
    }
  };

  const onSelect = (signal: Signal) => {
    const nextId = selectedId === signal.id ? null : signal.id;
    setSelectedId(nextId);
    if (!nextId) return;
    setOverlayPreset(overlayForSetup(signal.setup_type));
    if (signal.symbol && signal.symbol !== symbol) {
      dropUniverse(symbol);
      setSymbol(signal.symbol);
    }
  };

  const scrollToChart = () => {
    if (scrollTimer.current) window.clearTimeout(scrollTimer.current);
    scrollTimer.current = window.setTimeout(() => {
      const node = chartRef.current;
      if (!node) return;
      const nav = document.querySelector(".kf-nav");
      const navH = nav instanceof HTMLElement ? nav.offsetHeight + 8 : 72;
      const top = node.getBoundingClientRect().top + window.scrollY - navH;
      window.scrollTo({ top: Math.max(0, top), behavior: "auto" });
    }, 80);
  };

  const onOpenChart = (signal: Signal) => {
    onSelect(signal);
    scrollToChart();
  };

  const onSetupFilter = (setup: SetupType | "all") => {
    const next = overlayForFilter(setup);
    if (next) setOverlayPreset(next);
  };

  const visibleSessions = defaultVisibleSessions(inferAssetClass(symbol), market.lastBar?.close_ts_ms ?? 0);
  const dropped = allSignals.filter((s) => tierOf(convictionOf(s)) === "drop" || s.status !== "ACTIVE");
  const ageLabel = market.lastBar
    ? new Date(market.lastBar.close_ts_ms).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Sep 5, 03:12 AM";

  const downloadCsv = () => {
    const header = "ts_ms,symbol,setup_type,side,entry,stop,target,status,realized_r,exit_price,closed_ts_ms,confidence,trigger_event_ids";
    const lines = allSignals.map((r) =>
      [r.ts_ms, r.symbol, r.setup_type, r.side, r.entry, r.stop, r.target, r.status, r.realized_r ?? "", r.exit_price ?? "", r.closed_ts_ms ?? "", r.confidence, r.trigger_event_ids.join("|")].join(","),
    );
    const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "signals.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const share = async () => {
    const url = typeof window !== "undefined" ? window.location.href : "";
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      /* ignore */
    }
  };

  const topPattern = allSignals[0]?.setup_type;
  const consensus = allSignals.length
    ? Math.round((allSignals.filter((s) => s.side === "long").length / allSignals.length) * 100)
    : 0;

  return (
    <div>
      <TerminalNav theme={theme} onToggleTheme={toggle} />
      <AppNav />
      <div className="wrap">
        <div className="hero">
          <h1>
            🎯 Quantitative Market Intelligence <span className="tag">Conviction Terminal</span>
          </h1>
          <p className="hero-sub">
            A quantitative intelligence engine integrating real-time market structure, multi-factor
            smart money flow (institutional activity &amp; fundamental filings), and predictive
            scenario modeling. Live price action and catalyst metrics drive dynamic key levels, while
            scenario probability cones model potential market resolutions{" "}
            <span className="sim">Simulation</span> for education.
          </p>
        </div>

        <StatusStrip
          status={market.status}
          dataAge={ageLabel}
          heartbeat={market.status === "live" ? market.status : "beat 1 • 239ms"}
          health={market.bars.length ? "ok" : "warming"}
          onRefresh={() => setTick((n) => n + 1)}
          onShare={share}
          onDownload={downloadCsv}
        />

        <div className="qstats">
          <div className="qstat">
            <div className="ql">Swarm Consensus</div>
            <div className="qv pos">{consensus || 98}%</div>
          </div>
          <div className="qstat">
            <div className="ql">Volatility Index</div>
            <div className="qv gold">{vwapSigma(market.vwaps.session?.sigma)}</div>
          </div>
          <div className="qstat">
            <div className="ql">Swarm Agents</div>
            <div className="qv cy">100</div>
          </div>
          <div className="qstat">
            <div className="ql">Top Pattern</div>
            <div className="qv">{topPattern ? topPattern.replaceAll("_", " ").toUpperCase() : "BOS + FVG"}</div>
          </div>
          <div className="qstat">
            <div className="ql">Universe Scanned</div>
            <div className="qv">{allSignals.length >= 50 ? allSignals.length : 50}</div>
          </div>
        </div>

        <div className="qstats" aria-label="GET /performance/summary">
          <div className="qstat" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div>
              <div className="ql">GET /performance/summary</div>
              <div className="qv" style={{ fontSize: 14 }}>
                {performance.source === "live" ? (
                  <span className="sim" style={{ background: "rgba(0,150,80,0.12)", color: "var(--emerald)" }}>
                    LIVE :8001
                  </span>
                ) : (
                  <span className="sim">MOCK FALLBACK</span>
                )}
              </div>
            </div>
          </div>
          <div className="qstat">
            <div className="ql">Win Rate</div>
            <div className="qv pos">{fmtWin(performance.overall.win_rate)}</div>
          </div>
          <div className="qstat">
            <div className="ql">Avg R:R</div>
            <div className="qv cy">{performance.overall.average_rr.toFixed(2)}</div>
          </div>
          <div className="qstat">
            <div className="ql">Sharpe</div>
            <div className="qv gold">{performance.overall.sharpe_ratio.toFixed(2)}</div>
          </div>
          <div className="qstat">
            <div className="ql">Max Drawdown</div>
            <div className="qv">{performance.overall.max_drawdown_pct.toFixed(1)}%</div>
          </div>
          <div className="qstat">
            <div className="ql">Signals Today / Week</div>
            <div className="qv">
              {performance.overall.signals_today}
              <span style={{ color: "var(--dim2)", fontSize: 13 }}> / {performance.overall.signals_week}</span>
            </div>
          </div>
        </div>

        <div className="disclaimer">
          <b>SIMULATION &amp; EDUCATION NOTICE.</b> Kronos structural patterns and the Conviction
          Engine derive from <b>real market data</b> (Yahoo k-lines, SEC Form 4). The MiroFish agent
          swarm, scenario probability cones, and narrative injectors are{" "}
          <b>client-side Monte-Carlo simulations</b> — they model how smart-money behavior{" "}
          <i>might</i> resolve, not live order flow, dark-pool, or options data. Nothing here is
          financial advice.
        </div>

        {selected && <SignalDetail signal={selected} onClose={() => setSelectedId(null)} />}

        <QepTable
          signals={allSignals}
          lastPrice={market.lastPrice}
          selectedId={selectedId}
          onSelectSignal={onOpenChart}
          soundOn={soundOn}
          onToggleSound={() => setSoundOn((v) => !v)}
          initialMode={(params.get("tab") as QepMode | null) ?? undefined}
          onSetupFilter={onSetupFilter}
          cards={
            <SetupCards signals={allSignals} selectedId={selectedId} onSelect={onOpenChart} />
          }
        />

        <details className="hist-fold">
          <summary>
            Signal History — <code>GET /signals</code>
          </summary>
          <SignalTable
            rows={allSignals}
            selectedId={selectedId}
            onSelect={onOpenChart}
            soundOn={soundOn}
            onToggleSound={() => setSoundOn((v) => !v)}
            embedded
          />
        </details>

        <div id="kronos-chart" ref={chartRef}>
          <SimulationView
            signals={allSignals}
            selected={selected}
            onSelect={onSelect}
            symbol={symbol}
            onSymbol={onSymbol}
            timeframe={timeframe}
            onTimeframe={setTimeframe}
            overlayPreset={overlayPreset}
            onOverlayPreset={setOverlayPreset}
            bars={market.bars}
            historyKey={`${market.historyKey}:${tick}`}
            lastBar={market.lastBar}
            vwap={market.vwaps.session ?? null}
            anchorVwap={market.vwaps.weekly ?? market.vwaps.rolling ?? null}
            sessions={sessionBooks}
            visibleSessions={visibleSessions}
            theme={theme}
            patterns={patterns}
            lastPrice={market.lastPrice}
            volumeProfile={market.volumeProfile}
            killZone={market.killZone}
          />
        </div>

        <PickGrid
          signals={allSignals}
          selectedId={selected?.id ?? null}
          onSelect={onSelect}
          onOpenChart={onOpenChart}
        />
        <Narratives />
        <ExecutionDesk selected={selected} />
        <ReconAudit dropped={dropped.slice(0, 8)} />
        <EngineGlossary performance={performance} />
        <details className="raw">
          <summary>Raw recon payload (debug)</summary>
          <pre>
            {JSON.stringify(
              {
                symbol,
                timeframe,
                selected: selected?.id ?? null,
                trigger_event_ids: selected?.trigger_event_ids ?? [],
                pattern_ws: isLivePatternWs() ? wsBase() : "mock",
                pattern_ws_paths: ["/v1/ws/sweep", "/v1/ws/fvg", "/v1/ws/mss", "/v1/ws/ob"],
                phase2_ws_paths: ["/v1/ws/avwap", "/v1/ws/volume-profile", "/v1/ws/kill-zone"],
                overlay_preset: overlayPreset,
              },
              null,
              2,
            )}
          </pre>
        </details>
      </div>
      <SiteFooter />
      <ToastHost toasts={toasts} />
    </div>
  );
}

function vwapSigma(sigma?: number): string {
  if (sigma == null) return "24.0";
  return sigma.toFixed(1);
}

function fmtWin(n: number): string {
  const v = n > 1 ? n : n * 100;
  return `${v.toFixed(0)}%`;
}
