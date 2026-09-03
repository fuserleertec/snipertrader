import { Fragment } from 'react';
import { useAppStore } from '../stores/appStore';
import type { PipelineStage } from '../types';

const STATUS_COLOR: Record<string, string> = {
  Running: '#33C77E',
  Installed: '#7C8AA0',
  Active: '#33C77E',
  Monitoring: '#E3A93E',
  Live: '#33C77E',
};

function StageCard({ stage, final }: { stage: PipelineStage; final: boolean }) {
  const dot = STATUS_COLOR[stage.status] || '#4B5768';
  return (
    <div
      className="relative flex min-h-[186px] flex-[0_0_178px] flex-col gap-2.5 rounded-lg border bg-panel px-[13px] py-3.5"
      style={
        final
          ? {
              borderColor: '#2A3D33',
              background: 'linear-gradient(180deg, rgba(51,199,126,0.07), #111820 60%)',
            }
          : { borderColor: '#212B36' }
      }
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10.5px] text-dim">
          STAGE {String(stage.id).padStart(2, '0')}
        </span>
        <span className="inline-flex items-center gap-1.5 font-mono text-[9.5px] text-muted">
          <span
            className="h-[6px] w-[6px] rounded-full"
            style={{ background: dot, boxShadow: `0 0 0 3px ${dot}24` }}
          />
          {stage.status}
        </span>
      </div>
      <div
        className="text-[13.5px] font-semibold leading-snug"
        style={{ color: final ? '#33C77E' : '#E7ECF2' }}
      >
        {stage.name}
      </div>
      <div className="flex-grow text-[11.5px] leading-relaxed text-muted">{stage.desc}</div>
      <div className="flex flex-col gap-[3px] border-t border-linesoft pt-2">
        <span className="font-mono text-[9px] tracking-[0.04em] text-dim">{stage.plabel}</span>
        <span className="font-mono text-[11px] text-s">{stage.pvalue}</span>
      </div>
    </div>
  );
}

function Connector() {
  return (
    <div className="flex flex-[0_0_26px] items-center justify-center">
      <svg width="26" height="14" viewBox="0 0 26 14">
        <path className="connector-arrow" d="M0 7 H20" stroke="#212B36" strokeWidth="1.5" fill="none" />
        <path d="M15 2 L21 7 L15 12" stroke="#212B36" strokeWidth="1.5" fill="none" />
      </svg>
    </div>
  );
}

export default function CognitivePipeline() {
  const stages = useAppStore((s) => s.pipelineStages);
  return (
    <section className="mb-10">
      <div className="mb-3.5 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-fg">Pipeline flow</h2>
        <span className="font-mono text-[11px] text-dim">{stages.length} stages · left to right</span>
      </div>
      <div className="flex items-stretch overflow-x-auto pb-2.5">
        {stages.map((s, i) => (
          <Fragment key={s.id}>
            <StageCard stage={s} final={i === stages.length - 1} />
            {i < stages.length - 1 && <Connector />}
          </Fragment>
        ))}
      </div>
    </section>
  );
}
