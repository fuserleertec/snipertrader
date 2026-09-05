import { OVERLAY_PRESETS, OVERLAY_SETUP_TYPES } from "./constants";
import type { OverlayPreset, OverlaySetupType, PerformanceSetupKey, SetupType } from "./types";

/** Locked GET /performance/summary keys. Index by_setup by these strings only. */
export const PRODUCT_KEYS: PerformanceSetupKey[] = [
  "1_liquidity_sweep_vwap_reclaim",
  "2_fvg_mitigation_vwap",
  "3_po3_asia_range_sweep",
  "4_sd_extension_fade",
  "5_vwap_pullback_cont",
  "6_avwap_ob_confluence",
];

export const SETUP_TO_PRODUCT: Partial<Record<SetupType, PerformanceSetupKey>> = {
  sweep_reclaim: "1_liquidity_sweep_vwap_reclaim",
  fvg_entry: "2_fvg_mitigation_vwap",
  ob_fvg: "2_fvg_mitigation_vwap",
  po3_judas: "3_po3_asia_range_sweep",
  sd_extension_fade: "4_sd_extension_fade",
  vwap_pullback_cont: "5_vwap_pullback_cont",
  avwap_ob_confluence: "6_avwap_ob_confluence",
};

export function productKeyOf(setup: SetupType): PerformanceSetupKey | undefined {
  return SETUP_TO_PRODUCT[setup];
}

export function isOverlaySetup(setup: string): setup is OverlaySetupType {
  return (OVERLAY_SETUP_TYPES as string[]).includes(setup);
}

export function overlayForSetup(setup: SetupType): OverlayPreset {
  if (setup === "fvg_entry" || setup === "ob_fvg") return "fvg_ob";
  if (setup === "sweep_reclaim") return "sweep_reclaim";
  if (setup === "po3_judas") return "po3_judas";
  if (setup === "sd_extension_fade") return "sd_extension_fade";
  if (setup === "vwap_pullback_cont") return "vwap_pullback_cont";
  if (setup === "avwap_ob_confluence") return "avwap_ob_confluence";
  return "all";
}

export function parseOverlayParam(raw: string | null | undefined): OverlayPreset | null {
  if (!raw) return null;
  if (raw === "ob_fvg" || raw === "fvg_entry") return "fvg_ob";
  const hit = OVERLAY_PRESETS.find((p) => p.id === raw || p.label === raw);
  return hit?.id ?? null;
}
