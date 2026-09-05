"use client";

import { pinSetupCards } from "@/lib/setupView";
import { riskReward } from "@/lib/signals";
import type { Signal } from "@/lib/types";
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
}: {
  signals: Signal[];
  selectedId: string | null;
  onSelect: (signal: Signal) => void;
}) {
  const cards = useMemo(() => pinSetupCards(signals, selectedId), [signals, selectedId]);

  return (
    <div className="card-strip" data-pin="signal.id">
      {cards.length === 0 && <div className="card-empty">Waiting for ACTIVE setups…</div>}
      {cards.map((s) => (
        <button
          key={s.id}
          type="button"
          id={`setup-card-${s.id}`}
          className={`setup-card ${s.side} ${selectedId === s.id ? "selected" : ""}`}
          onClick={() => onSelect(s)}
          data-setup={s.setup_type}
          data-symbol={s.symbol}
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
  );
}
