import type { AssetClass, CategorizedPickItem, EnsemblePickItem, RankComponents, Signal } from "../types";
import { mockQuote, universeName } from "./lists";

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
  tooltip: string;
  mode: "market" | "activity";
  category: string;
  source: string;
  latency: string;
  id: string | null;
  trigger_event_ids: string[];
}

export function formatRankComponents(rc: RankComponents): string {
  return `sq ${rc.setup_quality.toFixed(1)} · confluence ${rc.confluence.toFixed(1)} · kz ${rc.kill_zone.toFixed(1)} · vol ${rc.volume.toFixed(1)} · fresh ${rc.freshness.toFixed(1)}`;
}

/** Native `title` text for QEP ensemble rows (rank_components + contributing_factors). */
export function ensembleFeatureTooltip(item: EnsemblePickItem): string {
  const conf = item.best_confidence ?? item.confidence;
  const score = item.ensemble_score ?? item.score;
  const lines = [`ensemble_score ${score.toFixed(1)} · confidence ${conf.toFixed(3)}`];
  if (item.rank_components) {
    lines.push(`rank_components  ${formatRankComponents(item.rank_components)}`);
  }
  if (item.contributing_factors?.length) {
    lines.push(`contributing_factors  ${item.contributing_factors.join(" · ")}`);
  }
  if (item.category) lines.push(`category  ${item.category}`);
  return lines.join("\n");
}

export const ENGINE_META: Record<EngineId, { label: string; color: string }> = {
  K: { label: "Kronos", color: "var(--qep-k)" },
  S: { label: "SNN", color: "var(--qep-s)" },
  M: { label: "MiroFish", color: "var(--qep-m)" },
  F: { label: "Fundamental", color: "var(--qep-f)" },
  Q: { label: "Quantum", color: "var(--qep-q)" },
};

export const ENGINE_ORDER: EngineId[] = ["K", "S", "M", "F", "Q"];

export const QEP_CATS: Record<"market" | "activity", string[]> = {
  market: ["All", "Futures", "Stocks", "Cryptos"],
  activity: ["All", "Insiders", "Executives"],
};

export const NARRATIVES = [
  { icon: "💰", title: "Fed Rate-Cut Expectations", impact: "+2.3% on Tech · Probability: 78%", body: "82% of agents repositioning" },
  { icon: "🚀", title: "AI Sector Revolution", impact: "+4.1% on Semis · Probability: 65%", body: "Kronos: Breakout confirmed (89%)" },
  { icon: "⚠️", title: "Geopolitical Tensions", impact: "-1.2% on Energy · Probability: 23%", body: "Volatility injection +15% VIX" },
];

export interface ReconPick {
  symbol: string;
  cap: string;
  category: string | null;
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

export function reconFromCategorized(row: CategorizedPickItem): ReconPick {
  const t = tierOf(row.score);
  return {
    symbol: row.symbol,
    cap: row.asset_class === "futures" ? "fut" : row.asset_class === "crypto" ? "crypto" : "mid",
    category: row.category,
    tier: t === "drop" ? "watch" : t,
    score: row.score,
    entry: row.entry,
    stop: row.stop,
    target: row.target,
    atr: row.atr,
    rewardRisk: row.reward_risk,
    triggers: row.contributing_factors?.length
      ? row.contributing_factors
      : row.setup_types.length
        ? row.setup_types
        : row.category
          ? [row.category]
          : [],
    note: `${universeName(row.symbol)} · category ${row.category ?? "null"} · score ${row.score.toFixed(0)}/100`,
    dropped: t === "drop",
  };
}

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

/** P0 conviction ← ensemble_score (0–100). Fallback: setup_signals.confidence. */
export function convictionOf(signal: Signal): number {
  if (typeof signal.ensemble_score === "number" && Number.isFinite(signal.ensemble_score)) {
    return Math.round(signal.ensemble_score);
  }
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
  if (signal.setup_type === "sweep_reclaim" || signal.setup_type === "po3_judas") base.S = dir;
  if (signal.setup_type === "fvg_entry") base.S = dir;
  if (signal.setup_type === "sd_extension_fade") base.S = dir;
  if (signal.confidence < 0.7) base.M = signal.setup_type === "avwap_ob_confluence" ? opp : "hold";
  return base;
}

export function whyForSetup(signal: Signal): string {
  const ids = signal.trigger_event_ids.join(", ") || "none";
  return `${signal.setup_type.replaceAll("_", " ")} ${signal.side.toUpperCase()} chart join id ${signal.id} + trigger_event_ids: ${ids}.`;
}

function classCategory(asset: AssetClass): string {
  if (asset === "futures") return "Futures";
  if (asset === "equity") return "Stocks";
  return "Cryptos";
}

/** Map GET /picks/ensemble items onto the locked QEP table columns. */
export function presentEnsemble(item: EnsemblePickItem, mode: "market" | "activity", cycle = 0): EnsemblePick {
  const quote = mockQuote(item.symbol, cycle);
  const conv = item.ensemble_score != null ? Math.round(item.ensemble_score) : 0;
  const signal: "Buy" | "Sell" | "Hold" = conv >= 70 ? "Buy" : conv <= 45 ? "Sell" : "Hold";
  const setup = item.setup_types[0] ?? "sweep_reclaim";
  const fake: Signal = {
    id: item.id ?? `ens_${item.symbol}`,
    ts_ms: 0,
    symbol: item.symbol,
    asset_class: item.asset_class,
    setup_type: setup,
    side: signal === "Sell" ? "short" : "long",
    entry: quote.last,
    stop: quote.last * 0.99,
    target: quote.target,
    status: "ACTIVE",
    confidence: item.confidence,
    timeframe: "5m",
    ref_session: "ny_am",
    trigger_event_ids: item.trigger_event_ids ?? [],
    contributing_factors: item.contributing_factors,
    factor_breakdown: item.factor_breakdown,
    ensemble_score: item.ensemble_score,
    rank_components: item.rank_components,
    category: item.category ?? item.asset_class,
    realized_r: null,
    exit_price: null,
    closed_ts_ms: null,
  };
  const rc = item.rank_components;
  const factorTags = item.contributing_factors?.length ? ` · ${item.contributing_factors.join("+")}` : "";
  const setups = item.setup_types.join(" + ") || "ensemble";
  const why = !rc
    ? `${setups} · ensemble_score ${(item.ensemble_score ?? item.score).toFixed(1)}${factorTags}`
    : mode === "activity"
      ? `rank_components vol ${rc.volume.toFixed(1)} · kz ${rc.kill_zone.toFixed(1)} · freshness ${rc.freshness.toFixed(1)}${factorTags}`
      : `${setups} · sq ${rc.setup_quality.toFixed(1)} · confluence ${rc.confluence.toFixed(1)}${factorTags}`;
  return {
    ticker: item.symbol,
    company: `${universeName(item.symbol)} · ${item.category ?? item.asset_class}`,
    signal,
    last: quote.last >= 1000 ? quote.last.toFixed(1) : quote.last.toFixed(2),
    chg: `${quote.chgPct >= 0 ? "+" : ""}${quote.chgPct.toFixed(2)}%`,
    target: quote.target >= 1000 ? quote.target.toFixed(0) : quote.target.toFixed(2),
    conviction: conv,
    engines: enginesForSetup(fake),
    reason: why,
    tooltip: ensembleFeatureTooltip(item),
    mode,
    category: classCategory(item.category ?? item.asset_class),
    source: "GET /picks/ensemble",
    latency: "15m",
    id: item.id ?? null,
    trigger_event_ids: item.trigger_event_ids ?? [],
  };
}

export function matchesQepCat(pick: EnsemblePick, cat: string): boolean {
  if (cat === "All") return true;
  if (cat === "Insiders" || cat === "Executives") return pick.category === "Stocks";
  return pick.category === cat;
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
