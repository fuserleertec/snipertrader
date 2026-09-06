import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isInactiveRow,
  readContributingFactors,
  readEnsembleScore,
  readFactorBreakdown,
  readPublishExplain,
  readRankComponents,
} from "./bind";
import { normalizeCategorizedPicks, normalizeEnsemblePicks } from "./http";
import { normalizeSignal } from "./signals";

describe("publish-only bind lock", () => {
  it("reads ensemble_score 0–100 and rank_components object keys", () => {
    assert.equal(readEnsembleScore(72.4), 72.4);
    assert.equal(readEnsembleScore(101), 100);
    assert.equal(readEnsembleScore(-1), 0);
    assert.equal(readEnsembleScore(undefined), null);
    assert.equal(readRankComponents([{ setup_quality: 1 }]), null);
    assert.deepEqual(readRankComponents({ setup_quality: 40, confluence: 20 }), {
      setup_quality: 40,
      confluence: 20,
      kill_zone: 0,
      volume: 0,
      freshness: 0,
    });
  });

  it("never binds a wire field named factors", () => {
    const src = JSON.stringify({
      isInactiveRow,
      readContributingFactors,
      readFactorBreakdown,
      readPublishExplain,
      readRankComponents,
    });
    assert.equal(src.includes("raw.factors"), false);
    assert.equal(src.includes('["factors"]'), false);
    const row = {
      contributing_factors: ["liquidity_sweep"],
      factors: ["do_not_bind"],
      factor_breakdown: [{ name: "liquidity_sweep", weight: 15, score: 80 }],
    };
    const explain = readPublishExplain(row);
    assert.deepEqual(explain.contributing_factors, ["liquidity_sweep"]);
    assert.equal(explain.factor_breakdown?.[0]?.name, "liquidity_sweep");
  });

  it("filters FactorId enum and drops unknown names", () => {
    assert.deepEqual(readContributingFactors(["liquidity_sweep", "not_a_factor", "fvg"]), [
      "liquidity_sweep",
      "fvg",
    ]);
    assert.deepEqual(
      readFactorBreakdown([
        { name: "mss", weight: 15, score: 20 },
        { name: "nope", weight: 1, score: 1 },
      ]),
      [{ name: "mss", weight: 15, score: 20, note: null }],
    );
  });

  it("prefers ensemble_features over the setup_signals row", () => {
    const explain = readPublishExplain({
      ensemble_score: 10,
      rank_components: { setup_quality: 1 },
      ensemble_features: {
        ensemble_score: 88,
        rank_components: { setup_quality: 36, confluence: 18, kill_zone: 12, volume: 12, freshness: 10 },
      },
    });
    assert.equal(explain.ensemble_score, 88);
    assert.equal(explain.rank_components?.confluence, 18);
  });

  it("skips active_levels===false or skip_reason on picks and signals", () => {
    assert.equal(isInactiveRow({ active_levels: false }), true);
    assert.equal(isInactiveRow({ skip_reason: "no_active_levels" }), true);
    assert.equal(isInactiveRow({ active_levels: true }), false);
    const ens = normalizeEnsemblePicks({
      items: [
        { symbol: "ES", ensemble_score: 90, active_levels: false, setup_types: ["sweep_reclaim"] },
        { symbol: "CL", ensemble_score: 80, skip_reason: "mitigated_only", setup_types: ["fvg_entry"] },
        { symbol: "GC", ensemble_score: 70, category: "futures", setup_types: ["vwap_pullback_cont"] },
      ],
    });
    assert.deepEqual(
      ens?.items.map((i) => i.symbol),
      ["GC"],
    );
    const cats = normalizeCategorizedPicks({
      items: [
        { symbol: "AAPL", category: "equity", score: 80, active_levels: false },
        { symbol: "NVDA", category: "equity", score: 70 },
      ],
    });
    assert.deepEqual(
      cats?.items.map((i) => i.symbol),
      ["NVDA"],
    );
    assert.equal(
      normalizeSignal({
        id: "dead",
        symbol: "ES",
        setup_type: "sweep_reclaim",
        side: "long",
        skip_reason: "no_active_zones",
      }),
      null,
    );
  });
});
