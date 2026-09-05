"use client";

import { useMemo } from "react";
import { SETUP_TYPES } from "@/lib/constants";
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

function setupRank(setup: string): number {
  const i = (SETUP_TYPES as readonly string[]).indexOf(setup);
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
    const active = [...signals].filter((s) => s.status === "ACTIVE").sort((a, b) => b.ts_ms - a.ts_ms);
    const seen = new Set<string>();
    const pinned: Signal[] = [];
    const rest: Signal[] = [];
    for (const s of active) {
      if ((SETUP_TYPES as readonly string[]).includes(s.setup_type) && !seen.has(s.setup_type)) {
        seen.add(s.setup_type);
        pinned.push(s);
      } else {
        rest.push(s);
      }
    }
    pinned.sort((a, b) => setupRank(a.setup_type) - setupRank(b.setup_type));
    return [...pinned, ...rest].slice(0, 6);
  }, [signals]);

  return (
    <section className="sec" aria-label="Setup signal cards">
      <div className="sec-head">
        <span className="ix">P2</span>
        <h2>Active Setup Cards</h2>
        <span className="sim">setup_signals</span>
      </div>
      <div className="sec-sub">
        One newest ACTIVE per locked setup 1–6. Click a card to switch the overlay
        view and highlight ids in <code>trigger_event_ids</code>.
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
