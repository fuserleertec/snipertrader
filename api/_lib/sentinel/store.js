'use strict';
/**
 * api/_lib/sentinel/store.js — parameterized pg query layer for the Sentinel
 * admin. All writes use $1..$n parameters (no string interpolation) and RETURNING.
 * Consumed by the future admin endpoint / Edge Function. Reuses the
 * SUPABASE_* connection helper from traderedge (same Supabase project).
 *
 * NOTE: no auth is enforced here — that lives in the API/Edge layer (RBAC:
 * admin / affiliate_manager / read_only) before any of these are callable.
 */
const db = require('../traderedge/db');

async function createAffiliate(a) {
  const r = await db.query(
    `insert into sentinel_affiliates
       (id, email, name, handle, tier, status, sponsor_id, referral_code,
        tracking_method, audience, platforms, payout_method, tax_form_status)
     values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13)
     returning *`,
    [a.id, a.email || null, a.name, a.handle || null, a.tier || 'recruit', a.status || 'pending',
     a.sponsorId || null, a.referralCode, a.trackingMethod || 'link', a.audience || null,
     JSON.stringify(a.platforms || []), a.payoutMethod || null, a.taxFormStatus || 'not_collected']
  );
  return r.rows[0];
}

async function getAffiliate(id) {
  const r = await db.query('select * from sentinel_affiliates where id = $1', [id]);
  return r.rows[0] || null;
}

async function listAffiliates() {
  const r = await db.query('select * from sentinel_affiliates order by joined_at desc');
  return r.rows;
}

async function logReferral(r) {
  const row = await db.query(
    `insert into sentinel_referrals
       (affiliate_id, customer_email, product_slug, attribution_window_days, first_touch_at, conversion_at, status, metadata)
     values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb) returning *`,
    [r.affiliateId, r.customerEmail || null, r.productSlug, r.windowDays || 60,
     r.firstTouchAt || null, r.conversionAt || null, r.status || 'pending', JSON.stringify(r.metadata || {})]
  );
  return row.rows[0];
}

async function logAttributionTouch(t) {
  await db.query(
    `insert into sentinel_attribution_log (referral_id, touch_affiliate_id, touch_at, is_winner, resolved_by, note)
     values ($1,$2,$3,$4,$5,$6)`,
    [t.referralId, t.affiliateId, t.touchAt, !!t.isWinner, t.resolvedBy || 'auto-last-touch', t.note || null]
  );
}

async function createCommission(c) {
  const row = await db.query(
    `insert into sentinel_commissions
       (referral_id, affiliate_id, type, amount_cents, currency, status, rule_snapshot, period_start, period_end)
     values ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9) returning *`,
    [c.referralId || null, c.affiliateId, c.type, c.amountCents, c.currency || 'USD',
     c.status || 'pending', JSON.stringify(c.ruleSnapshot || {}), c.periodStart || null, c.periodEnd || null]
  );
  return row.rows[0];
}

async function createPayout(p) {
  const row = await db.query(
    `insert into sentinel_payouts (affiliate_id, amount_cents, currency, status, method, period_start, period_end, notes)
     values ($1,$2,$3,$4,$5,$6,$7,$8) returning *`,
    [p.affiliateId, p.amountCents, p.currency || 'USD', p.status || 'queued', p.method || null,
     p.periodStart || null, p.periodEnd || null, p.notes || null]
  );
  return row.rows[0];
}

async function logTierChange(t) {
  const row = await db.query(
    `insert into sentinel_tier_audit (affiliate_id, from_tier, to_tier, trigger, triggered_by, reason)
     values ($1,$2,$3,$4,$5,$6) returning *`,
    [t.affiliateId, t.fromTier || null, t.toTier, t.trigger || 'manual', t.triggeredBy || null, t.reason || null]
  );
  return row.rows[0];
}

async function appendAudit(a) {
  await db.query(
    `insert into sentinel_audit_log (actor_id, action, target_id, before_state, after_state)
     values ($1,$2,$3,$4::jsonb,$5::jsonb)`,
    [a.actorId || null, a.action, a.targetId || null,
     JSON.stringify(a.before || null), JSON.stringify(a.after || null)]
  );
}

module.exports = {
  createAffiliate, getAffiliate, listAffiliates,
  logReferral, logAttributionTouch, createCommission, createPayout,
  logTierChange, appendAudit
};
