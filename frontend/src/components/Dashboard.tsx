"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMarketData } from "@/hooks/useMarketData";
import { useSignals } from "@/hooks/useSignals";
import { useTheme } from "@/hooks/useTheme";
import { inferAssetClass, sessionsForAsset } from "@/lib/constants";
import { defaultVisibleSessions } from "@/lib/sessions";
import type { AnchorType, SessionType, SignalKind, Timeframe } from "@/lib/types";
import { Header } from "./Header";
import { PriceChart } from "./PriceChart";
import { Sidebar } from "./Sidebar";
import { SignalTable } from "./SignalTable";

const ALL_KINDS: SignalKind[] = ["setup", "fvg", "sweep"];

export function Dashboard() {
  const { theme, toggle } = useTheme();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("1m");
  const [anchor, setAnchor] = useState<AnchorType>("session");
  const [visibleSessions, setVisibleSessions] = useState<SessionType[]>(() =>
    defaultVisibleSessions("crypto", Date.now()),
  );
  const [signalKinds, setSignalKinds] = useState<SignalKind[]>(ALL_KINDS);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const assetClass = inferAssetClass(symbol);
  const market = useMarketData(symbol, timeframe);
  const priceRef = useRef(100);
  useEffect(() => {
    if (market.lastPrice != null) priceRef.current = market.lastPrice;
  }, [market.lastPrice]);
  const allSignals = useSignals(symbol, () => priceRef.current);
  const signals = useMemo(
    () => allSignals.filter((row) => signalKinds.includes(row.kind)),
    [allSignals, signalKinds],
  );

  const sessionBooks = useMemo(
    () => Object.values(market.sessions).filter((s): s is NonNullable<typeof s> => !!s),
    [market.sessions],
  );

  const onSymbol = (next: string) => {
    setSymbol(next);
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

  const onToggleKind = (kind: SignalKind) => {
    setSignalKinds((prev) =>
      prev.includes(kind) ? prev.filter((k) => k !== kind) : [...prev, kind],
    );
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
          signalKinds={signalKinds}
          onToggleKind={onToggleKind}
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
        />
      </div>
      <SignalTable rows={signals} />
    </div>
  );
}
