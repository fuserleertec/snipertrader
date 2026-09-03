export type Signal = 'Buy' | 'Sell' | 'Hold';
export type Stance = 'buy' | 'sell' | 'hold';
export type EngineKey = 'K' | 'S' | 'M' | 'F' | 'Q';
export type Mode = 'market' | 'activity';

export interface PipelineStage {
  id: number;
  name: string;
  desc: string;
  plabel: string;
  pvalue: string;
  status: string;
}

export interface Pick {
  ticker: string;
  company: string;
  signal: Signal;
  last: string;
  chg: string;
  target: string;
  conviction: number;
  engines: Record<EngineKey, Stance>;
  drift: number;
  similarity: number;
  sigma: number;
  epsSurprise: number;
  reason: string;
  source: string;
  latency: string;
  activityNote: string | null;
  mode: Mode;
  category: string;
}

export interface HeartbeatPayload {
  seq?: number;
  timestamp: string;
  pipelineStages: PipelineStage[];
  picks: Pick[];
  vetoes: unknown[];
}
