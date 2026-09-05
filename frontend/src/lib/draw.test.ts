import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildDrawModelFromOverlays, highlightIds } from "./draw";
import type { Overlay, PatternBook } from "./types";

const emptyBook: PatternBook = { fvgs: [], obs: [], sweeps: [], mss: [] };

const overlays: Overlay[] = [
  { kind: "zone", source: "fvg", id: "fvg-1", symbol: "BTCUSDT", t0: 1, t1: 2, high: 2, low: 1, direction: "bullish" },
  { kind: "zone", source: "ob", id: "ob-1", symbol: "BTCUSDT", t0: 1, t1: 2, high: 2, low: 1, direction: "bullish" },
  { kind: "marker", source: "sweep", id: "sw-1", symbol: "BTCUSDT", time: 1, price: 1, side: "sell" },
  { kind: "marker", source: "mss", id: "mss-1", symbol: "BTCUSDT", time: 1, price: 1, direction: "bullish" },
];

describe("overlay allow-list + trigger filter", () => {
  it("sweep_reclaim never draws FVG/OB even on all overlays input", () => {
    const model = buildDrawModelFromOverlays({
      preset: "sweep_reclaim",
      overlays,
      book: emptyBook,
      highlight: new Set(),
      asia: null,
      killZone: null,
    });
    assert.equal(model.zones.some((z) => z.kind === "fvg" || z.kind === "ob"), false);
    assert.equal(model.arrows.some((a) => a.id === "sw-1"), true);
    assert.equal(model.lines.some((l) => l.id === "mss-1"), true);
  });

  it("selected trigger_event_ids hide non-joined FVG/OB/sweep/mss", () => {
    const model = buildDrawModelFromOverlays({
      preset: "fvg_ob",
      overlays,
      book: emptyBook,
      highlight: new Set(["fvg-1"]),
      asia: null,
      killZone: null,
    });
    assert.deepEqual(
      model.zones.map((z) => z.id),
      ["fvg-1"],
    );
    assert.equal(model.arrows.length, 0);
  });

  it("highlightIds reads only trigger_event_ids", () => {
    const ids = highlightIds({
      id: "s",
      ts_ms: 1,
      symbol: "BTCUSDT",
      asset_class: "crypto",
      setup_type: "sweep_reclaim",
      side: "long",
      entry: 1,
      stop: 1,
      target: 1,
      status: "ACTIVE",
      confidence: 0.8,
      timeframe: "5m",
      ref_session: "ny_am",
      trigger_event_ids: ["sw-1", "mss-1"],
      realized_r: null,
      exit_price: null,
      closed_ts_ms: null,
    });
    assert.equal(ids.has("sw-1"), true);
    assert.equal(ids.has("fvg-1"), false);
  });
});
