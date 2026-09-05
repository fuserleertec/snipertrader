"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMarketData } from "@/hooks/useMarketData";
import { useSignals } from "@/hooks/useSignals";
import { useTheme } from "@/hooks/useTheme";
import { inferAssetClass, sessionsForAsset, SETUP_TYPES, SIGNAL_STATUSES } from "@/lib/constants";
import { defaultVisibleSessions } from "@/lib/sessions";
import type { AnchorType, SessionType, SetupType, SignalStatus, Timeframe } from "@/lib/types";
import { Header } from "./Header";
import { PriceChart } from "./PriceChart";
import { Sidebar } from "./Sidebar";
import { SignalTable } from "./SignalTable";

export function Dashboard() {
  const { theme, toggle } = useTheme();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<Timeframe>("1m");
  const [anchor, setAnchor] = useState<AnchorType>("session");
  const [visibleSessions, setVisibleSessions] = useState<SessionType[]>(() =>
    defaultVisibleSessions("crypto", Date.now()),
  );
  const [setupTypes, setSetupTypes] = useState<SetupType[]>(SETUP_TYPES);
  const [statuses, setStatuses] = useState<SignalStatus[]>(SIGNAL_STATUSES);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const assetClass = inferAssetClass(symbol);
  const market = useMarketData(symbol, timeframe);
  const priceRef = useRef(100);
  useEffect(() => {
    if (market.lastPrice != null) priceRef.current = market.lastPrice;
  }, [market.lastPrice]);
  const allSignals = useSignals(symbol, () => priceRef.current);
  const signals = useMemo(
    () =>
      allSignals.filter(
        (row) => setupTypes.includes(row.setup_type) && statuses.includes(row.status),
      ),
    [allSignals, setupTypes, statuses],
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

  const onToggleSetupType = (type: SetupType) => {
    setSetupTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
    );
  };

  const onToggleStatus = (status: SignalStatus) => {
    setStatuses((prev) =>
      prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status],
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
          setupTypes={setupTypes}
          onToggleSetupType={onToggleSetupType}
          statuses={statuses}
          onToggleStatus={onToggleStatus}
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
