'use strict';
/**
 * api/_lib/sentinel/rls.js — enable RLS + RBAC policies on the sentinel tables.
 *
 * Roles are read from the request JWT: auth.jwt() -> 'app_metadata' ->> 'role'
 *   - admin             : full CRUD on every table
 *   - affiliate_manager : SELECT all + UPDATE commissions (approve/reject)
 *   - read_only         : SELECT all
 *   - anon (no JWT)     : nothing
 * service_role and postgres bypass RLS (standard Supabase behavior), so the
 * Edge Functions and this migration keep working through the server-side key.
 *
 * Idempotent — run once (or any time): node api/_lib/sentinel/rls.js
 */
const db = require('../traderedge/db');

const SQL = `
create or replace function sentinel_role() returns text
language sql stable as $$
  select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', 'anon')
$$;

do $$
declare t text;
begin
  foreach t in array array[
    'sentinel_affiliates','sentinel_referrals','sentinel_attribution_log',
    'sentinel_commissions','sentinel_commission_rules','sentinel_payouts',
    'sentinel_tier_audit','sentinel_audit_log'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I_select on %I', t, t);
    execute format('create policy %I_select on %I for select using (sentinel_role() in (''admin'',''affiliate_manager'',''read_only''))', t, t);
    execute format('drop policy if exists %I_insert on %I', t, t);
    execute format('create policy %I_insert on %I for insert with check (sentinel_role() = ''admin'')', t, t);
    execute format('drop policy if exists %I_update on %I', t, t);
    execute format('create policy %I_update on %I for update using (sentinel_role() = ''admin'') with check (sentinel_role() = ''admin'')', t, t);
    execute format('drop policy if exists %I_delete on %I', t, t);
    execute format('create policy %I_delete on %I for delete using (sentinel_role() = ''admin'')', t, t);
  end loop;
end $$;

-- Exception: affiliate_manager can approve/reject commissions (UPDATE only).
drop policy if exists sentinel_commissions_manager_update on sentinel_commissions;
create policy sentinel_commissions_manager_update on sentinel_commissions
  for update using (sentinel_role() = 'affiliate_manager') with check (sentinel_role() = 'affiliate_manager');
`;

async function run() {
  if (!db.isConfigured()) { console.error('ERROR: DB not configured'); process.exit(1); }
  try {
    await db.query(SQL);
    const r = await db.query(
      "select relname, relrowsecurity from pg_class where relname like 'sentinel_%' and relkind='r' order by relname"
    );
    console.log('RLS applied. Tables:', r.rows.map(x => x.relname + (x.relrowsecurity ? '(rls ON)' : '(rls OFF)')).join(', '));
    process.exit(0);
  } catch (e) { console.error('RLS FAILED:', e.message); process.exit(1); }
}

if (require.main === module) run();
module.exports = { run, SQL };
