import { useHeartbeat } from './hooks/useHeartbeat';
import { useAppStore } from './stores/appStore';
import CognitivePipeline from './components/CognitivePipeline';
import PicksTable from './components/PicksTable';

export default function App() {
  useHeartbeat();
  const connected = useAppStore((s) => s.connected);

  return (
    <div className="mx-auto max-w-[1400px] px-7 pt-7 pb-16">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-[18px] mb-7">
        <div>
          <h1 className="mb-1.5 text-[22px] font-semibold tracking-[-0.01em] text-fg">
            Cognitive Pipeline — Quantum Ensemble Picks
          </h1>
          <p className="max-w-[560px] text-[13.5px] leading-relaxed text-muted">
            Eight-stage inference pipeline for futures, equities, and crypto, ending in
            provenance-tagged, ranked picks. All prices, signals, and filings below are synthetic
            demo data for illustrating the interface — not live market data or investment advice.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1.5 font-mono text-[11.5px] text-muted">
          <span
            className="heartbeat-dot h-[7px] w-[7px] rounded-full"
            style={{
              background: connected ? '#33C77E' : '#4B5768',
              boxShadow: connected ? '0 0 0 3px rgba(51,199,126,0.14)' : 'none',
            }}
          />
          {connected ? 'LIVE HEARTBEAT — SYNTHETIC DATA' : 'CONNECTING — SYNTHETIC DATA'}
        </div>
      </header>

      <CognitivePipeline />
      <PicksTable />

      <footer className="mt-[34px] border-t border-line pt-4 font-mono text-[11px] leading-relaxed text-dim">
        Stage order: INGESTION → SNN ENCODING → KRONOS → MIROFISH → QUANTUM ENSEMBLE →
        FUNDAMENTAL AGENT → ALPHA SCREENING → RECOMMENDED PICKS.
        <br />
        Click any row to expand its per-engine breakdown. Conviction is the ensemble-weighted
        agreement score across all five engines, 0–100.
      </footer>
    </div>
  );
}
