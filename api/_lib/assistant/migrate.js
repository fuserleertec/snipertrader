'use strict';
/**
 * api/_lib/assistant/migrate.js — SniperTrader.ai site-assistant schema.
 *
 * Postgres = Supabase (already wired via ../traderedge/db). pgvector ships on
 * Supabase, so `create extension if not exists vector` is safe.
 *
 * Honest adaptation vs the original v2 sketch:
 *  - plan_tier access-control DROPPED: the platform has no auth / tier system
 *    yet (same reason sentinel keeps TEXT identifiers, no FKs). Access control
 *    is `access = 'public' | 'internal'` — internal docs are ingested but never
 *    served to visitors by the public endpoint.
 *  - feedback.session_id, sessions.metadata, chunks.token_count DROPPED:
 *    session_id is recoverable via the message join; token_count needs tiktoken
 *    which this zero-dep backend does not carry.
 *  - sessions.ip_hash KEPT and populated (sha256 of client IP) for abuse tracking.
 *
 * Run once (idempotent):  node api/_lib/assistant/migrate.js
 */
const db = require('../traderedge/db');
const { dims } = require('./embeddings');

const VEC_DIMS = dims();

const SCHEMA = `
create extension if not exists vector;

create table if not exists assistant_documents (
  id           bigserial primary key,
  source_path  text not null unique,
  title        text not null,
  category     text,
  access       text not null default 'public' check (access in ('public','internal')),
  content_hash text not null,
  updated_at   timestamptz not null default now()
);

create table if not exists assistant_chunks (
  id           bigserial primary key,
  document_id  bigint not null references assistant_documents(id) on delete cascade,
  chunk_index  int not null,
  section      text,
  content      text not null,
  content_hash text not null,
  embedding    vector(${VEC_DIMS}),
  tsv          tsvector generated always as (to_tsvector('english', coalesce(section,'') || ' ' || content)) stored,
  created_at   timestamptz not null default now(),
  unique (document_id, content_hash)
);

create index if not exists assistant_chunks_embedding_hnsw on assistant_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists assistant_chunks_tsv_gin on assistant_chunks using gin (tsv);
create index if not exists assistant_chunks_doc_idx on assistant_chunks (document_id, chunk_index);

create table if not exists assistant_sessions (
  id           uuid primary key,
  created_at   timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  ip_hash      text,
  metadata     jsonb default '{}'::jsonb
);

create table if not exists assistant_messages (
  id                  bigserial primary key,
  session_id          uuid not null references assistant_sessions(id) on delete cascade,
  role                text not null check (role in ('user','assistant','system')),
  content             text not null,
  sources             jsonb,
  retrieved_chunk_ids bigint[],
  latency_ms          int,
  created_at          timestamptz not null default now()
);
create index if not exists assistant_messages_session_created_idx on assistant_messages (session_id, created_at desc);

create table if not exists assistant_feedback (
  id         bigserial primary key,
  message_id bigint references assistant_messages(id) on delete cascade,
  rating     smallint not null,
  reason     text,
  comment    text,
  created_at timestamptz not null default now()
);
`;

async function run() {
  if (!db.isConfigured()) {
    console.error('ERROR: SUPABASE_DATABASE_URL (or SUPABASE_HOST + SUPABASE_PASSWORD) not configured.');
    process.exit(1);
  }
  try {
    await db.query(SCHEMA);
    const r = await db.query(
      "select table_name from information_schema.tables where table_schema='public' and table_name like 'assistant_%' order by table_name"
    );
    console.log(`Migration OK (embedding dims=${VEC_DIMS}). Tables:`, r.rows.map(x => x.table_name).join(', '));
    process.exit(0);
  } catch (e) {
    console.error('Migration FAILED:', e.message);
    process.exit(1);
  }
}

if (require.main === module) run();
module.exports = { run, SCHEMA, VEC_DIMS };
