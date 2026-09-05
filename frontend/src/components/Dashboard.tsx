"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMarketData } from "@/hooks/useMarketData";
import { usePatterns } from "@/hooks/usePatterns";
import { useSignals } from "@/hooks/useSignals";
import { useTheme } from "@/hooks/useTheme";
import { inferAssetClass, sessionsForAsset, SETUP_TYPES, SIGNAL_STATUSES } from "@/lib/constants";
import { dropUniverse } from "@/lib/mocks/universe";
import { defaultVisibleSessions } from "@/lib/sessions";
import type { AnchorType, OverlayPreset, SessionType, SetupType, Signal, SignalStatus, Timeframe } from "@/lib/types";
import { Header } from "./Header";
import { PriceChart } from "./PriceChart";
import { SetupCards } from "./SetupCards";
import { Sidebar } from "./Sidebar";
import { SignalTable } from "./SignalTable";
import { playAlert, ToastHost, type ToastItem } from "./ToastHost";

export function Dashboard() {
  const { theme, toggle } = useTheme();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [anchor, setAnchor] = useState<AnchorType>("session");
  const [visibleSessions, setVisibleSessions] = useState<SessionType[]>(() =>
    defaultVisibleSessions("crypto", Date.now()),
  );
  const [setupTypes, setSetupTypes] = useState<SetupType[]>(SETUP_TYPES);
  const [statuses, setStatuses] = useState<SignalStatus[]>(SIGNAL_STATUSES);
  const [overlayPreset, setOverlayPreset] = useState<OverlayPreset>("all");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selected, setSelected] = useState<Signal | null>(null);
  const [soundOn, setSoundOn] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seenHigh = useRef(new Set<string>());

  const assetClass = inferAssetClass(symbol);
  const market = useMarketData(symbol, timeframe);
  const priceRef = useRef(100);
  useEffect(() => {
    if (market.lastPrice != null) priceRef.current = market.lastPrice;
  }, [market.lastPrice]);
  const allSignals = useSignals(symbol, () => priceRef.current);
  const patterns = usePatterns(symbol);

  const signals = useMemo(
    () =>
      allSignals.filter(
        (row) => setupTypes.includes(row.setup_type) && statuses.includes(row.status),
      ),
    [allSignals, setupTypes, statuses],
  );

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
    const asset = inferAssetClass(next);
    setVisibleSessions(defaultVisibleSessions(asset, Date.now()));
  };

  const onToggleSession = (session: SessionType) => {
    setVisibleSessions((prev) => {
      const allowed = sessionsForAsset(assetClass);
      if (!allowed.includes(session)) return prev;
      return prev.includes(session) ? prev.filter((s) => s !== session) : [...prev, session];
    });
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
  };

  return (
    <div className="dash">
      <Header
        symbol={symbol}
        onSymbol={onSymbol}
        timeframe={timeframe}
        onTimeframe={setTimeframe}
        status={market.status}
        theme={theme}
        onToggleTheme={toggle}
        lastPrice={market.lastPrice}
      />
      <SetupCards signals={signals} selectedId={selected?.id ?? null} onSelect={onSelect} />
      <button
        type="button"
        className="sidebar-toggle"
        onClick={() => setSidebarOpen((v) => !v)}
      >
        {sidebarOpen ? "Hide filters" : "Filters"}
      </button>
      <div className="dash-body">
        <Sidebar
          assetClass={assetClass}
          anchor={anchor}
          onAnchor={setAnchor}
          visibleSessions={visibleSessions}
          onToggleSession={onToggleSession}
          setupTypes={setupTypes}
          onToggleSetupType={(type) =>
            setSetupTypes((prev) =>
              prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
            )
          }
          statuses={statuses}
          onToggleStatus={(status) =>
            setStatuses((prev) =>
              prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status],
            )
          }
          overlayPreset={overlayPreset}
          onOverlayPreset={setOverlayPreset}
          vwap={market.vwaps[anchor] ?? null}
          sessionBooks={sessionBooks}
          open={sidebarOpen}
        />
        <PriceChart
          bars={market.bars}
          historyKey={market.historyKey}
          lastBar={market.lastBar}
          vwap={market.vwaps[anchor] ?? null}
          sessions={sessionBooks}
          visibleSessions={visibleSessions}
          timeframe={timeframe}
          theme={theme}
          patterns={patterns}
          overlayPreset={overlayPreset}
          selected={selected}
        />
      </div>
      <SignalTable
        rows={signals}
        selectedId={selected?.id ?? null}
        onSelect={onSelect}
        soundOn={soundOn}
        onToggleSound={() => setSoundOn((v) => !v)}
      />
      <ToastHost toasts={toasts} />
    </div>
  );
}
