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
  { ticker: "GC", company: "Gold", signal: "Hold", last: "2,486.10", chg: "+0.18%", target: "2,520", conviction: 52, engines: { K: "hold", S: "hold", M: "buy", F: "hold", Q: "hold" }, reason: "A stalled probe of the overnight high leaves Quantum parked in the middle until the next volatility pulse.", mode: "market", category: "Futures", source: "COMEX", latency: "8ms" },
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
  { icon: "💰", title: "Fed Rate-Cut Expectations", impact: "+2.3% on Tech · Probability: 78%", body: "82% of agents repositioning" },
  { icon: "🚀", title: "AI Sector Revolution", impact: "+4.1% on Semis · Probability: 65%", body: "Kronos: Breakout confirmed (89%)" },
  { icon: "⚠️", title: "Geopolitical Tensions", impact: "-1.2% on Energy · Probability: 23%", body: "Volatility injection +15% VIX" },
];

export interface ReconPick {
  symbol: string;
  cap: string;
  tier: "ultra" | "high" | "watch";
  score: number;
  entry: number;
  stop: number;
  target: number;
  atr: number;
  rewardRisk: number;
  triggers: string[];
  note: string;
  dropped?: boolean;
}

/** Snapshot-shaped picks so section 03/04 match the live terminal density. */
export const FALLBACK_PICKS: ReconPick[] = [
  { symbol: "SMCI", cap: "small", tier: "high", score: 81, entry: 42.1, stop: 36.4, target: 54.0, atr: 2.4, rewardRisk: 2.1, triggers: ["BOS", "FVG"], note: "SMCI conviction 81/100 · chart: BOS/FVG · vol surge 16%" },
  { symbol: "TSM", cap: "large", tier: "high", score: 78, entry: 168.2, stop: 154.0, target: 192.0, atr: 3.1, rewardRisk: 2.0, triggers: ["BOS", "FVG"], note: "TSM conviction 78/100 · chart: BOS/FVG" },
  { symbol: "NVDA", cap: "large", tier: "watch", score: 72, entry: 132.2, stop: 118.0, target: 148.0, atr: 4.2, rewardRisk: 2.1, triggers: ["BREAKOUT", "FVG"], note: "NVDA conviction 72/100 · SEC Form 4 buys: 1 · chart: BREAKOUT/FVG" },
  { symbol: "BE", cap: "small", tier: "watch", score: 69, entry: 11.4, stop: 9.8, target: 14.6, atr: 0.7, rewardRisk: 2.0, triggers: ["FVG"], note: "BE conviction 69/100 · chart: FVG" },
];

export const FALLBACK_DROPPED: ReconPick[] = [
  { symbol: "MSFT", cap: "large", tier: "watch", score: 58, entry: 438.2, stop: 412.0, target: 465.0, atr: 6.1, rewardRisk: 2.0, triggers: [], note: "No pattern · Δ 64% · no conviction · audit — no live levels", dropped: true },
  { symbol: "RIVN", cap: "mid", tier: "watch", score: 42, entry: 14, stop: 12, target: 18, atr: 0.8, rewardRisk: 2, triggers: [], note: "Composite 42/100 below 65 floor · no chart breakout/BOS/FVG", dropped: true },
  { symbol: "SOFI", cap: "mid", tier: "watch", score: 22, entry: 8, stop: 7, target: 10, atr: 0.4, rewardRisk: 2, triggers: [], note: "Composite 22/100 below 65 floor · no SEC Form 4 buys", dropped: true },
  { symbol: "COIN", cap: "mid", tier: "watch", score: 48, entry: 210, stop: 190, target: 240, atr: 8, rewardRisk: 1.5, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "SNOW", cap: "mid", tier: "watch", score: 44, entry: 115, stop: 100, target: 130, atr: 4, rewardRisk: 1.4, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "ASTS", cap: "small", tier: "watch", score: 40, entry: 28, stop: 22, target: 36, atr: 1.6, rewardRisk: 1.3, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "ALB", cap: "mid", tier: "watch", score: 38, entry: 92, stop: 80, target: 110, atr: 3.2, rewardRisk: 1.4, triggers: [], note: "No pattern · Δ 55% · no conviction · audit — no live levels", dropped: true },
  { symbol: "HOOD", cap: "mid", tier: "watch", score: 36, entry: 21, stop: 17, target: 26, atr: 0.9, rewardRisk: 1.3, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "SNAP", cap: "mid", tier: "watch", score: 34, entry: 9.4, stop: 8.1, target: 11.2, atr: 0.4, rewardRisk: 1.2, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "UBER", cap: "large", tier: "watch", score: 46, entry: 72, stop: 64, target: 84, atr: 1.8, rewardRisk: 1.5, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "PYPL", cap: "large", tier: "watch", score: 41, entry: 66, stop: 58, target: 76, atr: 1.5, rewardRisk: 1.4, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "NIO", cap: "mid", tier: "watch", score: 31, entry: 4.8, stop: 3.9, target: 6.1, atr: 0.3, rewardRisk: 1.2, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "PLUG", cap: "small", tier: "watch", score: 28, entry: 2.4, stop: 1.8, target: 3.2, atr: 0.2, rewardRisk: 1.1, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "MARA", cap: "mid", tier: "watch", score: 33, entry: 16.2, stop: 13.4, target: 20.1, atr: 1.1, rewardRisk: 1.3, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "RIOT", cap: "mid", tier: "watch", score: 29, entry: 8.6, stop: 7.1, target: 10.8, atr: 0.6, rewardRisk: 1.2, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
  { symbol: "AMC", cap: "small", tier: "watch", score: 24, entry: 4.1, stop: 3.2, target: 5.4, atr: 0.3, rewardRisk: 1.1, triggers: [], note: "No pattern · no conviction · audit — no live levels", dropped: true },
];

export function simScenario(score: number, atr: number, entry: number, bias = 0) {
  const c = Math.min(0.98, Math.max(0.05, score / 100));
  const e = entry > 0 ? entry : 100;
  const a = atr > 0 ? atr : e * 0.03;
  const drift = (a / e) * 100;
  let bullP = Math.min(0.9, Math.max(0.05, 0.5 + 0.4 * c + bias * 0.15));
  let bearP = Math.min(0.6, Math.max(0.03, 0.12 * (1 - c) + 0.05 + Math.max(0, -bias) * 0.15));
  let baseP = Math.min(0.8, Math.max(0.05, 1 - bullP - bearP));
  const tot = bullP + baseP + bearP;
  bullP /= tot;
  baseP /= tot;
  bearP /= tot;
  return {
    bull: { p: Math.round(bullP * 100), r: +(drift * 2.2).toFixed(1) },
    base: { p: Math.round(baseP * 100), r: +(drift * 0.9).toFixed(1) },
    bear: { p: Math.round(bearP * 100), r: -(drift * 1.8).toFixed(1) },
  };
}

export function scoreLeaderboard(picks: ReconPick[], dropped: ReconPick[]) {
  const all = [...picks, ...dropped.map((d) => ({ ...d, dropped: true }))];
  return all
    .map((p) => {
      const sc = simScenario(p.score, p.atr, p.entry);
      const runUpScore = Math.round(sc.bull.p * 0.6 + 40);
      const dumpScore = Math.round(sc.bear.p * 0.6 + 20);
      const netBias = runUpScore - dumpScore;
      return {
        ...p,
        sc,
        runUpScore,
        dumpScore,
        netBias,
        delta: sc.bull.p - sc.bear.p,
        pattern: p.triggers.length ? p.triggers.join(" + ") : "No pattern",
      };
    })
    .sort((a, b) => b.netBias - a.netBias)
    .slice(0, 20);
}

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
  for (let i = 0; i < 100; i++) {
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
