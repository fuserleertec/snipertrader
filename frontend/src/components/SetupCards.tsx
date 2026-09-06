"use client";

import { ASSET_TABS, SETUP_FILTERS } from "@/lib/constants";
import { cardsForTab } from "@/lib/desk";
import { pinSetupCards } from "@/lib/setupView";
import { riskReward } from "@/lib/signals";
import type { AssetTab, SetupType, Signal } from "@/lib/types";
import { useMemo } from "react";

function utcStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
}

function px(n: number): string {
  return n >= 1000 ? n.toFixed(1) : n.toFixed(2);
}

export function SetupCards({
  signals,
  selectedId,
  onSelect,
  assetTab,
  onAssetTab,
  setupFilter,
  onSetupFilter,
}: {
  signals: Signal[];
  selectedId: string | null;
  onSelect: (signal: Signal) => void;
  assetTab: AssetTab;
  onAssetTab: (tab: AssetTab) => void;
  setupFilter: SetupType | "all";
  onSetupFilter: (setup: SetupType | "all") => void;
}) {
  const cards = useMemo(
    () => cardsForTab(signals, assetTab, setupFilter, selectedId, pinSetupCards),
    [signals, assetTab, setupFilter, selectedId],
  );

  return (
    <div className="setup-desk" data-pin="signal.id">
      <div className="setup-desk-head">
        <div className="qep-toggle setup-tabs" role="tablist" aria-label="Active setup asset class">
          {ASSET_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={assetTab === tab.id}
              className={assetTab === tab.id ? "active" : ""}
              data-asset-tab={tab.id}
              onClick={() => onAssetTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <label className="setup-filter">
          <span>Setup</span>
          <select
            value={setupFilter}
            aria-label="Filter setups 1 through 6"
            onChange={(e) => onSetupFilter(e.target.value as SetupType | "all")}
          >
            <option value="all">all setups 1–6</option>
            {SETUP_FILTERS.map((s) => (
              <option key={s.setup_type} value={s.setup_type}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="card-strip">
        {cards.length === 0 && (
          <div className="card-empty">Waiting for ACTIVE {assetTab} setups…</div>
        )}
        {cards.map((s) => (
          <button
            key={s.id}
            type="button"
            id={`setup-card-${s.id}`}
            className={`setup-card ${s.side} ${selectedId === s.id ? "selected" : ""}`}
            onClick={() => onSelect(s)}
            data-setup={s.setup_type}
            data-symbol={s.symbol}
            data-asset-class={s.asset_class}
            data-signal-id={s.id}
            data-triggers={s.trigger_event_ids.join(",")}
          >
            <div className="card-top">
              <span className="card-symbol">{s.symbol}</span>
              <span className={`setup-badge setup-${s.setup_type}`}>{s.setup_type}</span>
              <span className={`side-pill ${s.side}`}>{s.side.toUpperCase()}</span>
            </div>
            <dl className="card-levels">
              <div>
                <dt>entry</dt>
                <dd>{px(s.entry)}</dd>
              </div>
              <div>
                <dt>stop</dt>
                <dd>{px(s.stop)}</dd>
              </div>
              <div>
                <dt>target</dt>
                <dd>{px(s.target)}</dd>
              </div>
              <div>
                <dt>R:R</dt>
                <dd>{riskReward(s).toFixed(2)}</dd>
              </div>
            </dl>
            <div className="card-meta">
              <span>
                {s.timeframe}
                {s.session_type ? ` · ${s.session_type}` : ""} · {Math.round(s.confidence * 100)}%
              </span>
              <span className="mono">{utcStamp(s.ts_ms)}</span>
            </div>
            {s.trigger_event_ids.length > 0 ? (
              <div className="card-meta" style={{ marginTop: 4, fontSize: 10 }}>
                <span>triggers {s.trigger_event_ids.length}</span>
                <span className="mono">{s.trigger_event_ids.join(" · ")}</span>
              </div>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}
