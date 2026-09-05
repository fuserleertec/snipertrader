import type { OverlayPreset, PerformanceSetupKey, SetupType } from "./types";

/** Locked GET /performance/summary keys. Index by_setup by these strings only. */
export const PRODUCT_KEYS: PerformanceSetupKey[] = [
  "1_liquidity_sweep_vwap_reclaim",
  "2_fvg_mitigation_vwap",
  "3_po3_asia_range_sweep",
  "4_sd_extension_fade",
  "5_vwap_pullback_cont",
  "6_avwap_ob_confluence",
];

export const SETUP_TO_PRODUCT: Record<SetupType, PerformanceSetupKey> = {
  sweep_reclaim: "1_liquidity_sweep_vwap_reclaim",
  fvg_entry: "2_fvg_mitigation_vwap",
  po3_judas: "3_po3_asia_range_sweep",
  sd_extension_fade: "4_sd_extension_fade",
  vwap_pullback_cont: "5_vwap_pullback_cont",
  avwap_ob_confluence: "6_avwap_ob_confluence",
};

export function productKeyOf(setup: SetupType): PerformanceSetupKey {
  return SETUP_TO_PRODUCT[setup];
}

export function overlayForSetup(setup: SetupType): OverlayPreset {
  if (setup === "fvg_entry") return "fvg_ob";
  return setup;
}
