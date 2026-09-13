'use strict';
/**
 * api/_lib/sentinel/engine.js — deterministic Sentinel commission + attribution
 * engine. PURE functions (no DB, no I/O, no side effects) so every rule is
 * unit-testable and every payout is reproducible.
 *
 * This is the code form of the "Commission Terms" published on
 * sentinel_program.html. It resolves the exact ambiguities the audit flagged:
 *   - attribution = LAST-touch within the window (first-touch available as an
 *     explicit, logged override) — never ambiguous between two affiliates;
 *   - sub-affiliate override = a % of the SPONSORED AFFILIATE'S SALE VALUE,
 *     NOT their commission (5% commander / 10% ghost);
 *   - cross-product +3% = of each extra product's net sale;
 *   - bundle +8% = of the bundle net sale, on top of base commission.
 *
 * Money is integer CENTS everywhere (no floating point in payouts).
 */

const RATES = {
  recruit:   { direct: 0.20, recurring: 0.00, override: 0.00, bundle: 0.00, cross: 0.00 },
  operative: { direct: 0.25, recurring: 0.15, override: 0.00, bundle: 0.00, cross: 0.03 },
  commander: { direct: 0.32, recurring: 0.22, override: 0.05, bundle: 0.08, cross: 0.03 },
  ghost:     { direct: 0.40, recurring: 0.30, override: 0.10, bundle: 0.08, cross: 0.03 }
};
const TIERS = Object.keys(RATES);

function rate(tier, kind) {
  if (!RATES[tier]) throw new Error('Unknown tier: ' + tier);
  return RATES[tier][kind] || 0;
}

/** round cents * percentage, half-up, always integer cents */
function pct(cents, p) { return Math.round(cents * p); }

/**
 * resolveAttribution(touches, opts)
 *   touches: [{ affiliateId, at }]  (at = ISO string or Date or epoch ms)
 *   opts: { mode = 'last' | 'first', windowDays = 60, now = Date.now() }
 * Returns { winnerAffiliateId | null, mode, touches: [{...t, qualified, isWinner}] }
 */
function resolveAttribution(touches, opts = {}) {
  const mode = opts.mode === 'first' ? 'first' : 'last';
  const windowDays = opts.windowDays || 60;
  const now = opts.now || Date.now();
  const winMs = windowDays * 86400000;
  const norm = touches.map(t => ({ ...t, ts: new Date(t.at).getTime() }));
  const qualified = norm.filter(t => (now - t.ts) <= winMs);
  const annotated = norm.map(t => ({ ...t, qualified: qualified.indexOf(t) !== -1 }));
  if (!qualified.length) return { winnerAffiliateId: null, mode, touches: annotated };
  const sorted = [...qualified].sort((a, b) => a.ts - b.ts);
  const winner = mode === 'first' ? sorted[0] : sorted[sorted.length - 1];
  return {
    winnerAffiliateId: winner.affiliateId,
    mode,
    touches: annotated.map(t => ({ affiliateId: t.affiliateId, at: t.at, qualified: t.qualified, isWinner: t.affiliateId === winner.affiliateId && t.ts === winner.ts }))
  };
}

/** Direct commission: rate(tier) * sale value */
function computeDirect(tier, saleCents) {
  const r = rate(tier, 'direct');
  return { cents: pct(saleCents, r), rule: { type: 'direct', rate: r, baseCents: saleCents } };
}

/** Recurring commission: rate(tier) * renewal value. Recruit = 0 (no recurring). */
function computeRecurring(tier, renewalCents) {
  const r = rate(tier, 'recurring');
  return { cents: pct(renewalCents, r), rule: { type: 'recurring', rate: r, baseCents: renewalCents } };
}

/**
 * Sub-affiliate override — THE audit's key ambiguity.
 * Calculated on the SPONSORED AFFILIATE'S SALE VALUE, not their commission.
 * Commander 5%, Ghost 10%. Recruit/Operative = 0 (cannot sponsor).
 */
function computeOverride(sponsorTier, saleCents) {
  const r = rate(sponsorTier, 'override');
  return { cents: pct(saleCents, r), rule: { type: 'override', rate: r, baseCents: saleCents, note: 'on sponsored affiliate sale value' } };
}

/** Ecosystem bundle bonus: rate(tier) * bundle net sale, on top of base. */
function computeBundleBonus(tier, bundleCents) {
  const r = rate(tier, 'bundle');
  return { cents: pct(bundleCents, r), rule: { type: 'bundle_bonus', rate: r, baseCents: bundleCents } };
}

/** Cross-product bonus: rate(tier) * each extra product's net sale. */
function computeCrossProduct(tier, extraCents) {
  const r = rate(tier, 'cross');
  return { cents: pct(extraCents, r), rule: { type: 'cross_product', rate: r, baseCents: extraCents } };
}

function isRecurringEligible(tier) { return rate(tier, 'recurring') > 0; }
function canSponsor(tier) { return rate(tier, 'override') > 0; }

module.exports = {
  RATES, TIERS, rate, pct,
  resolveAttribution,
  computeDirect, computeRecurring, computeOverride, computeBundleBonus, computeCrossProduct,
  isRecurringEligible, canSponsor
};
