"use client";

import { productKeyOf } from "@/lib/setups";
import { riskReward } from "@/lib/signals";
import type { Signal } from "@/lib/types";

export function SignalDetail({
  signal,
  onClose,
}: {
  signal: Signal;
  onClose: () => void;
}) {
  const ids = signal.contributing_factors ?? [];
  const rows = signal.factor_breakdown ?? [];
  const conviction = rows.reduce((s, r) => s + r.score, 0);
  const copy = async () => {
    const payload = {
      id: signal.id,
      setup_type: signal.setup_type,
      product_key: productKeyOf(signal.setup_type),
      symbol: signal.symbol,
      side: signal.side,
      entry: signal.entry,
      stop: signal.stop,
      target: signal.target,
      trigger_event_ids: signal.trigger_event_ids,
      contributing_factors: ids,
      factor_breakdown: rows,
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="panel signal-detail">
      <div className="perf-head">
        <b>
          {signal.symbol} · {signal.setup_type}
        </b>
        <span className="qep-name">{productKeyOf(signal.setup_type)}</span>
        <span className="spacer" />
        <button type="button" className="btn" onClick={copy}>
          COPY SIGNAL
        </button>
        <button type="button" className="btn" onClick={onClose}>
          CLOSE
        </button>
      </div>
      <div className="pick-metrics">
        <div className="pm">
          <div className="pk">entry</div>
          <div className="pv cy">{signal.entry.toFixed(2)}</div>
        </div>
        <div className="pm">
          <div className="pk">stop</div>
          <div className="pv neu">{signal.stop.toFixed(2)}</div>
        </div>
        <div className="pm">
          <div className="pk">target</div>
          <div className="pv pos">{signal.target.toFixed(2)}</div>
        </div>
        <div className="pm">
          <div className="pk">R:R</div>
          <div className="pv">{riskReward(signal).toFixed(2)}</div>
        </div>
      </div>
      <div className="sec-sub" style={{ marginTop: 12 }}>
        PR #9 explainability — <code>contributing_factors[]</code> are factor ids.{" "}
        <code>sum(factor_breakdown.score)</code> ≈ conviction ({conviction.toFixed(0)}). Chart join is{" "}
        <code>trigger_event_ids</code> only
        {signal.trigger_event_ids.length ? `: ${signal.trigger_event_ids.join(", ")}` : " (none)"}.
      </div>
      <div className="pick-tags" style={{ marginTop: 10 }}>
        {ids.map((id) => (
          <span key={id} className="ptag">
            {id}
          </span>
        ))}
      </div>
      <div className="recon-grid">
        {rows.length === 0 && <div className="note">No factor_breakdown on this row.</div>}
        {rows.map((f) => (
          <div key={f.name} className="drop" style={{ borderLeftColor: "var(--cyan)" }}>
            <div className="dt">
              <div className="dsym">{f.name}</div>
              <div className="dbull">{f.score.toFixed(1)}</div>
            </div>
            <div className="dreason">
              weight {f.weight}
              {f.note ? ` · ${f.note}` : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
