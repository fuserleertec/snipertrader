"use client";

import { ANCHORS, OVERLAY_PRESETS, sessionsForAsset, SETUP_TYPES, SIGNAL_STATUSES } from "@/lib/constants";
import type {
  AnchorType,
  AssetClass,
  OverlayPreset,
  SessionLevels,
  SessionType,
  SetupType,
  SignalStatus,
  VWAPValues,
} from "@/lib/types";

export function Sidebar({
  assetClass,
  anchor,
  onAnchor,
  visibleSessions,
  onToggleSession,
  setupTypes,
  onToggleSetupType,
  statuses,
  onToggleStatus,
  overlayPreset,
  onOverlayPreset,
  vwap,
  sessionBooks,
  open,
}: {
  assetClass: AssetClass;
  anchor: AnchorType;
  onAnchor: (a: AnchorType) => void;
  visibleSessions: SessionType[];
  onToggleSession: (s: SessionType) => void;
  setupTypes: SetupType[];
  onToggleSetupType: (t: SetupType) => void;
  statuses: SignalStatus[];
  onToggleStatus: (s: SignalStatus) => void;
  overlayPreset: OverlayPreset;
  onOverlayPreset: (p: OverlayPreset) => void;
  vwap: VWAPValues | null;
  sessionBooks: SessionLevels[];
  open: boolean;
}) {
  const available = sessionsForAsset(assetClass);

  return (
    <aside className={`dash-sidebar ${open ? "open" : ""}`}>
      <section>
        <h3>Overlay view</h3>
        <div className="choice-col">
          {OVERLAY_PRESETS.map((p) => (
            <label key={p.id}>
              <input
                type="radio"
                name="overlay"
                checked={overlayPreset === p.id}
                onChange={() => onOverlayPreset(p.id)}
              />
              {p.label}
            </label>
          ))}
        </div>
        <p className="hint">
          sweep_reclaim: sweep + MSS. fvg_entry / ob_fvg: FVG (+ overlapping OBs). po3_judas:
          Asia box + extreme sweep (no MSS). Card click highlights trigger_event_ids only.
        </p>
      </section>

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
        <h3>setup_type</h3>
        <div className="choice-col">
          {SETUP_TYPES.map((t) => (
            <label key={t}>
              <input
                type="checkbox"
                checked={setupTypes.includes(t)}
                onChange={() => onToggleSetupType(t)}
              />
              {t}
            </label>
          ))}
        </div>
      </section>

      <section>
        <h3>status</h3>
        <div className="choice-col">
          {SIGNAL_STATUSES.map((s) => (
            <label key={s}>
              <input
                type="checkbox"
                checked={statuses.includes(s)}
                onChange={() => onToggleStatus(s)}
              />
              {s}
            </label>
          ))}
        </div>
        <p className="hint">
          Quant setup/trade signals (post risk-approval). Not raw sweep/FVG streams.
        </p>
      </section>
    </aside>
  );
}

function fmt(n: number): string {
  return n >= 1000 ? n.toFixed(2) : n.toFixed(3);
}
