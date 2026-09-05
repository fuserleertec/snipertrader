"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMarketData } from "@/hooks/useMarketData";
import { usePatterns } from "@/hooks/usePatterns";
import { useSignals } from "@/hooks/useSignals";
import { useTheme } from "@/hooks/useTheme";
import { inferAssetClass } from "@/lib/constants";
import { dropUniverse } from "@/lib/mocks/universe";
import { convictionOf, tierOf } from "@/lib/mocks/terminal";
import { defaultVisibleSessions } from "@/lib/sessions";
import type { OverlayPreset, Signal, Timeframe } from "@/lib/types";
import { playAlert, ToastHost, type ToastItem } from "./ToastHost";
import { EngineGlossary, ExecutionDesk, Narratives, PickGrid, ReconAudit } from "./terminal/PickAndDesk";
import { QepTable } from "./terminal/QepTable";
import { SimulationView } from "./terminal/SimulationView";
import { SiteFooter, StatusStrip, TerminalNav } from "./terminal/SiteChrome";

export function Dashboard() {
  const { theme, toggle } = useTheme();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [overlayPreset, setOverlayPreset] = useState<OverlayPreset>("all");
  const [selected, setSelected] = useState<Signal | null>(null);
  const [soundOn, setSoundOn] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [tick, setTick] = useState(0);
  const seenHigh = useRef(new Set<string>());
  const chartRef = useRef<HTMLDivElement>(null);

  const market = useMarketData(symbol, timeframe);
  const priceRef = useRef(100);
  useEffect(() => {
    if (market.lastPrice != null) priceRef.current = market.lastPrice;
  }, [market.lastPrice]);
  const allSignals = useSignals(symbol, () => priceRef.current);
  const patterns = usePatterns(symbol);

  useEffect(() => {
    for (const row of allSignals) {
      if (row.confidence <= 0.8 || seenHigh.current.has(row.id)) continue;
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
    setSelected(null);
  };

  const onSelect = (signal: Signal) => {
    setSelected((prev) => (prev?.id === signal.id ? null : signal));
    if (signal.setup_type === "sweep_reclaim" || signal.setup_type === "sweep_mss") {
      setOverlayPreset("sweep_reclaim");
    } else if (signal.setup_type === "fvg_entry" || signal.setup_type === "ob_fvg" || signal.setup_type === "order_block") {
      setOverlayPreset("fvg_ob");
    } else if (signal.setup_type === "po3_judas") {
      setOverlayPreset("po3_judas");
    }
    if (signal.symbol && signal.symbol !== symbol) onSymbol(signal.symbol);
  };

  const onOpenChart = (signal: Signal) => {
    onSelect(signal);
    chartRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const visibleSessions = defaultVisibleSessions(inferAssetClass(symbol), market.lastBar?.close_ts_ms ?? 0);
  const dropped = allSignals.filter((s) => tierOf(convictionOf(s)) === "drop" || s.status !== "ACTIVE");
  const ageLabel = market.lastBar ? new Date(market.lastBar.close_ts_ms).toISOString().slice(11, 19) + "Z" : "—";

  const downloadCsv = () => {
    const header = "ts_ms,symbol,setup_type,side,entry,stop,target,status,confidence,trigger_event_ids";
    const lines = allSignals.map((r) =>
      [r.ts_ms, r.symbol, r.setup_type, r.side, r.entry, r.stop, r.target, r.status, r.confidence, r.trigger_event_ids.join("|")].join(","),
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

  const topPattern = allSignals[0]?.setup_type ?? "—";
  const consensus = allSignals.length
    ? Math.round((allSignals.filter((s) => s.side === "long").length / allSignals.length) * 100)
    : 0;

  return (
    <div>
      <TerminalNav theme={theme} onToggleTheme={toggle} />
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
          heartbeat={market.status === "mock" ? "mock 3s" : market.status}
          health={market.bars.length ? "ok" : "warming"}
          onRefresh={() => setTick((n) => n + 1)}
          onShare={share}
          onDownload={downloadCsv}
        />

        <div className="qstats">
          <div className="qstat">
            <div className="ql">Swarm Consensus</div>
            <div className="qv pos">{consensus ? `${consensus}% long` : "—"}</div>
          </div>
          <div className="qstat">
            <div className="ql">Volatility Index</div>
            <div className="qv gold">{vwapSigma(market.vwaps.session?.sigma)}</div>
          </div>
          <div className="qstat">
            <div className="ql">Swarm Agents</div>
            <div className="qv cy">80</div>
          </div>
          <div className="qstat">
            <div className="ql">Top Pattern</div>
            <div className="qv">{topPattern}</div>
          </div>
          <div className="qstat">
            <div className="ql">Universe Scanned</div>
            <div className="qv">{allSignals.length || "—"}</div>
          </div>
        </div>

        <div className="disclaimer">
          <b>SIMULATION &amp; EDUCATION NOTICE.</b> Kronos structural patterns overlay Rev 1.1 FVG,
          order blocks, liquidity sweeps, and MSS. The MiroFish agent swarm and scenario cones are{" "}
          <b>client-side simulations</b>. Nothing here is financial advice.
        </div>

        <QepTable
          signals={allSignals}
          lastPrice={market.lastPrice}
          selectedId={selected?.id ?? null}
          onSelectSignal={onOpenChart}
          soundOn={soundOn}
          onToggleSound={() => setSoundOn((v) => !v)}
        />

        <div ref={chartRef}>
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
            sessions={sessionBooks}
            visibleSessions={visibleSessions}
            theme={theme}
            patterns={patterns}
            lastPrice={market.lastPrice}
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
        <EngineGlossary />
        <details className="raw">
          <summary>Raw recon payload (debug)</summary>
          <pre>
            {JSON.stringify(
              { symbol, timeframe, selected: selected?.id ?? null, trigger_event_ids: selected?.trigger_event_ids ?? [] },
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
  if (sigma == null) return "—";
  return sigma.toFixed(2);
}
