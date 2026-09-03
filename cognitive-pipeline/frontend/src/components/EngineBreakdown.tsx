import type { Pick, Signal } from '../types';
import { ENGINE_ORDER, ENGINE_META, engineScore, metricText, STANCE_COLOR, STANCE_DIM } from '../lib/engines';
import type { Stance } from '../types';

const STANCE_BADGE: Record<Stance, Signal> = { buy: 'Buy', sell: 'Sell', hold: 'Hold' };

export default function EngineBreakdown({ pick }: { pick: Pick }) {
  return (
    <div className="grid grid-cols-2 gap-3.5 px-[22px] py-5 md:grid-cols-3 xl:grid-cols-5">
      <div className="col-span-full mb-0.5 flex flex-wrap items-center justify-between gap-2.5 border-b border-linesoft pb-3">
        <div>
          <div className="text-[13px] font-semibold text-fg">{pick.ticker} — engine breakdown</div>
          <div className="font-mono text-[11px] text-dim">
            source: {pick.source} · lag: {pick.latency}
          </div>
        </div>
        {pick.activityNote && (
          <div className="font-mono text-[12px] text-hold">{pick.activityNote}</div>
        )}
      </div>

      {ENGINE_ORDER.map((k) => {
        const st = pick.engines[k];
        const meta = ENGINE_META[k];
        const score = engineScore(k, pick);
        return (
          <div key={k} className="rounded-lg border border-line bg-panel px-3 py-[11px]">
            <div className="mb-[7px] flex items-center gap-[7px]">
              <span className="h-2 w-2 shrink-0 rounded-[2px]" style={{ background: meta.color }} />
              <span className="text-[12px] font-semibold text-fg">{meta.label}</span>
              <span
                className="ml-auto rounded-full px-[7px] py-px font-mono text-[9.5px] tracking-[0.03em]"
                style={{ background: STANCE_DIM[st], color: STANCE_COLOR[st] }}
              >
                {STANCE_BADGE[st].toUpperCase()}
              </span>
            </div>
            <div className="my-1 font-mono text-[18px] font-semibold" style={{ color: meta.color }}>
              {score}
            </div>
            <div className="text-[11px] leading-relaxed text-muted">{metricText(k, pick)}</div>
          </div>
        );
      })}
    </div>
  );
}
