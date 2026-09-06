"use client";

import { formatRankComponents } from "@/lib/mocks/terminal";
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
  const conviction =
    signal.ensemble_score != null ? signal.ensemble_score : rows.reduce((s, r) => s + r.score, 0);
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
      ensemble_score: signal.ensemble_score,
      rank_components: signal.rank_components,
      category: signal.category,
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
        Publish-only explainability — <code>contributing_factors[]</code> badges,{" "}
        <code>factor_breakdown[]</code> rows. Conviction ← <code>ensemble_score</code>{" "}
        ({conviction.toFixed(0)}). Chart join is <code>id</code> + <code>trigger_event_ids</code>
        {`: ${signal.id}${signal.trigger_event_ids.length ? ` · ${signal.trigger_event_ids.join(", ")}` : ""}`}.
        Never on POST /risk/validate. Paper / live_trading=false.
      </div>
      {signal.rank_components && (
        <div
          className="sec-sub"
          title={[
            `rank_components  ${formatRankComponents(signal.rank_components)}`,
            signal.contributing_factors?.length
              ? `contributing_factors  ${signal.contributing_factors.join(" · ")}`
              : "",
          ]
            .filter(Boolean)
            .join("\n")}
        >
          rank_components · {formatRankComponents(signal.rank_components)}
        </div>
      )}
      <div className="pick-tags" style={{ marginTop: 10 }}>
        {ids.map((id) => (
          <span key={id} className="ptag">
            {id}
          </span>
        ))}
        {signal.category && <span className="ptag">{signal.category}</span>}
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
