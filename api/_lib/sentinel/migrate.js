'use strict';
/**
 * api/_lib/sentinel/migrate.js — Sentinel Affiliate Program schema.
 *
 * Idempotent (create table if not exists) — run once:
 *   node api/_lib/sentinel/migrate.js
 *
 * HONEST ADAPTATION vs the original build spec:
 *  - The spec assumed FK -> users(id) and FK -> products(id). Neither table
 *    exists on this Supabase instance (the platform has no user/session or
 *    product-catalog tables yet — only traderedge_*). So those columns are
 *    TEXT identifiers (customer_email / product_slug / actor_id) with no FK.
 *    When a real auth + catalog lands, these become FKs in a follow-up migration.
 *  - TimescaleDB is NOT available (Postgres 17.6). Plain indexed tables are the
 *    correct choice for affiliate volume; no hypertables.
 */
const db = require('../traderedge/db'); // reuse the SUPABASE_* connection helper

const SCHEMA = `
-- Affiliates (one row per Sentinel)
create table if not exists sentinel_affiliates (
  id              text primary key,               -- e.g. 'SEN-7K2-A3'
  email           text,                           -- no users table yet; account email
  name            text not null,
  handle          text,
  tier            text not null default 'recruit'
                  check (tier in ('recruit','operative','commander','ghost')),
  status          text not null default 'pending'
                  check (status in ('pending','active','suspended','terminated')),
  sponsor_id      text references sentinel_affiliates(id) on delete set null,
  referral_code   text unique not null,
  tracking_method text not null default 'link'
                  check (tracking_method in ('link','coupon','postback')),
  audience        text,
  platforms       jsonb not null default '[]'::jsonb,
  payout_method   text check (payout_method in ('stripe','paypal','crypto','wire')),
  payout_details  jsonb not null default '{}'::jsonb,  -- encrypt at rest in real deploy (AES-256, key in secret manager)
  tax_form_status text not null default 'not_collected'
                  check (tax_form_status in ('not_collected','w9_collected','w8_collected')),
  joined_at       timestamptz not null default now(),
  approved_at     timestamptz,
  last_active_at  timestamptz
);
create index if not exists idx_aff_refcode on sentinel_affiliates(referral_code);
create index if not exists idx_aff_sponsor on sentinel_affiliates(sponsor_id);

-- Commission rules with effective dates (rate changes are auditable)
create table if not exists sentinel_commission_rules (
  id             text primary key,
  tier           text not null,
  product_slug   text not null,                    -- '*' = all products
  type           text not null check (type in
                   ('direct','recurring','override','bundle_bonus','cross_product','revenue_share')),
  rate           numeric not null,                -- 0.25 = 25%
  effective_from timestamptz not null default now(),
  effective_to   timestamptz,
  note           text
);

-- Referrals (attribution target)
create table if not exists sentinel_referrals (
  id                     uuid primary key default gen_random_uuid(),
  affiliate_id           text not null references sentinel_affiliates(id) on delete cascade,
  customer_email         text,                    -- no users table yet
  product_slug           text not null,
  attribution_window_days int not null default 60,
  first_touch_at         timestamptz,
  conversion_at          timestamptz,
  status                 text not null default 'pending'
                         check (status in ('pending','approved','rejected','refunded')),
  metadata               jsonb not null default '{}'::jsonb
);
create index if not exists idx_ref_aff on sentinel_referrals(affiliate_id, conversion_at desc);

-- Every attribution touch, with the winner flagged (dispute resolution source)
create table if not exists sentinel_attribution_log (
  id             uuid primary key default gen_random_uuid(),
  referral_id    uuid references sentinel_referrals(id) on delete cascade,
  touch_affiliate_id text not null,
  touch_at       timestamptz not null,
  is_winner      boolean not null default false,
  resolved_by    text not null default 'auto-last-touch',  -- auto-last-touch | auto-first-touch | manual
  note           text
);
create index if not exists idx_attrib_ref on sentinel_attribution_log(referral_id);

-- Commissions — snapshot the applicable rule at conversion time (auditable)
create table if not exists sentinel_commissions (
  id             uuid primary key default gen_random_uuid(),
  referral_id    uuid references sentinel_referrals(id) on delete set null,
  affiliate_id   text not null references sentinel_affiliates(id) on delete cascade,
  type           text not null check (type in
                   ('direct','recurring','override','bundle_bonus','cross_product','revenue_share')),
  amount_cents   integer not null,
  currency       char(3) not null default 'USD',
  status         text not null default 'pending'
                 check (status in ('pending','approved','paid','clawed_back','rejected')),
  rule_snapshot  jsonb not null default '{}'::jsonb,  -- rate + base at conversion
  period_start   timestamptz,
  period_end     timestamptz,
  created_at     timestamptz not null default now()
);
create index if not exists idx_com_aff on sentinel_commissions(affiliate_id, created_at desc);
create index if not exists idx_com_status on sentinel_commissions(status);

-- Payouts
create table if not exists sentinel_payouts (
  id             uuid primary key default gen_random_uuid(),
  affiliate_id   text not null references sentinel_affiliates(id) on delete cascade,
  amount_cents   integer not null,
  currency       char(3) not null default 'USD',
  status         text not null default 'queued'
                 check (status in ('queued','processing','completed','failed','reversed')),
  method         text check (method in ('stripe','paypal','crypto','wire')),
  transaction_ref text,
  period_start   timestamptz,
  period_end     timestamptz,
  processed_at   timestamptz,
  notes          text
);
create index if not exists idx_pay_aff on sentinel_payouts(affiliate_id, processed_at desc);

-- Tier changes (manual / automated / dispute), full audit trail
create table if not exists sentinel_tier_audit (
  id            uuid primary key default gen_random_uuid(),
  affiliate_id  text not null references sentinel_affiliates(id) on delete cascade,
  from_tier     text,
  to_tier       text not null,
  trigger       text not null check (trigger in ('manual','automated','dispute')),
  triggered_by  text,                              -- actor (no users table yet)
  reason        text,
  created_at    timestamptz not null default now()
);
create index if not exists idx_tier_aff on sentinel_tier_audit(affiliate_id, created_at desc);

-- Append-only audit log for every mutation (never exposed to affiliates)
create table if not exists sentinel_audit_log (
  id           uuid primary key default gen_random_uuid(),
  actor_id     text,
  action       text not null,
  target_id    text,
  before_state jsonb,
  after_state  jsonb,
  created_at   timestamptz not null default now()
);
`;

async function run() {
  if (!db.isConfigured()) {
    console.error('ERROR: SUPABASE_DATABASE_URL (or SUPABASE_HOST + SUPABASE_PASSWORD) not configured.');
    process.exit(1);
  }
  try {
    await db.query(SCHEMA);
    const t = await db.query(
      "select table_name from information_schema.tables where table_schema='public' and table_name like 'sentinel_%' order by table_name"
    );
    console.log('Migration OK. Tables:', t.rows.map(r => r.table_name).join(', '));
    process.exit(0);
  } catch (e) {
    console.error('Migration FAILED:', e.message);
    process.exit(1);
  }
}

if (require.main === module) run();
module.exports = { run, SCHEMA };
