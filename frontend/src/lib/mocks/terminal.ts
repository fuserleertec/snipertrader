import type { Signal } from "../types";

export type EngineId = "K" | "S" | "M" | "F" | "Q";
export type Stance = "buy" | "sell" | "hold";
export type QepMode = "market" | "activity" | "setups";

export interface EnsemblePick {
  ticker: string;
  company: string;
  signal: "Buy" | "Sell" | "Hold";
  last: string;
  chg: string;
  target: string;
  conviction: number;
  engines: Record<EngineId, Stance>;
  reason: string;
  mode: "market" | "activity";
  category: string;
  source: string;
  latency: string;
}

export const ENGINE_META: Record<EngineId, { label: string; color: string }> = {
  K: { label: "Kronos", color: "var(--qep-k)" },
  S: { label: "SNN", color: "var(--qep-s)" },
  M: { label: "MiroFish", color: "var(--qep-m)" },
  F: { label: "Fundamental", color: "var(--qep-f)" },
  Q: { label: "Quantum", color: "var(--qep-q)" },
};

export const ENGINE_ORDER: EngineId[] = ["K", "S", "M", "F", "Q"];

/** Compact subset of the live stock_picks.html Quantum Ensemble table. */
export const ENSEMBLE_PICKS: EnsemblePick[] = [
  { ticker: "ES", company: "E-mini S&P 500", signal: "Buy", last: "5,812.25", chg: "+0.64%", target: "5,910", conviction: 81, engines: { K: "buy", S: "buy", M: "buy", F: "hold", Q: "buy" }, reason: "Breadth is broadening into cyclicals while SNN clocks a volume spike on the reopen; fundamentals lag but don't contradict.", mode: "market", category: "Futures", source: "CME ITCH", latency: "6ms" },
  { ticker: "CL", company: "WTI Crude", signal: "Sell", last: "76.40", chg: "-1.12%", target: "71.50", conviction: 74, engines: { K: "sell", S: "sell", M: "sell", F: "buy", Q: "sell" }, reason: "Kronos and MiroFish both read a rollover pattern into a demand-softening macro print.", mode: "market", category: "Futures", source: "NYMEX", latency: "9ms" },
  { ticker: "NQ", company: "Nasdaq 100", signal: "Buy", last: "20,904.00", chg: "+0.88%", target: "21,300", conviction: 77, engines: { K: "buy", S: "buy", M: "hold", F: "buy", Q: "buy" }, reason: "Momentum in mega-cap tech is confirmed by both temporal and pattern models.", mode: "market", category: "Futures", source: "CME ITCH", latency: "6ms" },
  { ticker: "NVDA", company: "NVIDIA Corp", signal: "Buy", last: "132.18", chg: "+2.14%", target: "148.00", conviction: 88, engines: { K: "buy", S: "buy", M: "buy", F: "buy", Q: "buy" }, reason: "Every engine agrees: accelerating data-center demand, a breakout analogue, and a fundamentals beat.", mode: "market", category: "Stocks", source: "NASDAQ", latency: "4ms" },
  { ticker: "AAPL", company: "Apple Inc", signal: "Hold", last: "221.40", chg: "-0.22%", target: "228.00", conviction: 48, engines: { K: "hold", S: "sell", M: "hold", F: "hold", Q: "hold" }, reason: "Sideways price action with only MiroFish leaning bearish on a stalled-breakout analogue.", mode: "market", category: "Stocks", source: "NASDAQ", latency: "4ms" },
  { ticker: "TSLA", company: "Tesla Inc", signal: "Sell", last: "214.60", chg: "-3.05%", target: "192.00", conviction: 72, engines: { K: "sell", S: "sell", M: "buy", F: "sell", Q: "sell" }, reason: "Delivery-miss chatter plus a sharp SNN volume spike outweigh a lone bullish read.", mode: "market", category: "Stocks", source: "NASDAQ", latency: "4ms" },
  { ticker: "BTC", company: "Bitcoin", signal: "Buy", last: "61,240", chg: "+3.42%", target: "67,500", conviction: 83, engines: { K: "buy", S: "buy", M: "buy", F: "hold", Q: "buy" }, reason: "ETF inflows plus a textbook accumulation-to-breakout analogue.", mode: "market", category: "Cryptos", source: "Coinbase", latency: "11ms" },
  { ticker: "ETH", company: "Ethereum", signal: "Hold", last: "2,940", chg: "+0.61%", target: "3,050", conviction: 55, engines: { K: "hold", S: "hold", M: "buy", F: "hold", Q: "hold" }, reason: "Range-bound with a mild bullish tilt from MiroFish only.", mode: "market", category: "Cryptos", source: "Coinbase", latency: "11ms" },
  { ticker: "SOL", company: "Solana", signal: "Buy", last: "148.20", chg: "+4.87%", target: "172.00", conviction: 79, engines: { K: "buy", S: "buy", M: "buy", F: "hold", Q: "buy" }, reason: "Network activity and a steep SNN spike both confirm continuation.", mode: "market", category: "Cryptos", source: "Coinbase", latency: "11ms" },
  { ticker: "MSFT", company: "Microsoft Corp", signal: "Buy", last: "438.20", chg: "+0.52%", target: "465.00", conviction: 74, engines: { K: "buy", S: "hold", M: "buy", F: "buy", Q: "buy" }, reason: "A director's open-market purchase lines up with a bullish pattern read.", mode: "activity", category: "Insiders", source: "Form 4", latency: "2h" },
  { ticker: "PLTR", company: "Palantir Technologies", signal: "Buy", last: "41.15", chg: "+2.88%", target: "47.50", conviction: 69, engines: { K: "buy", S: "buy", M: "hold", F: "hold", Q: "buy" }, reason: "CEO added shares alongside a fresh SNN volume spike on the filing date.", mode: "activity", category: "Insiders", source: "Form 4", latency: "1h" },
  { ticker: "META", company: "Meta Platforms", signal: "Buy", last: "512.40", chg: "+1.22%", target: "545.00", conviction: 72, engines: { K: "buy", S: "hold", M: "buy", F: "buy", Q: "buy" }, reason: "CFO's scheduled 10b5-1 buy coincides with an ad-revenue beat.", mode: "activity", category: "Executives", source: "10b5-1 filing", latency: "4h" },
];

export const QEP_CATS: Record<"market" | "activity", string[]> = {
  market: ["Futures", "Stocks", "Cryptos"],
  activity: ["Insiders", "Executives"],
};

export const NARRATIVES = [
  { icon: "⚡", title: "CPI surprise", impact: "Swarm bias −0.35 · vol +18%", body: "Hot print would rotate swarm cells bearish into duration-sensitive names." },
  { icon: "🏦", title: "FOMC hold", impact: "Swarm bias +0.20 · vol −8%", body: "A hold-and-guide-lower path lifts risk-on analogues Kronos already has on tape." },
  { icon: "🛢️", title: "Crude inventory draw", impact: "Energy +12% cone", body: "Illustrative shock: energy leaders gain Ultra-High conviction if draw exceeds 4mm." },
  { icon: "🛰️", title: "ETF flow spike", impact: "Crypto +0.40 bias", body: "MiroFish treats a 3-day inflow cluster as a continuation analogue, not a reversal." },
];

export const GLOSSARY = [
  { title: "Kronos", body: "Temporal / structural engine. Reads session VWAP, FVG, order blocks, sweeps, and MSS on the K-line.", perf: "Walk-forward hit 61%" },
  { title: "SNN", body: "Spike / regime detector. Flags volume and volatility shocks versus a trailing baseline.", perf: "Regime recall 0.74" },
  { title: "MiroFish", body: "Pattern swarm. 80 agents vote Bullish / Neutral / Bearish into the heatmap.", perf: "Swarm κ 0.68" },
  { title: "Fundamental", body: "Filings and catalyst scorer (Form 4, 10b5-1, EPS surprise).", perf: "Precision 0.58" },
  { title: "Quantum", body: "Weighted resolver. Collapses the four votes into a 0–100 conviction.", perf: "Brier 0.19" },
  { title: "FVG / OB / Sweep / MSS", body: "Rev 1.1 overlays joined to setup_signals.trigger_event_ids. Cards highlight the matching zones.", perf: "schema 1.1" },
];

export function convictionOf(signal: Signal): number {
  return Math.round(signal.confidence * 100);
}

export function tierOf(conviction: number): "ultra" | "high" | "watch" | "drop" {
  if (conviction >= 88) return "ultra";
  if (conviction >= 78) return "high";
  if (conviction >= 65) return "watch";
  return "drop";
}

export function enginesForSetup(signal: Signal): Record<EngineId, Stance> {
  const dir: Stance = signal.side === "long" ? "buy" : "sell";
  const opp: Stance = dir === "buy" ? "sell" : "buy";
  const base: Record<EngineId, Stance> = { K: dir, S: "hold", M: dir, F: "hold", Q: dir };
  if (signal.setup_type.includes("sweep") || signal.setup_type === "po3_judas") base.S = dir;
  if (signal.setup_type === "order_block") base.F = "hold";
  if (signal.confidence < 0.7) base.M = signal.setup_type === "mss_break" ? opp : "hold";
  return base;
}

export function whyForSetup(signal: Signal): string {
  const ids = signal.trigger_event_ids.join(", ") || "no trigger ids";
  return `${signal.setup_type.replaceAll("_", " ")} ${signal.side.toUpperCase()} joined via trigger_event_ids: ${ids}.`;
}

export function swarmCells(seed: string, bias: number): Array<"bull" | "neu" | "bear"> {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  const cells: Array<"bull" | "neu" | "bear"> = [];
  for (let i = 0; i < 80; i++) {
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    const r = ((h >>> 0) / 4294967296) + bias * 0.18;
    cells.push(r > 0.62 ? "bull" : r < 0.38 ? "bear" : "neu");
  }
  return cells;
}

export function scenarioCones(conviction: number, side: "long" | "short"): { bull: number; base: number; bear: number } {
  const edge = Math.min(70, Math.max(20, conviction - 10));
  if (side === "long") {
    const bull = edge;
    const bear = Math.max(8, 100 - edge - 28);
    return { bull, bear, base: 100 - bull - bear };
  }
  const bear = edge;
  const bull = Math.max(8, 100 - edge - 28);
  return { bull, bear, base: 100 - bull - bear };
}
