import type { FactorBreakdown, FactorId, SetupType } from "./types";

/** PR #9 locked factor ids. Labels only — chart join is id + trigger_event_ids. */
export const STABLE_FACTORS = [
  "liquidity_sweep",
  "mss",
  "fvg",
  "order_block",
  "vwap_reclaim",
  "vwap_band_extension",
  "vwap_pullback",
  "first_touch",
  "low_volume",
  "volume_confirm",
  "rejection_candle",
  "engulfing",
  "avwap",
  "htf_ob",
  "kill_zone",
  "multi_pattern",
  "trend_align",
] as const satisfies readonly FactorId[];

export const FACTOR_WEIGHTS: Record<FactorId, number> = {
  liquidity_sweep: 15,
  mss: 15,
  fvg: 15,
  order_block: 15,
  vwap_reclaim: 15,
  vwap_band_extension: 20,
  vwap_pullback: 15,
  first_touch: 10,
  low_volume: 10,
  volume_confirm: 10,
  rejection_candle: 15,
  engulfing: 10,
  avwap: 20,
  htf_ob: 20,
  kill_zone: 10,
  multi_pattern: 10,
  trend_align: 15,
};

export const FACTOR_NOTES: Record<FactorId, string> = {
  liquidity_sweep: "Session high/low sweep (chart via trigger_event_ids)",
  mss: "Market-structure shift (chart via trigger_event_ids)",
  fvg: "Fair-value gap at the entry zone",
  order_block: "Order block overlapping the entry zone",
  vwap_reclaim: "Close reclaimed session VWAP",
  vwap_band_extension: "Session VWAP ±2σ/±3σ extension",
  vwap_pullback: "Pullback into session VWAP or ±1σ",
  first_touch: "First clean VWAP touch in the lookback window",
  low_volume: "Bar volume below the tunable average fraction",
  volume_confirm: "Volume / delta confirmation",
  rejection_candle: "Rejection candle (pin / hammer / shooting star)",
  engulfing: "Engulfing confirmation with the setup",
  avwap: "Anchored VWAP line (Phase 2 nested bands)",
  htf_ob: "Higher-timeframe order block confluence",
  kill_zone: "Active kill-zone window",
  multi_pattern: "More than one setup fired same symbol+side",
  trend_align: "Price aligned with rising/falling session VWAP",
};

const FACTOR_SET = new Set<string>(STABLE_FACTORS);

export function isFactorId(value: string): value is FactorId {
  return FACTOR_SET.has(value);
}

/** ML publish-only: scale row scores so sum(score) ≈ conviction 0–100. */
export function explain(names: FactorId[], conviction: number): {
  contributing_factors: FactorId[];
  factor_breakdown: FactorBreakdown[];
} {
  const seen = new Set<FactorId>();
  const rows: FactorBreakdown[] = [];
  for (const name of names) {
    if (seen.has(name)) continue;
    seen.add(name);
    rows.push({
      name,
      weight: FACTOR_WEIGHTS[name],
      score: FACTOR_WEIGHTS[name],
      note: FACTOR_NOTES[name],
    });
  }
  const target = Math.max(0, Math.min(100, conviction));
  if (rows.length) {
    const total = rows.reduce((s, r) => s + r.score, 0);
    const scale = total > 0 ? target / total : target / rows.length;
    for (const row of rows) row.score = Math.round(row.score * scale * 100) / 100;
    const drift = Math.round((target - rows.reduce((s, r) => s + r.score, 0)) * 100) / 100;
    rows[rows.length - 1].score = Math.round((rows[rows.length - 1].score + drift) * 100) / 100;
  }
  return { contributing_factors: [...seen], factor_breakdown: rows };
}

export function factorsForSetup(setup: SetupType): FactorId[] {
  if (setup === "sweep_reclaim") return ["liquidity_sweep", "mss", "vwap_reclaim"];
  if (setup === "fvg_entry") return ["fvg", "vwap_reclaim"];
  if (setup === "ob_fvg") return ["fvg", "order_block", "vwap_reclaim"];
  if (setup === "po3_judas") return ["liquidity_sweep", "kill_zone"];
  if (setup === "sd_extension_fade") return ["vwap_band_extension", "low_volume", "rejection_candle"];
  if (setup === "vwap_pullback_cont") {
    return ["trend_align", "vwap_pullback", "order_block", "first_touch", "engulfing"];
  }
  return ["avwap", "htf_ob", "rejection_candle"];
}
