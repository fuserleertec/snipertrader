import type { EngineKey, Pick, Stance } from '../types';

export interface EngineMeta {
  key: EngineKey;
  label: string;
  color: string;
  role: string;
}

export const ENGINE_META: Record<EngineKey, EngineMeta> = {
  K: { key: 'K', label: 'Kronos', color: '#5FA8FF', role: 'Temporal forecast' },
  S: { key: 'S', label: 'SNN', color: '#33C2B8', role: 'Spike / regime detector' },
  M: { key: 'M', label: 'MiroFish', color: '#A98BFF', role: 'Pattern match' },
  F: { key: 'F', label: 'Fundamental Agent', color: '#E3A93E', role: 'Fundamentals cross-check' },
  Q: { key: 'Q', label: 'Quantum Ensemble', color: '#FF6FB0', role: 'Weighted resolver' },
};

export const ENGINE_ORDER: EngineKey[] = ['K', 'S', 'M', 'F', 'Q'];

export const STANCE_COLOR: Record<Stance, string> = {
  buy: '#33C77E',
  sell: '#F0555C',
  hold: '#E3A93E',
};

export const STANCE_DIM: Record<Stance, string> = {
  buy: 'rgba(51,199,126,0.14)',
  sell: 'rgba(240,85,92,0.14)',
  hold: 'rgba(227,169,62,0.14)',
};

export const STANCE_BORDER: Record<Stance, string> = {
  buy: 'rgba(51,199,126,0.35)',
  sell: 'rgba(240,85,92,0.35)',
  hold: 'rgba(227,169,62,0.35)',
};

export function engineScore(key: EngineKey, p: Pick): number {
  let v: number;
  switch (key) {
    case 'K':
      v = 50 + p.drift * 4;
      break;
    case 'S':
      v = 50 + p.sigma * 8;
      break;
    case 'M':
      v = p.similarity;
      break;
    case 'F':
      v = 50 + p.epsSurprise * 3;
      break;
    case 'Q':
      v = p.conviction;
      break;
  }
  return Math.max(1, Math.min(99, Math.round(v)));
}

export function metricText(key: EngineKey, p: Pick): string {
  switch (key) {
    case 'K':
      return `Forecasts ${p.drift >= 0 ? '+' : ''}${p.drift}% drift over the pipeline horizon.`;
    case 'S':
      return `Flags a ${p.sigma}σ spike vs. the trailing baseline.`;
    case 'M':
      return `${p.similarity}% match against a historical analogue pattern.`;
    case 'F':
      return `${p.epsSurprise >= 0 ? 'Beats' : 'Misses'} consensus by ${Math.abs(
        p.epsSurprise
      )}% on the latest print.`;
    case 'Q':
      return `Resolves ${p.conviction}/100 conviction after weighting all four inputs.`;
  }
}
