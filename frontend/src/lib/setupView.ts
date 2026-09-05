import { SETUP_TYPES } from "./constants";
import { overlayForSetup } from "./setups";
import type { OverlayPreset, SetupType, Signal } from "./types";

/** Chart layers a setup view may draw. `all` allows every layer. */
export type OverlayLayer =
  | "fvg"
  | "ob"
  | "sweep"
  | "mss"
  | "asia"
  | "kill_zone"
  | "hvn"
  | "avwap"
  | "pullback"
  | "rejection"
  | "disp"
  | "entry"
  | "vwap";

/**
 * Locked setup → allowed overlay layers.
 * `sweep_reclaim` must not show FVG / OB / DISP.
 * `ob_fvg` is not a setup_type.
 */
export const SETUP_VIEW_LAYERS: Record<Exclude<OverlayPreset, "all">, readonly OverlayLayer[]> = {
  sweep_reclaim: ["sweep", "mss", "vwap"],
  fvg_ob: ["fvg", "ob", "hvn", "entry", "vwap"],
  po3_judas: ["sweep", "asia", "kill_zone", "disp"],
  sd_extension_fade: ["rejection", "vwap"],
  vwap_pullback_cont: ["fvg", "ob", "pullback", "vwap"],
  avwap_ob_confluence: ["ob", "avwap"],
};

export function viewAllows(preset: OverlayPreset, layer: OverlayLayer): boolean {
  if (preset === "all") return true;
  return SETUP_VIEW_LAYERS[preset].includes(layer);
}

export function setupRank(setup: string): number {
  const i = (SETUP_TYPES as readonly string[]).indexOf(setup);
  return i === -1 ? 100 : i;
}

/**
 * One ACTIVE card per locked setup 1–6, but a pinned `selectedId` always
 * occupies that setup's slot so WS upserts / reorders cannot steal highlight.
 */
export function pinSetupCards(signals: Signal[], selectedId: string | null): Signal[] {
  const byId = new Map(signals.map((s) => [s.id, s]));
  const selected = selectedId ? byId.get(selectedId) ?? null : null;
  const active = [...signals]
    .filter((s) => s.status === "ACTIVE")
    .sort((a, b) => b.ts_ms - a.ts_ms || a.id.localeCompare(b.id));

  const slot = new Map<SetupType, Signal>();
  if (selected && (SETUP_TYPES as readonly string[]).includes(selected.setup_type)) {
    slot.set(selected.setup_type, selected);
  }
  for (const row of active) {
    if (!(SETUP_TYPES as readonly string[]).includes(row.setup_type)) continue;
    if (!slot.has(row.setup_type)) slot.set(row.setup_type, row);
  }

  return SETUP_TYPES.map((type) => slot.get(type)).filter((row): row is Signal => !!row);
}

/** Resolve the live row for a pinned id; keep the last snapshot if WS dropped it. */
export function resolveSelected(
  signals: Signal[],
  selectedId: string | null,
  snapshot: Signal | null,
): Signal | null {
  if (!selectedId) return null;
  return signals.find((s) => s.id === selectedId) ?? (snapshot?.id === selectedId ? snapshot : null);
}

export function overlayForFilter(setup: SetupType | "all"): OverlayPreset | null {
  if (setup === "all") return null;
  return overlayForSetup(setup);
}
