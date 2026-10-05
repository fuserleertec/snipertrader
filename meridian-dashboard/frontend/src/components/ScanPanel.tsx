import type { ScanRow } from '../types';
import { fmtPct, fmtPx, signClass } from '../lib/format';

interface ScanPanelProps {
  rows: ScanRow[];
  active: string;
  onPick: (symbol: string) => void;
  error: string | null;
}

function Spark({ values, up }: { values: number[]; up: boolean }) {
  if (values.length < 2) return <svg className="spark" viewBox="0 0 72 22" />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const d = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 72;
      const y = 20 - ((value - min) / span) * 18;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg className={`spark ${up ? 'up' : 'down'}`} viewBox="0 0 72 22" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export function ScanPanel({ rows, active, onPick, error }: ScanPanelProps) {
  const ranked = [...rows].sort((a, b) => Math.abs(b.changePct ?? -1) - Math.abs(a.changePct ?? -1));
  return (
    <section className="panel scan-panel">
      <div className="panel-h">
        <span>Scan</span>
        <span className="panel-meta">{rows.length ? `${rows.length} names` : 'US book'}</span>
      </div>
      <div className="scan-list" role="listbox" aria-label="Equity scan">
        {error && !rows.length ? <p className="empty">{error}</p> : null}
        {!error && !rows.length ? <p className="empty">Loading the book…</p> : null}
        {ranked.map((row) => {
          const tone = signClass(row.changePct);
          return (
            <button
              key={row.symbol}
              type="button"
              role="option"
              aria-selected={row.symbol === active}
              className={row.symbol === active ? 'scan-row on' : 'scan-row'}
              onClick={() => onPick(row.symbol)}
            >
              <span className="scan-id">
                <b>{row.symbol}</b>
                <small>{row.name}</small>
              </span>
              <Spark values={row.spark} up={(row.changePct ?? 0) >= 0} />
              <span className="scan-px">{fmtPx(row.last)}</span>
              <span className={`scan-chg ${tone}`}>{fmtPct(row.changePct)}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
