import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { LIST_REFRESH_SEC, SETUP_FILTERS, SETUP_TYPES, wireAssetClass } from "./constants";
import { cardsForTab, chartSymbolsForTab, clampRefreshSec, setupFilterType, uniqueSymbols } from "./desk";
import { joinSymbols, normalizeCategorizedPicks, normalizeEnsemblePicks, normalizeUniverseTop, signalListPath } from "./http";
import { mockCategorizedPicks, mockDroppedPicks, mockEnsemblePicks, mockUniverseTop, SETUP_UNIVERSE } from "./mocks/lists";
import { mockListSignals } from "./mocks/signals";
import { normalizeSignal } from "./signals";
import { pinSetupCards } from "./setupView";
import type { Signal } from "./types";

function sig(partial: Partial<Signal> & Pick<Signal, "id" | "setup_type" | "symbol" | "asset_class">): Signal {
  return {
    ts_ms: 1,
    side: "long",
    entry: 100,
    stop: 90,
    target: 120,
    status: "ACTIVE",
    confidence: 0.8,
    timeframe: "5m",
    ref_session: "ny_am",
    trigger_event_ids: [],
    realized_r: null,
    exit_price: null,
    closed_ts_ms: null,
    ...partial,
  };
}

describe("Quant list contracts", () => {
  it("ensemble mock returns ≤10 ranked items with refresh_sec 900", () => {
    const a = mockEnsemblePicks(0);
    const b = mockEnsemblePicks(3);
    assert.equal(a.refresh_sec, 900);
    assert.ok(a.items.length <= 10);
    assert.equal(a.items.length, 10);
    assert.equal(a.universe_source, "SETUP_UNIVERSE");
    assert.ok(a.items.every((i) => i.rank >= 1 && i.rank <= 10));
    assert.ok(a.items.every((i) => i.rank_components && typeof i.ensemble_score === "number"));
    assert.ok(a.items.every((i) => typeof i.best_confidence === "number"));
    assert.ok(a.items.every((i) => (i.contributing_factors?.length ?? 0) >= 1));
    assert.ok(a.items.every((i) => !i.setup_types.includes("ob_fvg" as never)));
    assert.notDeepEqual(
      a.items.map((i) => i.symbol),
      b.items.map((i) => i.symbol),
    );
  });

  it("categorized mock returns ≤20 and accepts no asset-class filter", () => {
    const all = mockCategorizedPicks(0);
    const futures = mockCategorizedPicks(0, undefined, "futures");
    assert.ok(all.items.length <= 20);
    assert.equal(all.items.length, 20);
    assert.ok(new Set(all.items.map((i) => i.asset_class)).size >= 2);
    assert.ok(futures.items.every((i) => i.asset_class === "futures"));
    assert.ok(all.items.every((i) => ["momentum", "mean_reversion", "confluence", "other"].includes(i.category)));
  });

  it("normalizes the locked Quant GET /picks/ensemble envelope", () => {
    const ens = normalizeEnsemblePicks({
      as_of_ts_ms: 0,
      refresh_sec: 900,
      items: [
        {
          rank: 1,
          symbol: "BTCUSDT",
          asset_class: "crypto",
          score: 0.0,
          setup_types: ["sweep_reclaim"],
          confidence: 0.0,
        },
      ],
    });
    assert.ok(ens);
    assert.equal(ens.as_of_ts_ms, 0);
    assert.equal(ens.refresh_sec, 900);
    assert.equal(ens.universe_source, undefined);
    assert.equal(ens.items.length, 1);
    assert.ok(ens.items.length <= 10);
    assert.deepEqual(ens.items[0], {
      rank: 1,
      symbol: "BTCUSDT",
      asset_class: "crypto",
      score: 0,
      setup_types: ["sweep_reclaim"],
      confidence: 0,
    });
  });

  it("maps ensemble_score → score and best_confidence → confidence when present", () => {
    const ens = normalizeEnsemblePicks({
      as_of_ts_ms: 1,
      refresh_sec: 900,
      universe_source: "DE",
      items: [
        {
          rank: 2,
          symbol: "es",
          asset_class: "futures",
          score: 0.1,
          ensemble_score: 0.77,
          setup_types: ["fvg_entry"],
          confidence: 0.2,
          best_confidence: 0.81,
        },
      ],
    });
    assert.equal(ens?.universe_source, "DE");
    assert.equal(ens?.items[0]?.score, 0.77);
    assert.equal(ens?.items[0]?.ensemble_score, 0.77);
    assert.equal(ens?.items[0]?.confidence, 0.81);
    assert.equal(ens?.items[0]?.best_confidence, 0.81);
    assert.equal(ens?.items[0]?.symbol, "ES");
    assert.equal(ens?.items[0]?.rank_components, undefined);
  });

  it("normalizers clamp to contract caps and map stocks→equity", () => {
    const ens = normalizeEnsemblePicks({
      as_of_ts_ms: 1,
      refresh_sec: 60,
      universe_source: "DE",
      items: Array.from({ length: 15 }, (_, i) => ({
        rank: i + 1,
        symbol: `S${i}`,
        asset_class: "stocks",
        score: 0.5,
        setup_types: ["sweep_reclaim", "ob_fvg"],
        confidence: 0.4,
        ensemble_score: 0.5,
        rank_components: { setup_quality: 1, risk_adjusted: 1, kill_zone: 1, volume: 1, freshness: 1 },
      })),
    });
    assert.equal(ens?.items.length, 10);
    assert.equal(ens?.refresh_sec, 900);
    assert.ok(ens?.items.every((i) => i.asset_class === "equity"));
    assert.ok(ens?.items.every((i) => !i.setup_types.includes("ob_fvg" as never)));

    const cats = normalizeCategorizedPicks({
      items: Array.from({ length: 30 }, (_, i) => ({ symbol: `P${i}`, category: "momentum", score: 70 })),
    });
    assert.equal(cats?.items.length, 20);
  });
});

describe("desk tabs + chart selector", () => {
  it("maps setup dropdown 1–6 and rejects ob_fvg", () => {
    assert.deepEqual(
      SETUP_FILTERS.map((s) => s.setup_type),
      SETUP_TYPES,
    );
    assert.equal(setupFilterType("3"), "po3_judas");
    assert.equal(setupFilterType("ob_fvg"), "all");
    assert.equal(wireAssetClass("stocks"), "equity");
  });

  it("cardsForTab isolates futures/stocks/cryptos and setup 1–6", () => {
    const rows = [
      sig({ id: "f1", symbol: "ES", asset_class: "futures", setup_type: "sweep_reclaim", ts_ms: 2 }),
      sig({ id: "f2", symbol: "CL", asset_class: "futures", setup_type: "fvg_entry", ts_ms: 3 }),
      sig({ id: "e1", symbol: "AAPL", asset_class: "equity", setup_type: "sweep_reclaim", ts_ms: 4 }),
      sig({ id: "c1", symbol: "BTCUSDT", asset_class: "crypto", setup_type: "po3_judas", ts_ms: 5 }),
    ];
    const futures = cardsForTab(rows, "futures", "all", null, pinSetupCards);
    assert.deepEqual(
      futures.map((s) => s.symbol).sort(),
      ["CL", "ES"],
    );
    const onlySweep = cardsForTab(rows, "futures", "sweep_reclaim", null, pinSetupCards);
    assert.equal(onlySweep.length, 1);
    assert.equal(onlySweep[0]?.symbol, "ES");
    const stocks = cardsForTab(rows, "stocks", "all", null, pinSetupCards);
    assert.equal(stocks[0]?.symbol, "AAPL");
  });

  it("futures chart selector includes ES CL GC NQ", () => {
    const opts = chartSymbolsForTab("futures", [], []);
    assert.ok(["ES", "CL", "GC", "NQ"].every((s) => opts.includes(s)));
  });

  it("chart selector uses universe/top first (tab symbols in front, not a 4-symbol lock)", () => {
    const extras = [
      { symbol: "AAPL", asset_class: "equity" as const },
      { symbol: "ES", asset_class: "futures" as const },
      { symbol: "CL", asset_class: "futures" as const },
      { symbol: "BTCUSDT", asset_class: "crypto" as const },
      { symbol: "NVDA", asset_class: "equity" as const },
    ];
    const opts = chartSymbolsForTab("futures", [], extras);
    assert.ok(opts.length >= 5);
    assert.ok(opts.indexOf("ES") < opts.indexOf("AAPL"));
    assert.ok(opts.includes("NVDA"));
    assert.ok(opts.includes("BTCUSDT"));
  });
});

describe("multi-symbol Quant clients", () => {
  it("GET /signals serializes symbols= (≤20) and keeps single-symbol", () => {
    assert.equal(signalListPath({ symbol: "BTCUSDT" }), "/signals?symbol=BTCUSDT");
    const path = signalListPath({
      symbols: ["es", "CL", "GC", "NQ", "es", "AAPL"],
      status: "ACTIVE",
      limit: 200,
    });
    assert.ok(path.startsWith("/signals?"));
    assert.match(path, /symbols=ES%2CCL%2CGC%2CNQ%2CAAPL/);
    assert.match(path, /status=ACTIVE/);
    assert.equal(joinSymbols(["es", "CL", "es", ...Array.from({ length: 30 }, (_, i) => `S${i}`)])?.split(",").length, 20);
  });

  it("GET /performance/summary accepts optional symbols=", () => {
    assert.equal(joinSymbols(["BTCUSDT", "ETHUSDT"]), "BTCUSDT,ETHUSDT");
  });
});

describe("multi-symbol history", () => {
  it("lists denser setup_signals across ~20 symbols", () => {
    const { items } = mockListSignals({ limit: 200 }, 0);
    const symbols = uniqueSymbols(items);
    assert.ok(symbols.length >= 18);
    assert.ok(symbols.length <= 20);
    assert.ok(["ES", "CL", "GC", "NQ"].every((s) => symbols.includes(s)));
    assert.ok(symbols.includes("BTCUSDT") || symbols.includes("ETHUSDT"));
    assert.ok(items.every((s) => (s.contributing_factors?.length ?? 0) >= 1));
    assert.ok(items.every((s) => (s.factor_breakdown?.length ?? 0) >= 1));
    assert.ok(items.every((s) => typeof s.ensemble_score === "number"));
    assert.ok(items.every((s) => s.rank_components && typeof s.rank_components.setup_quality === "number"));
    const futures = mockListSignals({ asset_class: "futures", status: "ACTIVE", limit: 80 }, 0).items;
    assert.ok(futures.every((s) => s.asset_class === "futures"));
    const stocks = mockListSignals({ asset_class: "stocks", limit: 80 }, 0).items;
    assert.ok(stocks.every((s) => s.asset_class === "equity"));
    const scoped = mockListSignals({ symbols: ["ES", "CL"], limit: 80 }, 0).items;
    assert.ok(scoped.every((s) => s.symbol === "ES" || s.symbol === "CL"));
  });

  it("keeps optional ensemble ranking on signal or ensemble_features side channel", () => {
    const base = mockListSignals({ symbol: "ES", limit: 1 }, 0).items[0];
    assert.ok(base);
    const direct = normalizeSignal({ ...base, ensemble_score: 0.42, rank_components: undefined });
    assert.equal(direct?.ensemble_score, 0.42);
    const side = normalizeSignal({
      ...base,
      ensemble_score: undefined,
      rank_components: undefined,
      ensemble_features: {
        ensemble_score: 0.55,
        rank_components: { setup_quality: 0.1, risk_adjusted: 0.2, kill_zone: 0.3, volume: 0.4, freshness: 0.5 },
      },
    });
    assert.equal(side?.ensemble_score, 0.55);
    assert.equal(side?.rank_components?.freshness, 0.5);
    const bare = normalizeSignal({
      id: "s1",
      symbol: "BTCUSDT",
      setup_type: "sweep_reclaim",
      side: "long",
      ts_ms: 1,
      entry: 1,
      stop: 0.9,
      target: 1.2,
      contributing_factors: ["liquidity_sweep"],
      factor_breakdown: [{ name: "liquidity_sweep", weight: 15, score: 80 }],
    });
    assert.equal(bare?.ensemble_score, undefined);
    assert.equal(bare?.rank_components, undefined);
    assert.deepEqual(bare?.contributing_factors, ["liquidity_sweep"]);
    assert.equal(bare?.factor_breakdown?.[0]?.name, "liquidity_sweep");
  });
});

describe("refresh cadence", () => {
  it("never polls faster than 15 minutes", () => {
    assert.equal(LIST_REFRESH_SEC, 900);
    assert.equal(clampRefreshSec(60), 900);
    assert.equal(clampRefreshSec(1800), 1800);
  });
});

describe("provisional universe is mock-only", () => {
  it("SETUP_UNIVERSE is 20 symbols and excludes SMCI/TSM placeholders", () => {
    assert.equal(SETUP_UNIVERSE.length, 20);
    assert.ok(!SETUP_UNIVERSE.some((s) => s.symbol === "SMCI" || s.symbol === "TSM"));
  });

  it("GET /v1/universe/top mock + parser honor limit 10/20", () => {
    const top10 = mockUniverseTop(10);
    const top20 = mockUniverseTop(20);
    assert.equal(top10.limit, 10);
    assert.equal(top10.symbols.length, 10);
    assert.equal(top20.symbols.length, 20);
    assert.ok(top10.symbols.some((s) => ["ES", "CL", "GC", "NQ"].includes(s.symbol)) || top20.symbols.some((s) => s.symbol === "ES"));
    const parsed = normalizeUniverseTop({
      as_of_ts_ms: 1,
      limit: 10,
      symbols: [
        { symbol: "ES", asset_class: "futures", rank: 1, score: 0.9 },
        { symbol: "CL", asset_class: "futures", rank: 2, score: 0.8 },
      ],
    });
    assert.equal(parsed?.symbols[0]?.symbol, "ES");
  });

  it("recon audit mock caps at 16", () => {
    const dropped = mockDroppedPicks(0, new Set(), 16);
    assert.ok(dropped.length <= 16);
  });
});
