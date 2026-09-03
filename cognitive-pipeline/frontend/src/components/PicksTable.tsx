import { Fragment } from 'react';
import { CATEGORIES, useAppStore } from '../stores/appStore';
import { ENGINE_ORDER, ENGINE_META, STANCE_COLOR, STANCE_DIM, STANCE_BORDER } from '../lib/engines';
import type { Mode, Signal } from '../types';
import EngineBreakdown from './EngineBreakdown';

const SIGNAL_STYLE: Record<Signal, { bg: string; color: string }> = {
  Buy: { bg: 'rgba(51,199,126,0.14)', color: '#33C77E' },
  Sell: { bg: 'rgba(240,85,92,0.14)', color: '#F0555C' },
  Hold: { bg: 'rgba(227,169,62,0.14)', color: '#E3A93E' },
};

const MODE_LABEL: Record<Mode, string> = {
  market: 'Market Signals',
  activity: 'Smart Money Activity',
};

const convictionColor = (c: number) => (c >= 70 ? '#33C77E' : c >= 50 ? '#E3A93E' : '#F0555C');

const SUB_ACTIVE: Record<string, { background: string; borderColor: string; color: string }> = {
  All: { background: '#E7ECF2', borderColor: '#E7ECF2', color: '#0A0E13' },
  Buy: { background: '#33C77E', borderColor: '#33C77E', color: '#08120C' },
  Sell: { background: '#F0555C', borderColor: '#F0555C', color: '#1A0505' },
  Hold: { background: '#E3A93E', borderColor: '#E3A93E', color: '#1F1602' },
};

const HEADERS = ['#', 'Asset', 'Signal', 'Last / Chg', 'Target', 'Conviction', 'Engines', 'Why'];

export default function PicksTable() {
  const mode = useAppStore((s) => s.mode);
  const cat = useAppStore((s) => s.cat);
  const sub = useAppStore((s) => s.sub);
  const expanded = useAppStore((s) => s.expanded);
  const picks = useAppStore((s) => s.picks);
  const setMode = useAppStore((s) => s.setMode);
  const setCat = useAppStore((s) => s.setCat);
  const setSub = useAppStore((s) => s.setSub);
  const toggleRow = useAppStore((s) => s.toggleRow);

  const cats = CATEGORIES[mode];
  const rows = picks.filter(
    (p) => p.mode === mode && p.category === cat && (sub === 'All' || p.signal === sub)
  );

  return (
    <section>
      <div className="mb-3.5 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-fg">Quantum Ensemble Picks</h2>
        <span className="font-mono text-[11px] text-dim">
          {rows.length} row{rows.length === 1 ? '' : 's'}
        </span>
      </div>

      {/* mode toggle + legend */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3.5">
        <div className="inline-flex gap-0.5 rounded-lg border border-line bg-panel p-[3px]">
          {(Object.keys(MODE_LABEL) as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded-md px-3.5 py-[7px] text-[12.5px] font-medium transition-colors ${
                mode === m ? 'bg-panelalt text-fg shadow-[inset_0_0_0_1px_#212B36]' : 'text-muted'
              }`}
            >
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>
        <div className="flex gap-3.5 font-mono text-[10.5px] text-muted">
          {ENGINE_ORDER.map((k) => (
            <span key={k}>
              <b style={{ color: ENGINE_META[k].color }}>{k}</b> {ENGINE_META[k].label}
            </span>
          ))}
        </div>
      </div>

      {/* category tabs + sub tabs */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 border-b border-line">
          {cats.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className={`-mb-px border-b-2 px-3.5 py-[9px] text-[13px] transition-colors ${
                cat === c ? 'border-q text-fg' : 'border-transparent text-muted hover:text-fg'
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5">
          {(['All', 'Buy', 'Sell', 'Hold'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSub(s)}
              className="rounded-full border px-[11px] py-[5px] font-mono text-[11px] transition-colors"
              style={
                sub === s
                  ? SUB_ACTIVE[s]
                  : { background: '#111820', borderColor: '#212B36', color: '#7C8AA0' }
              }
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* table */}
      <div className="overflow-hidden rounded-lg border border-line bg-panel">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {HEADERS.map((h, i) => (
                <th
                  key={h}
                  className={`whitespace-nowrap border-b border-line bg-panelalt px-3.5 py-2.5 text-left font-mono text-[10.5px] font-medium tracking-[0.03em] text-dim ${
                    h === 'Why' ? 'hidden md:table-cell' : ''
                  } ${i === 0 ? 'w-[34px]' : ''}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-8 py-8 text-center font-mono text-[12px] text-dim"
                >
                  No rows match this filter.
                </td>
              </tr>
            ) : (
              rows.map((r, i) => (
                <Fragment key={`${r.mode}-${r.category}-${r.ticker}`}>
                  <tr
                    className={`cursor-pointer border-b border-linesoft transition-colors ${
                      expanded === r.ticker ? 'bg-panelalt' : 'hover:bg-panelalt'
                    }`}
                    onClick={() => toggleRow(r.ticker)}
                  >
                    <td
                      className="px-3.5 py-[11px] align-middle"
                      style={expanded === r.ticker ? { boxShadow: 'inset 3px 0 0 #FF6FB0' } : undefined}
                    >
                      <span className="font-mono text-[12px] text-dim">{i + 1}</span>
                    </td>
                    <td className="px-3.5 py-[11px] align-middle">
                      <div className="text-[13.5px] font-semibold tracking-[0.01em] text-fg">
                        {r.ticker}
                      </div>
                      <div className="mt-px text-[11.5px] text-muted">{r.company}</div>
                    </td>
                    <td className="px-3.5 py-[11px] align-middle">
                      <span
                        className="inline-block rounded-full px-[9px] py-[3px] font-mono text-[10.5px] font-semibold tracking-[0.03em]"
                        style={{ background: SIGNAL_STYLE[r.signal].bg, color: SIGNAL_STYLE[r.signal].color }}
                      >
                        {r.signal.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-3.5 py-[11px] align-middle font-mono text-[12.5px] text-fg">
                      {r.last}
                      <br />
                      <span className={r.chg.trim().startsWith('+') ? 'text-buy' : 'text-sell'}>
                        {r.chg}
                      </span>
                    </td>
                    <td className="px-3.5 py-[11px] align-middle font-mono text-[12.5px] text-muted">
                      {r.target}
                    </td>
                    <td className="px-3.5 py-[11px] align-middle">
                      <div className="flex min-w-[120px] items-center gap-2">
                        <div className="h-[5px] flex-1 overflow-hidden rounded-[3px] bg-linesoft">
                          <div
                            className="conviction-fill h-full rounded-[3px]"
                            style={{ width: `${r.conviction}%`, background: convictionColor(r.conviction) }}
                          />
                        </div>
                        <div className="w-[26px] text-right font-mono text-[11px] text-muted">
                          {r.conviction}
                        </div>
                      </div>
                    </td>
                    <td className="px-3.5 py-[11px] align-middle">
                      <div className="flex gap-[3px]">
                        {ENGINE_ORDER.map((k) => {
                          const st = r.engines[k];
                          return (
                            <span
                              key={k}
                              title={`${ENGINE_META[k].label}: ${st}`}
                              className="inline-flex h-[19px] w-[19px] items-center justify-center rounded-[5px] font-mono text-[9.5px] font-semibold"
                              style={{
                                background: STANCE_DIM[st],
                                color: STANCE_COLOR[st],
                                border: `1px solid ${STANCE_BORDER[st]}`,
                              }}
                            >
                              {k}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                    <td className="hidden max-w-[280px] px-3.5 py-[11px] align-middle text-[12.5px] leading-relaxed text-muted md:table-cell">
                      {r.reason}
                    </td>
                  </tr>
                  {expanded === r.ticker && (
                    <tr>
                      <td colSpan={8} className="border-b border-line bg-panelalt p-0">
                        <EngineBreakdown pick={r} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
