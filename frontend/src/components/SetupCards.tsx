"use client";

import { useMemo } from "react";
import { OVERLAY_SETUP_TYPES } from "@/lib/constants";
import { riskReward } from "@/lib/signals";
import type { Signal } from "@/lib/types";

function utcStamp(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`;
}

function px(n: number): string {
  return n >= 1000 ? n.toFixed(1) : n.toFixed(2);
}

function overlayRank(setup: string): number {
  const i = (OVERLAY_SETUP_TYPES as readonly string[]).indexOf(setup);
  return i === -1 ? 100 : i;
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
  const cards = useMemo(() => {
    return [...signals]
      .filter((s) => s.status === "ACTIVE")
      .sort((a, b) => {
        const d = overlayRank(a.setup_type) - overlayRank(b.setup_type);
        if (d !== 0) return d;
        return b.ts_ms - a.ts_ms;
      })
      .slice(0, 8);
  }, [signals]);

  return (
    <section className="sec" aria-label="Setup signal cards">
      <div className="sec-head">
        <span className="ix">P2</span>
        <h2>Active Setup Cards</h2>
        <span className="sim">setup_signals</span>
      </div>
      <div className="sec-sub">
        Overlay-focus first ({OVERLAY_SETUP_TYPES.join(", ")}). Click a card to switch the
        setup view and highlight overlays whose ids are in <code>trigger_event_ids</code>.
      </div>
      <div className="card-strip">
        {cards.length === 0 && <div className="card-empty">Waiting for ACTIVE setups…</div>}
        {cards.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`setup-card ${s.side} ${selectedId === s.id ? "selected" : ""}`}
            onClick={() => onSelect(s)}
            data-setup={s.setup_type}
            data-symbol={s.symbol}
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
    </section>
  );
}
