"use client";

import { ANCHORS, sessionsForAsset } from "@/lib/constants";
import type { AnchorType, AssetClass, SessionType, SignalKind, VWAPValues } from "@/lib/types";
import type { SessionLevels } from "@/lib/types";

const KIND_LABEL: Record<SignalKind, string> = {
  setup: "Setups",
  fvg: "FVGs",
  sweep: "Sweeps",
};

export function Sidebar({
  assetClass,
  anchor,
  onAnchor,
  visibleSessions,
  onToggleSession,
  signalKinds,
  onToggleKind,
  vwap,
  sessionBooks,
  open,
}: {
  assetClass: AssetClass;
  anchor: AnchorType;
  onAnchor: (a: AnchorType) => void;
  visibleSessions: SessionType[];
  onToggleSession: (s: SessionType) => void;
  signalKinds: SignalKind[];
  onToggleKind: (k: SignalKind) => void;
  vwap: VWAPValues | null;
  sessionBooks: SessionLevels[];
  open: boolean;
}) {
  const available = sessionsForAsset(assetClass);

  return (
    <aside className={`dash-sidebar ${open ? "open" : ""}`}>
      <section>
        <h3>VWAP anchor</h3>
        <div className="choice-col">
          {ANCHORS.map((a) => (
            <label key={a}>
              <input
                type="radio"
                name="anchor"
                checked={anchor === a}
                onChange={() => onAnchor(a)}
              />
              {a}
            </label>
          ))}
        </div>
        {vwap && (
          <dl className="stats">
            <div>
              <dt>vwap</dt>
              <dd>{fmt(vwap.vwap)}</dd>
            </div>
            <div>
              <dt>sigma</dt>
              <dd>{fmt(vwap.sigma)}</dd>
            </div>
            <div>
              <dt>n_obs</dt>
              <dd>{vwap.n_obs}</dd>
            </div>
            <div>
              <dt>cum_volume</dt>
              <dd>{vwap.cum_volume.toFixed(1)}</dd>
            </div>
          </dl>
        )}
      </section>

      <section>
        <h3>Session levels</h3>
        <div className="choice-col">
          {available.map((s) => (
            <label key={s}>
              <input
                type="checkbox"
                checked={visibleSessions.includes(s)}
                onChange={() => onToggleSession(s)}
              />
              {s}
            </label>
          ))}
        </div>
        {sessionBooks
          .filter((b) => visibleSessions.includes(b.session_type))
          .map((b) => (
            <dl key={b.session_type} className="stats tight">
              <div className="span">
                <dt>{b.session_type}</dt>
                <dd>O {fmt(b.open)}</dd>
              </div>
              <div>
                <dt>H</dt>
                <dd>{fmt(b.high)}</dd>
              </div>
              <div>
                <dt>L</dt>
                <dd>{fmt(b.low)}</dd>
              </div>
              <div>
                <dt>C</dt>
                <dd>{fmt(b.close)}</dd>
              </div>
            </dl>
          ))}
      </section>

      <section>
        <h3>Signals</h3>
        <div className="choice-col">
          {(Object.keys(KIND_LABEL) as SignalKind[]).map((k) => (
            <label key={k}>
              <input
                type="checkbox"
                checked={signalKinds.includes(k)}
                onChange={() => onToggleKind(k)}
              />
              {KIND_LABEL[k]}
            </label>
          ))}
        </div>
        <p className="hint">
          Mock feed until Quant Risk Pre-Filter lands. Frames are setup_signal / fvg_zone /
          sweep_event.
        </p>
      </section>
    </aside>
  );
}

function fmt(n: number): string {
  return n >= 1000 ? n.toFixed(2) : n.toFixed(3);
}
