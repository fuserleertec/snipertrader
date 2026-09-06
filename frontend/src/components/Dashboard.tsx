"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useActiveSetups } from "@/hooks/useActiveSetups";
import { useDeskLists } from "@/hooks/useDeskLists";
import { formatEt, formatRemain, useListRefresh } from "@/hooks/useListRefresh";
import { useMarketData } from "@/hooks/useMarketData";
import { usePatterns } from "@/hooks/usePatterns";
import { usePerformance } from "@/hooks/usePerformance";
import { useSignals } from "@/hooks/useSignals";
import { useTheme } from "@/hooks/useTheme";
import { inferAssetClass, LIST_REFRESH_SEC } from "@/lib/constants";
import {
  assetClassToTab,
  capReconAudit,
  chartExtrasFromTop,
  chartSymbolsForTab,
  defaultSymbolForTab,
  tabToAssetClass,
  uniqueSymbols,
} from "@/lib/desk";
import { isLivePatternWs, wsBase } from "@/lib/env";
import { overlayForSetup, parseOverlayParam } from "@/lib/setups";
import { overlayForFilter, resolveSelected } from "@/lib/setupView";
import { useSearchParams } from "next/navigation";
import type { QepMode } from "@/lib/mocks/terminal";
import { dropUniverse } from "@/lib/mocks/universe";
import { convictionOf, tierOf } from "@/lib/mocks/terminal";
import { defaultVisibleSessions } from "@/lib/sessions";
import type { AssetTab, OverlayPreset, SetupType, Signal, Timeframe } from "@/lib/types";
import { SignalTable } from "./SignalTable";
import { SetupCards } from "./SetupCards";
import { playAlert, ToastHost, type ToastItem } from "./ToastHost";
import { EngineGlossary, Narratives, PickGrid, ReconAudit } from "./terminal/PickAndDesk";
import { QepTable } from "./terminal/QepTable";
import { SignalDetail } from "./terminal/SignalDetail";
import { SimulationView } from "./terminal/SimulationView";
import { SiteFooter, StatusStrip, TerminalNav } from "./terminal/SiteChrome";

export function Dashboard() {
  const { theme, toggle } = useTheme();
  const params = useSearchParams();
  const [assetTab, setAssetTab] = useState<AssetTab>("futures");
  const [setupFilter, setSetupFilter] = useState<SetupType | "all">("all");
  const [symbol, setSymbol] = useState("ES");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [overlayPreset, setOverlayPreset] = useState<OverlayPreset>(
    () => parseOverlayParam(params.get("overlay")) ?? "all",
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedSnap, setSelectedSnap] = useState<Signal | null>(null);
  const [soundOn, setSoundOn] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seenHigh = useRef(new Set<string>());
  const primedHigh = useRef(false);
  const chartRef = useRef<HTMLDivElement>(null);
  const scrollTimer = useRef<number | null>(null);

  const [refreshSec, setRefreshSec] = useState(LIST_REFRESH_SEC);
  const [asOfTsMs, setAsOfTsMs] = useState(0);
  const refresh = useListRefresh(refreshSec, asOfTsMs);
  const desk = useDeskLists(refresh.tick);

  useEffect(() => {
    setRefreshSec(desk.ensemble.refresh_sec);
    const asOf = Math.max(
      desk.universeTop20.as_of_ts_ms,
      desk.universeTop10.as_of_ts_ms,
      desk.ensemble.as_of_ts_ms,
      desk.categorized.as_of_ts_ms,
    );
    setAsOfTsMs(asOf);
  }, [
    desk.ensemble.refresh_sec,
    desk.universeTop20.as_of_ts_ms,
    desk.universeTop10.as_of_ts_ms,
    desk.ensemble.as_of_ts_ms,
    desk.categorized.as_of_ts_ms,
  ]);

  const deskSymbols = useMemo(
    () => uniqueSymbols(chartExtrasFromTop(desk.universeTop20)),
    [desk.universeTop20],
  );

  const market = useMarketData(symbol, timeframe);
  const priceRef = useRef(100);
  useEffect(() => {
    if (market.lastPrice != null) priceRef.current = market.lastPrice;
  }, [market.lastPrice]);
  const allSignals = useSignals(symbol, () => priceRef.current, refresh.tick, deskSymbols);
  const activeSetups = useActiveSetups(assetTab, setupFilter, refresh.tick);
  const selected = resolveSelected(allSignals, selectedId, selectedSnap);
  const patterns = usePatterns(symbol);
  const performance = usePerformance(refresh.tick, deskSymbols);

  const chartSymbols = useMemo(
    () => chartSymbolsForTab(assetTab, allSignals, chartExtrasFromTop(desk.universeTop20), symbol),
    [assetTab, allSignals, desk.universeTop20, symbol],
  );

  useEffect(() => {
    if (!selectedId) {
      setSelectedSnap(null);
      return;
    }
    if (selected) setSelectedSnap(selected);
  }, [selectedId, selected]);

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
    const nextClass = inferAssetClass(next);
    const nextTab = assetClassToTab(nextClass);
    if (nextTab !== assetTab) setAssetTab(nextTab);
    if (selected?.symbol !== next) {
      setSelectedId(null);
    }
  };

  const onAssetTab = (tab: AssetTab) => {
    setAssetTab(tab);
    if (inferAssetClass(symbol) !== tabToAssetClass(tab)) {
      const options = chartSymbolsForTab(tab, allSignals, chartExtrasFromTop(desk.universeTop20));
      onSymbol(defaultSymbolForTab(tab, options));
    }
  };

  const onSelect = (signal: Signal) => {
    const nextId = selectedId === signal.id ? null : signal.id;
    setSelectedId(nextId);
    if (!nextId) return;
    setOverlayPreset(overlayForSetup(signal.setup_type));
    setAssetTab(assetClassToTab(signal.asset_class));
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
    setSetupFilter(setup);
    const next = overlayForFilter(setup);
    if (next) setOverlayPreset(next);
  };

  const visibleSessions = defaultVisibleSessions(inferAssetClass(symbol), market.lastBar?.close_ts_ms ?? 0);
  const dropped = capReconAudit(
    allSignals.filter((s) => tierOf(convictionOf(s)) === "drop" || s.status !== "ACTIVE"),
  );
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
          nextRefresh={`${formatEt(refresh.nextAtMs)} ET · ${formatRemain(refresh.remainMs)} · ${refresh.refreshSec}s cycle`}
          onRefresh={refresh.refreshNow}
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
            <div className="qv">{new Set(allSignals.map((s) => s.symbol)).size || 20}</div>
          </div>
        </div>

        <div className="disclaimer">
          <b>SIMULATION &amp; EDUCATION NOTICE.</b> Kronos structural patterns and the Conviction
          Engine derive from <b>real market data</b> (Yahoo k-lines, SEC Form 4). The MiroFish agent
          swarm, scenario probability cones, and narrative injectors are{" "}
          <b>client-side Monte-Carlo simulations</b> — they model how smart-money behavior{" "}
          <i>might</i> resolve, not live order flow, dark-pool, or options data. Nothing here is
          financial advice. Paper desk only — <code>live_trading=false</code>.
        </div>

        <QepTable
          signals={allSignals}
          lastPrice={market.lastPrice}
          selectedId={selectedId}
          onSelectSignal={onOpenChart}
          onSelectSymbol={(next) => {
            onSymbol(next);
            scrollToChart();
          }}
          soundOn={soundOn}
          onToggleSound={() => setSoundOn((v) => !v)}
          initialMode={(params.get("tab") as QepMode | null) ?? undefined}
          onSetupFilter={onSetupFilter}
          ensembleItems={desk.ensemble.items}
          cycle={refresh.tick}
          universeSource={desk.ensemble.universe_source}
          cards={
            <SetupCards
              signals={activeSetups}
              selectedId={selectedId}
              onSelect={onOpenChart}
              assetTab={assetTab}
              onAssetTab={onAssetTab}
              setupFilter={setupFilter}
              onSetupFilter={onSetupFilter}
            />
          }
          history={
            <SignalTable
              rows={allSignals}
              selectedId={selectedId}
              onSelect={onOpenChart}
              soundOn={soundOn}
              onToggleSound={() => setSoundOn((v) => !v)}
              embedded
              deskSymbols={deskSymbols}
            />
          }
        />

        <SimulationView
          chartRef={chartRef}
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
          historyKey={`${market.historyKey}:${refresh.tick}`}
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
          chartSymbols={chartSymbols}
          categorized={desk.categorized.items}
        />
        {selected && <SignalDetail signal={selected} onClose={() => setSelectedId(null)} />}

        <PickGrid
          signals={allSignals}
          selectedId={selected?.id ?? null}
          onSelect={onSelect}
          onOpenChart={onOpenChart}
          onSelectSymbol={(next) => {
            onSymbol(next);
            scrollToChart();
          }}
          categorized={desk.categorized.items}
        />
        <Narratives />
        <ReconAudit dropped={dropped} audit={desk.dropped} />
        <EngineGlossary performance={performance} />
        <details className="raw">
          <summary>Raw recon payload (debug)</summary>
          <pre>
            {JSON.stringify(
              {
                symbol,
                asset_tab: assetTab,
                setup_filter: setupFilter,
                timeframe,
                selected: selected?.id ?? null,
                trigger_event_ids: selected?.trigger_event_ids ?? [],
                pattern_ws: isLivePatternWs() ? wsBase() : "mock",
                pattern_ws_paths: ["/v1/ws/sweep", "/v1/ws/fvg", "/v1/ws/mss", "/v1/ws/ob"],
                phase2_ws_paths: ["/v1/ws/avwap", "/v1/ws/volume-profile", "/v1/ws/kill-zone"],
                overlay_preset: overlayPreset,
                list_refresh_sec: refresh.refreshSec,
                ensemble_refresh_sec: desk.ensemble.refresh_sec,
                picks: {
                  ensemble: "/picks/ensemble",
                  categorized: "/picks/categorized",
                  signals: "/signals",
                  performance: "/performance/summary",
                  history: "/signals/history",
                  universe_top: "/v1/universe/top",
                  universe: "/v1/universe",
                  universe_source: desk.ensemble.universe_source,
                  universe_top10: desk.universeTop10.symbols.map((s) => s.symbol),
                  universe_top20: desk.universeTop20.symbols.map((s) => s.symbol),
                  desk_symbols: deskSymbols,
                },
                live_trading: false,
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
