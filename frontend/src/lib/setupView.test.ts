import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { Signal } from "./types";
import { pinSetupCards, resolveSelected, viewAllows } from "./setupView";

function sig(partial: Partial<Signal> & Pick<Signal, "id" | "setup_type">): Signal {
  return {
    ts_ms: 1,
    symbol: "BTCUSDT",
    asset_class: "crypto",
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

describe("pinSetupCards", () => {
  it("keeps one ACTIVE card per locked setup", () => {
    const rows = [
      sig({ id: "a1", setup_type: "sweep_reclaim", ts_ms: 10 }),
      sig({ id: "a2", setup_type: "sweep_reclaim", ts_ms: 20 }),
      sig({ id: "b1", setup_type: "fvg_entry", ts_ms: 5 }),
    ];
    const cards = pinSetupCards(rows, null);
    assert.equal(cards.find((c) => c.setup_type === "sweep_reclaim")?.id, "a2");
    assert.equal(cards.find((c) => c.setup_type === "fvg_entry")?.id, "b1");
  });

  it("pinned id occupies its setup slot across newer upserts", () => {
    const rows = [
      sig({ id: "old", setup_type: "sweep_reclaim", ts_ms: 10 }),
      sig({ id: "new", setup_type: "sweep_reclaim", ts_ms: 99 }),
    ];
    const cards = pinSetupCards(rows, "old");
    assert.equal(cards.find((c) => c.setup_type === "sweep_reclaim")?.id, "old");
  });
});

describe("resolveSelected", () => {
  it("prefers the live row, then the snapshot", () => {
    const live = sig({ id: "x", setup_type: "po3_judas", ts_ms: 50, entry: 111 });
    const snap = sig({ id: "x", setup_type: "po3_judas", ts_ms: 1, entry: 100 });
    const fromLive = resolveSelected([live], "x", snap);
    assert.equal(fromLive?.entry, 111);
    const fromSnap = resolveSelected([], "x", snap);
    assert.equal(fromSnap?.entry, 100);
    assert.equal(resolveSelected([], "gone", snap), null);
  });
});

describe("viewAllows", () => {
  it("blocks FVG/OB/DISP on sweep_reclaim", () => {
    assert.equal(viewAllows("sweep_reclaim", "sweep"), true);
    assert.equal(viewAllows("sweep_reclaim", "mss"), true);
    assert.equal(viewAllows("sweep_reclaim", "vwap"), true);
    assert.equal(viewAllows("sweep_reclaim", "fvg"), false);
    assert.equal(viewAllows("sweep_reclaim", "ob"), false);
    assert.equal(viewAllows("sweep_reclaim", "disp"), false);
  });

  it("never treats ob_fvg as a setup view", () => {
    assert.equal("ob_fvg" in { sweep_reclaim: 1, fvg_ob: 1 }, false);
    assert.equal(viewAllows("fvg_ob", "fvg"), true);
    assert.equal(viewAllows("fvg_ob", "sweep"), false);
  });
});
