import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { normalizeAvwap, normalizeKillZone, normalizeVolumeProfile } from "./overlays";

const bands = {
  plus_1_sigma: 101,
  plus_2_sigma: 102,
  plus_3_sigma: 103,
  minus_1_sigma: 99,
  minus_2_sigma: 98,
  minus_3_sigma: 97,
};

describe("normalizeAvwap", () => {
  it("parses DE Phase 2 fields and { value } wrap", () => {
    const raw = {
      anchor_id: "a1",
      symbol: "BTCUSDT",
      anchor_time: 1,
      anchor_price: 100,
      vwap_value: 100.5,
      bands,
      asset_class: "crypto",
    };
    const a = normalizeAvwap(raw);
    assert.equal(a?.vwap_value, 100.5);
    assert.equal(normalizeAvwap({ value: raw })?.anchor_id, "a1");
    assert.equal(normalizeAvwap({ ...raw, vwap_value: undefined }), null);
  });
});

describe("normalizeKillZone", () => {
  it("requires active boolean and known kill_zone", () => {
    const raw = {
      symbol: "ES",
      kill_zone: "ny_am",
      start_time: 1,
      end_time: 2,
      active: true,
      asset_class: "futures",
    };
    assert.equal(normalizeKillZone(raw)?.kill_zone, "ny_am");
    assert.equal(normalizeKillZone({ value: raw })?.active, true);
    assert.equal(normalizeKillZone({ ...raw, active: "yes" }), null);
    assert.equal(normalizeKillZone({ ...raw, kill_zone: "tokyo" }), null);
  });
});

describe("normalizeVolumeProfile", () => {
  it("unwraps { profiles: [{ value }] } and { value }", () => {
    const raw = {
      symbol: "AAPL",
      session_type: "rth",
      high_volume_nodes: [{ price: 10, volume: 1 }],
      low_volume_nodes: [],
      poc: 10,
      timestamp: 9,
    };
    assert.equal(normalizeVolumeProfile(raw)?.poc, 10);
    assert.equal(normalizeVolumeProfile({ value: raw })?.session_type, "rth");
    assert.equal(normalizeVolumeProfile({ profiles: [{ value: raw }] })?.symbol, "AAPL");
    assert.equal(normalizeVolumeProfile({ ...raw, session_type: "pre" }), null);
  });
});
