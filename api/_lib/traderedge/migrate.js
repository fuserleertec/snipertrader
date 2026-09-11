'use strict';
/**
 * api/_lib/traderedge/migrate.js — idempotent schema migration.
 *
 * Run once: `node api/_lib/traderedge/migrate.js`
 *
 * NOTE ON STORAGE: TimescaleDB is NOT available on this Supabase instance
 * (Postgres 17.6 — `create extension timescaledb` → "extension not available").
 * The ATPE event stream is LOW-VOLUME (sessions, trades, interventions — not
 * market ticks), so a plain table with a (trader_id, ts DESC) index is the
 * correct, honest choice here; a hypertable would be premature optimization.
 */
const db = require('./db');

const SCHEMA = `
create table if not exists traderedge_events (
  event_id          uuid primary key default gen_random_uuid(),
  ts                timestamptz not null default now(),
  trader_id         text not null default 'local-trader',
  fingerprint_version int not null default 1,
  type              text not null,              -- preflight|trade|outcome|override|intervention|regime
  source            text not null default 'self-report',  -- self-report|device|platform
  payload           jsonb not null default '{}'::jsonb
);
create index if not exists idx_events_trader_ts on traderedge_events (trader_id, ts desc);

create table if not exists traderedge_nodes (
  node_id    text primary key,
  type       text not null,   -- Trader|FingerprintVersion|PsychState|Regime|Decision|Outcome|Intervention
  props      jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists traderedge_edges (
  edge_id    text primary key,
  from_node  text not null references traderedge_nodes(node_id) on delete cascade,
  to_node    text not null references traderedge_nodes(node_id) on delete cascade,
  kind       text not null default 'association',  -- association|causal
  posterior  jsonb not null default '{"alpha":1,"beta":1,"n":0,"ci95":null}'::jsonb,
  updated_at timestamptz not null default now()
);
create index if not exists idx_edges_from on traderedge_edges (from_node);
create index if not exists idx_edges_to   on traderedge_edges (to_node);

create table if not exists traderedge_interventions (
  intervention_id uuid primary key default gen_random_uuid(),
  ts              timestamptz not null default now(),
  trader_id       text not null default 'local-trader',
  event_id        uuid references traderedge_events(event_id) on delete set null,
  level           int not null,        -- 0 none | 1 nudge | 2 friction | 3 gate
  action          text not null,
  message         text not null,
  decision        text,                -- accept|override|null (filled on response)
  note            text,
  responded_at    timestamptz
);
create index if not exists idx_interv_trader_ts on traderedge_interventions (trader_id, ts desc);
`;

async function run() {
  if (!db.isConfigured()) {
    console.error('ERROR: SUPABASE_DATABASE_URL not configured (api/.env).');
    process.exit(1);
  }
  try {
    await db.query(SCHEMA);
    const t = await db.query(
      "select table_name from information_schema.tables where table_schema='public' and table_name like 'traderedge_%' order by table_name"
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
