// _shared/engine.ts — deterministic Sentinel commission rules (Deno port of
// api/_lib/sentinel/engine.js). Kept in sync with the Node version so the
// server-side Edge Functions and the Node/Vercel layer agree exactly.
export const RATES: Record<string, Record<string, number>> = {
  recruit:   { direct: 0.20, recurring: 0.00, override: 0.00, bundle: 0.00, cross: 0.00 },
  operative: { direct: 0.25, recurring: 0.15, override: 0.00, bundle: 0.00, cross: 0.03 },
  commander: { direct: 0.32, recurring: 0.22, override: 0.05, bundle: 0.08, cross: 0.03 },
  ghost:     { direct: 0.40, recurring: 0.30, override: 0.10, bundle: 0.08, cross: 0.03 },
};

export function rate(tier: string, kind: string): number {
  if (!RATES[tier]) throw new Error("Unknown tier: " + tier);
  return RATES[tier][kind] || 0;
}

export function pct(cents: number, p: number): number {
  return Math.round(cents * p);
}

export function computeDirect(tier: string, saleCents: number) {
  const r = rate(tier, "direct");
  return { cents: pct(saleCents, r), rule: { type: "direct", rate: r, baseCents: saleCents } };
}

export function computeOverride(sponsorTier: string, saleCents: number) {
  const r = rate(sponsorTier, "override");
  return { cents: pct(saleCents, r), rule: { type: "override", rate: r, baseCents: saleCents } };
}
