import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { LIST_REFRESH_SEC, SETUP_FILTERS, SETUP_TYPES, wireAssetClass } from "./constants";
import {
  activeSetupQuery,
  allowedSymbolSet,
  cardsForTab,
  capWithinAllowed,
  chartExtrasFromTop,
  chartSymbolsForTab,
  clampRefreshSec,
  historyStatusMatches,
  rankWithinAllowed,
  setupFilterType,
  uniqueSymbols,
  universeSourceFromAllowed,
} from "./desk";
import {
  avwapPath,
  joinSymbols,
  killZonePath,
  normalizeCategorizedPicks,
  normalizeEnsemblePicks,
  normalizeUniverseTop,
  ohlcvPath,
  sessionPath,
  signalListPath,
  universePath,
  universeTopPath,
  volumeProfilePath,
  vwapPath,
} from "./http";
import { mockCategorizedPicks, mockDroppedPicks, mockEnsemblePicks, mockUniverse, mockUniverseTop, SETUP_UNIVERSE } from "./mocks/lists";
import { buildMockHistory } from "./mocks/market";
import { ensembleFeatureTooltip, presentEnsemble } from "./mocks/terminal";
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
    assert.equal(ens.universe_source, "SETUP_UNIVERSE");
    assert.equal(ens.items.length, 1);
    assert.ok(ens.items.length <= 10);
    assert.equal(ens.items[0]?.symbol, "BTCUSDT");
    assert.equal(ens.items[0]?.ensemble_score, 0);
    assert.equal(ens.items[0]?.rank_components, undefined);
    assert.equal(ens.items[0]?.contributing_factors, undefined);
  });

  it("parses universe_source + ensemble_score + rank_components on GET /picks/ensemble", () => {
    const ens = normalizeEnsemblePicks({
      as_of_ts_ms: 0,
      refresh_sec: 900,
      universe_source: "DE",
      items: [
        {
          rank: 1,
          symbol: "CL",
          asset_class: "futures",
          score: 0.2,
          ensemble_score: 0.64,
          setup_types: ["vwap_pullback_cont"],
          confidence: 0.7,
          rank_components: {
            setup_quality: 0.8,
            risk_adjusted: 0.7,
            kill_zone: 0.4,
            volume: 0.5,
            freshness: 0.6,
          },
        },
      ],
    });
    assert.equal(ens?.universe_source, "DE");
    assert.equal(ens?.items[0]?.score, 0.64);
    assert.equal(ens?.items[0]?.ensemble_score, 0.64);
    assert.deepEqual(ens?.items[0]?.rank_components, {
      setup_quality: 0.8,
      risk_adjusted: 0.7,
      kill_zone: 0.4,
      volume: 0.5,
      freshness: 0.6,
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

  it("keeps optional rank_components + contributing_factors on ensemble items", () => {
    const nested = normalizeEnsemblePicks({
      as_of_ts_ms: 2,
      refresh_sec: 900,
      items: [
        {
          rank: 1,
          symbol: "NQ",
          asset_class: "futures",
          score: 0.2,
          setup_types: ["fvg_entry"],
          confidence: 0.3,
          ensemble_features: {
            ensemble_score: 0.71,
            best_confidence: 0.88,
            rank_components: {
              setup_quality: 0.9,
              risk_adjusted: 0.6,
              kill_zone: 0.5,
              volume: 0.4,
              freshness: 0.3,
            },
            contributing_factors: ["liquidity_sweep", "volume_confirm"],
          },
        },
      ],
    });
    assert.equal(nested?.items[0]?.score, 0.71);
    assert.equal(nested?.items[0]?.ensemble_score, 0.71);
    assert.equal(nested?.items[0]?.confidence, 0.88);
    assert.deepEqual(nested?.items[0]?.contributing_factors, ["liquidity_sweep", "volume_confirm"]);
    assert.equal(nested?.items[0]?.rank_components?.setup_quality, 0.9);

    const tip = ensembleFeatureTooltip(nested!.items[0]!);
    assert.match(tip, /ensemble_score 0\.710/);
    assert.match(tip, /rank_components/);
    assert.match(tip, /contributing_factors  liquidity_sweep · volume_confirm/);

    const bare = presentEnsemble(
      {
        rank: 1,
        symbol: "ES",
        asset_class: "futures",
        score: 0.5,
        setup_types: ["sweep_reclaim"],
        confidence: 0.4,
        ensemble_score: 0.5,
      },
      "market",
    );
    assert.match(bare.reason, /score 0\.50/);
    assert.match(bare.tooltip, /ensemble_score 0\.500/);
    assert.doesNotMatch(bare.tooltip, /rank_components/);
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

  it("Active Setup query is GET /signals?status=ACTIVE&asset_class= (stocks→equity)", () => {
    const futures = activeSetupQuery("futures");
    assert.equal(futures.status, "ACTIVE");
    assert.equal(futures.asset_class, "futures");
    assert.equal(activeSetupQuery("stocks").asset_class, "equity");
    assert.equal(activeSetupQuery("cryptos").asset_class, "crypto");
    const path = signalListPath(activeSetupQuery("stocks", { setup_type: "sweep_reclaim", symbol: "aapl", limit: 20 }));
    assert.equal(path, "/signals?symbol=AAPL&status=ACTIVE&setup_type=sweep_reclaim&asset_class=equity&limit=20");
    const hist = signalListPath(
      { symbol: "ES", status: "TP_HIT", setup_type: "fvg_entry", side: "long", from_ts: 1, to_ts: 2, cursor: "c1" },
      "/signals/history",
    );
    assert.equal(
      hist,
      "/signals/history?symbol=ES&status=TP_HIT&setup_type=fvg_entry&side=long&from_ts=1&to_ts=2&cursor=c1",
    );
  });

  it("futures chart selector can switch ES CL GC NQ (paper sim, not a P0 list)", () => {
    const extras = ["ES", "CL", "GC", "NQ", "AAPL"].map((symbol) => ({
      symbol,
      asset_class: symbol === "AAPL" ? ("equity" as const) : ("futures" as const),
    }));
    const fromUniverse = chartSymbolsForTab("futures", [], extras);
    assert.ok(["ES", "CL", "GC", "NQ"].every((s) => fromUniverse.includes(s)));
    const paperOnly = chartSymbolsForTab("futures", [], []);
    assert.ok(["ES", "CL", "GC", "NQ"].every((s) => paperOnly.includes(s)));
    assert.ok(fromUniverse.indexOf("ES") < fromUniverse.indexOf("AAPL"));
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
    const top = mockUniverseTop(20);
    const fromTop = chartExtrasFromTop(top);
    assert.equal(fromTop.length, 20);
    assert.deepEqual(fromTop, top.symbols);
    assert.deepEqual(chartExtrasFromTop(undefined), []);
    assert.notEqual(universePath(), universeTopPath(20));
    const viaTop = chartSymbolsForTab("futures", [], fromTop);
    assert.ok(viaTop.length >= 4);
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
    assert.ok(historyStatusMatches("TP_HIT", "all"));
    assert.ok(historyStatusMatches("SL_HIT", "all"));
    assert.equal(historyStatusMatches("ACTIVE", "all"), false);
    assert.equal(historyStatusMatches("CANCELLED", "all"), false);
    assert.ok(historyStatusMatches("CANCELLED", "CANCELLED"));
    assert.ok(historyStatusMatches("ACTIVE", "ACTIVE"));
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

  it("picks stay dynamic, universe has ES/CL/GC/NQ, history is multi-symbol wins/losses", () => {
    const a = mockEnsemblePicks(0);
    const b = mockEnsemblePicks(5);
    const cats = mockCategorizedPicks(0);
    const uni = mockUniverseTop(20);
    assert.ok(["ES", "CL", "GC", "NQ"].every((s) => uni.symbols.some((row) => row.symbol === s)));
    assert.ok(["ES", "CL", "GC", "NQ"].every((s) => SETUP_UNIVERSE.some((row) => row.symbol === s)));
    assert.notDeepEqual(
      a.items.map((i) => i.symbol),
      b.items.map((i) => i.symbol),
    );
    const banned = new Set(["SMCI", "TSM"]);
    assert.ok(!a.items.some((i) => banned.has(i.symbol)));
    assert.ok(!cats.items.some((i) => banned.has(i.symbol)));
    assert.ok(!uni.symbols.some((i) => banned.has(i.symbol)));
    const closed = mockListSignals({ limit: 200 }, 0).items.filter((s) => historyStatusMatches(s.status, "all"));
    const wins = uniqueSymbols(closed.filter((s) => s.status === "TP_HIT"));
    const losses = uniqueSymbols(closed.filter((s) => s.status === "SL_HIT"));
    assert.ok(wins.length >= 8);
    assert.ok(losses.length >= 8);
    assert.ok(wins.includes("ES") || losses.includes("ES"));
    assert.ok(!closed.some((s) => banned.has(s.symbol)));
    assert.ok(closed.every((s) => s.status === "TP_HIT" || s.status === "SL_HIT"));
  });

  it("Quant P0/P4 rank only inside the DE allowed set and never invent a universe", () => {
    const allowed = allowedSymbolSet([
      { symbol: "ES" },
      { symbol: "CL" },
      { symbol: "GC" },
    ]);
    const ens = mockEnsemblePicks(0, undefined, [...allowed]);
    assert.ok(ens.items.length <= 10);
    assert.ok(ens.items.every((i) => allowed.has(i.symbol)));
    assert.equal(ens.universe_source, "DE");
    const outside = normalizeEnsemblePicks({
      as_of_ts_ms: 0,
      refresh_sec: 900,
      items: [
        { rank: 1, symbol: "SMCI", asset_class: "equity", score: 0.9, setup_types: ["sweep_reclaim"], confidence: 0.9 },
        { rank: 2, symbol: "ES", asset_class: "futures", score: 0.8, setup_types: ["sweep_reclaim"], confidence: 0.8 },
      ],
    });
    const clipped = rankWithinAllowed(outside?.items ?? [], allowed);
    assert.deepEqual(
      clipped.map((i) => i.symbol),
      ["ES"],
    );
    const passthrough = rankWithinAllowed(outside?.items ?? [], new Set());
    assert.deepEqual(
      passthrough.map((i) => i.symbol),
      ["SMCI", "ES"],
    );
    const cats = capWithinAllowed(
      [
        { symbol: "TSM", asset_class: "equity", category: "momentum", score: 1, confidence: 1, setup_types: [], entry: 1, stop: 1, target: 1, atr: 1, reward_risk: 1 },
        { symbol: "CL", asset_class: "futures", category: "other", score: 1, confidence: 1, setup_types: [], entry: 1, stop: 1, target: 1, atr: 1, reward_risk: 1 },
      ],
      allowed,
    );
    assert.deepEqual(
      cats.map((i) => i.symbol),
      ["CL"],
    );
  });

  it("GET /v1/universe/top mock + parser honor limit 10/20", () => {
    assert.equal(universePath(), "/v1/universe");
    assert.equal(universeTopPath(10), "/v1/universe/top?limit=10");
    assert.equal(universeTopPath(20), "/v1/universe/top?limit=20");
    assert.equal(universeTopPath(3), "/v1/universe/top?limit=10");
    assert.equal(universeTopPath(99), "/v1/universe/top?limit=20");
    const top10 = mockUniverseTop(10);
    const top20 = mockUniverseTop(20);
    assert.equal(top10.limit, 10);
    assert.equal(top10.symbols.length, 10);
    assert.equal(top20.symbols.length, 20);
    assert.ok(top10.symbols.some((s) => ["ES", "CL", "GC", "NQ"].includes(s.symbol)) || top20.symbols.some((s) => s.symbol === "ES"));
    const parsed = normalizeUniverseTop({
      as_of_ts_ms: 1725459000000,
      limit: 10,
      symbols: [
        { symbol: "ES", asset_class: "futures", rank: 1, score: 0.9 },
        { symbol: "CL", asset_class: "futures", rank: 2, score: 0.8 },
      ],
    });
    assert.equal(parsed?.as_of_ts_ms, 1725459000000);
    assert.equal(parsed?.symbols[0]?.symbol, "ES");
    const viaItems = normalizeUniverseTop({
      as_of_ts_ms: 2,
      items: [{ symbol: "nq", asset_class: "futures" }],
    });
    assert.equal(viaItems?.symbols[0]?.symbol, "NQ");
    assert.equal(viaItems?.symbols[0]?.asset_class, "futures");
    const allowed = allowedSymbolSet(parsed?.symbols);
    assert.equal(universeSourceFromAllowed(allowed), "DE");
    assert.equal(universeSourceFromAllowed(new Set()), "SETUP_UNIVERSE");
    const full = mockUniverse();
    assert.ok(full.symbols.length <= 20);
    assert.equal(full.limit, 20);
  });

  it("chart feed paths pass the selected symbol into existing DE clients", () => {
    assert.equal(ohlcvPath("es", "5m", 200), "/v1/ohlcv/ES?timeframe=5m&limit=200");
    assert.equal(vwapPath("CL", "session"), "/v1/vwap/CL?anchor=session");
    assert.equal(sessionPath("GC"), "/v1/session/GC");
    assert.equal(sessionPath("NQ", "rth"), "/v1/session/NQ/rth");
    assert.equal(avwapPath("BTCUSDT"), "/v1/avwap/BTCUSDT");
    assert.equal(volumeProfilePath("AAPL", "rth"), "/v1/volume-profile/AAPL/rth");
    assert.equal(killZonePath("ETHUSDT"), "/v1/kill-zone/ETHUSDT");
  });

  it("mock OHLC is per-symbol for ES/CL/GC/NQ until DE seeds live history", () => {
    const es = buildMockHistory("ES", "5m");
    const cl = buildMockHistory("CL", "5m");
    const gc = buildMockHistory("GC", "5m");
    const nq = buildMockHistory("NQ", "5m");
    assert.ok(es.length > 50 && cl.length > 50 && gc.length > 50 && nq.length > 50);
    assert.ok(es.every((b) => b.symbol === "ES" && b.asset_class === "futures"));
    assert.ok(cl.every((b) => b.symbol === "CL"));
    assert.ok(gc.every((b) => b.symbol === "GC"));
    assert.ok(nq.every((b) => b.symbol === "NQ"));
    assert.notEqual(es[0]?.close, cl[0]?.close);
    assert.notEqual(gc[0]?.close, nq[0]?.close);
  });

  it("recon audit mock caps at 16", () => {
    const dropped = mockDroppedPicks(0, new Set(), 16);
    assert.ok(dropped.length <= 16);
  });
});
