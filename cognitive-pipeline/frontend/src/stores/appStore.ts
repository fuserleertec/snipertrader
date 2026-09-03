import { create } from 'zustand';
import type { HeartbeatPayload, Mode, Pick } from '../types';
import seed from '../data/seed.json';

export const CATEGORIES: Record<Mode, string[]> = {
  market: ['Futures', 'Stocks', 'Cryptos'],
  activity: ['Insiders', 'Executives', 'Whales', 'Gov'],
};

const seedPayload = seed as unknown as HeartbeatPayload;

interface AppState {
  pipelineStages: HeartbeatPayload['pipelineStages'];
  picks: Pick[];
  vetoes: unknown[];
  connected: boolean;
  lastHeartbeat: string | null;
  mode: Mode;
  cat: string;
  sub: string;
  expanded: string | null;
  setHeartbeat: (p: HeartbeatPayload) => void;
  setConnected: (c: boolean) => void;
  setMode: (m: Mode) => void;
  setCat: (c: string) => void;
  setSub: (s: string) => void;
  toggleRow: (ticker: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  pipelineStages: seedPayload.pipelineStages,
  picks: seedPayload.picks,
  vetoes: seedPayload.vetoes ?? [],
  connected: false,
  lastHeartbeat: null,
  mode: 'market',
  cat: 'Futures',
  sub: 'All',
  expanded: null,

  setHeartbeat: (p) =>
    set({
      pipelineStages: p.pipelineStages,
      picks: p.picks,
      vetoes: p.vetoes ?? [],
      lastHeartbeat: p.timestamp,
    }),
  setConnected: (c) => set({ connected: c }),
  setMode: (m) => set({ mode: m, cat: CATEGORIES[m][0], sub: 'All', expanded: null }),
  setCat: (c) => set({ cat: c, expanded: null }),
  setSub: (s) => set({ sub: s, expanded: null }),
  toggleRow: (ticker) => set((s) => ({ expanded: s.expanded === ticker ? null : ticker })),
}));
