/**
 * Publish-only Quant / ML field lock (never on POST /risk/validate).
 * Paper / live_trading=false.
 *
 * Prefer Kafka `ensemble_features` @15m; fallback latest `setup_signals`.
 * There is no wire field named `factors`.
 */
import { isFactorId } from "./factors";
import type {
  AssetClass,
  FactorBreakdown,
  FactorId,
  PickCategory,
  RankComponents,
} from "./types";

/** Component max weights — setup_quality / confluence / kill_zone / volume / freshness. */
export const RANK_COMPONENT_MAX = {
  setup_quality: 40,
  confluence: 20,
  kill_zone: 15,
  volume: 15,
  freshness: 10,
} as const;

const RANK_KEYS = ["setup_quality", "confluence", "kill_zone", "volume", "freshness"] as const;

const CATEGORIES = new Set<PickCategory>(["crypto", "equity", "futures"]);

export function isObj(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/** Server skip preferred; FE drops `active_levels===false` or any `skip_reason`. */
export function isInactiveRow(raw: Record<string, unknown>): boolean {
  if (raw.active_levels === false) return true;
  const skip = raw.skip_reason;
  return skip != null && skip !== "";
}

export function readEnsembleScore(raw: unknown): number | null {
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  return Math.max(0, Math.min(100, raw));
}

/** OBJECT only — arrays are rejected. Missing / empty → null. */
export function readRankComponents(raw: unknown): RankComponents | null {
  if (!isObj(raw)) return null;
  const hasAny = RANK_KEYS.some((key) => typeof raw[key] === "number" && Number.isFinite(raw[key]));
  if (!hasAny) return null;
  return {
    setup_quality: finiteOr(raw.setup_quality, 0),
    confluence: finiteOr(raw.confluence, 0),
    kill_zone: finiteOr(raw.kill_zone, 0),
    volume: finiteOr(raw.volume, 0),
    freshness: finiteOr(raw.freshness, 0),
  };
}

export function sumRankComponents(parts: RankComponents): number {
  return +(
    parts.setup_quality +
    parts.confluence +
    parts.kill_zone +
    parts.volume +
    parts.freshness
  ).toFixed(2);
}

export function readContributingFactors(raw: unknown): FactorId[] | null {
  if (raw == null) return null;
  if (!Array.isArray(raw)) return null;
  const out: FactorId[] = [];
  const seen = new Set<FactorId>();
  for (const item of raw) {
    if (typeof item === "string" && isFactorId(item) && !seen.has(item)) {
      seen.add(item);
      out.push(item);
    }
  }
  return out;
}

export function readFactorBreakdown(raw: unknown): FactorBreakdown[] | null {
  if (raw == null) return null;
  if (!Array.isArray(raw)) return null;
  const out: FactorBreakdown[] = [];
  for (const item of raw) {
    if (!isObj(item)) continue;
    const name = typeof item.name === "string" ? item.name : "";
    if (!isFactorId(name)) continue;
    if (typeof item.weight !== "number" || !Number.isFinite(item.weight)) continue;
    if (typeof item.score !== "number" || !Number.isFinite(item.score)) continue;
    out.push({
      name,
      weight: item.weight,
      score: item.score,
      note: typeof item.note === "string" ? item.note : null,
    });
  }
  return out;
}

export function readCategory(raw: unknown): PickCategory | null {
  return typeof raw === "string" && CATEGORIES.has(raw as PickCategory) ? (raw as PickCategory) : null;
}

export function categoryOf(raw: Record<string, unknown>, fallback?: AssetClass): PickCategory | null {
  return readCategory(raw.category) ?? readCategory(raw.asset_class) ?? readCategory(fallback) ?? null;
}

/** Prefer Kafka `ensemble_features`, then the publish row. */
export function readPublishExplain(raw: Record<string, unknown>): {
  ensemble_score: number | null;
  rank_components: RankComponents | null;
  contributing_factors: FactorId[] | null;
  factor_breakdown: FactorBreakdown[] | null;
  category: PickCategory | null;
} {
  const side = isObj(raw.ensemble_features) ? raw.ensemble_features : {};
  return {
    ensemble_score: readEnsembleScore(side.ensemble_score) ?? readEnsembleScore(raw.ensemble_score),
    rank_components: readRankComponents(side.rank_components) ?? readRankComponents(raw.rank_components),
    contributing_factors:
      readContributingFactors(raw.contributing_factors) ?? readContributingFactors(side.contributing_factors),
    factor_breakdown: readFactorBreakdown(raw.factor_breakdown) ?? readFactorBreakdown(side.factor_breakdown),
    category: categoryOf(raw) ?? categoryOf(side),
  };
}

function finiteOr(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
