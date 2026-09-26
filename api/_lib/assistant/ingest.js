'use strict';
/**
 * api/_lib/assistant/ingest.js — ingest markdown docs into assistant_chunks.
 *
 * Hash-idempotent: only re-embeds chunks whose text actually changed, and
 * preserves real chunk_index ordering across partial re-ingests. With no
 * embeddings provider, chunks are stored with NULL embedding and remain
 * full-text searchable.
 *
 * Run:  node api/_lib/assistant/ingest.js [paths...]
 *       (default: docs/**\/*.md  +  docs/**\/*.txt  +  content/**\/*)
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const db = require('../traderedge/db');
const { chunkMarkdown } = require('./chunking');
const { embedMany, isConfigured } = require('./embeddings');

const CATEGORY_MAP = [
  ['indicators', 'indicators'],
  ['market_intelligence', 'market_intelligence'],
  ['pricing', 'pricing'],
  ['faq', 'faq']
];

function inferCategory(p) {
  const lp = p.toLowerCase();
  for (const [key, val] of CATEGORY_MAP) if (lp.includes(key)) return val;
  return null;
}

function inferAccess(p) {
  // docs/public/** and content/** are visitor-facing; everything else
  // (internal design / security / copy docs) is internal-only.
  const lp = p.toLowerCase();
  if (lp.includes('/public/') || lp.includes('/content/') || lp.includes('public-')) return 'public';
  return 'internal';
}

function sha256(s) { return crypto.createHash('sha256').update(s).digest('hex'); }

function walk(dir, out) {
  out = out || [];
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch (_) { return out; }
  for (const ent of entries) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(full, out);
    else if (/\.(md|txt)$/i.test(ent.name)) out.push(full);
  }
  return out;
}

async function ingestFile(p) {
  const raw = fs.readFileSync(p, 'utf8');
  const docHash = sha256(raw);
  const title = path.basename(p);
  const category = inferCategory(p);
  const access = inferAccess(p);

  const d = await db.query(
    `insert into assistant_documents (source_path, title, category, access, content_hash)
     values ($1, $2, $3, $4, $5)
     on conflict (source_path) do update
       set title = excluded.title,
           category = excluded.category,
           access = excluded.access,
           content_hash = excluded.content_hash,
           updated_at = now()
     returning id`,
    [p, title, category, access, docHash]
  );
  const docId = d.rows[0].id;

  const chunks = chunkMarkdown(raw).map(c => ({ ...c, hash: sha256(c.content) }));

  const ex = await db.query('select content_hash from assistant_chunks where document_id = $1', [docId]);
  const existingSet = new Set(ex.rows.map(r => r.content_hash));
  const fresh = chunks.filter(c => !existingSet.has(c.hash));

  const vecByHash = new Map();
  if (fresh.length && isConfigured()) {
    const vecs = await embedMany(fresh.map(c => c.content));
    fresh.forEach((c, i) => vecByHash.set(c.hash, vecs[i]));
  }

  // Drop stale chunks (guard the empty-array case: `= any('{}')` is NULL).
  if (chunks.length === 0) {
    await db.query('delete from assistant_chunks where document_id = $1', [docId]);
  } else {
    await db.query(
      'delete from assistant_chunks where document_id = $1 and not (content_hash = any($2::text[]))',
      [docId, chunks.map(c => c.hash)]
    );
  }

  // Write/refresh every chunk at its real index in the full ordered list.
  for (let i = 0; i < chunks.length; i++) {
    const c = chunks[i];
    if (existingSet.has(c.hash)) {
      await db.query(
        'update assistant_chunks set chunk_index = $1, section = $2 where document_id = $3 and content_hash = $4',
        [i, c.section, docId, c.hash]
      );
    } else {
      const vec = vecByHash.get(c.hash);
      const vecParam = vec ? '[' + vec.map(n => Number(n)).join(',') + ']' : null;
      await db.query(
        `insert into assistant_chunks (document_id, chunk_index, section, content, content_hash, embedding)
         values ($1, $2, $3, $4, $5, ${vecParam ? '$6::vector' : 'null'})
         on conflict (document_id, content_hash) do nothing`,
        vecParam ? [docId, i, c.section, c.content, c.hash, vecParam] : [docId, i, c.section, c.content, c.hash]
      );
    }
  }

  return { path: p, chunks: chunks.length, fresh: fresh.length, embedded: vecByHash.size };
}

async function main() {
  if (!db.isConfigured()) {
    console.error('ERROR: Supabase not configured (SUPABASE_DATABASE_URL / SUPABASE_HOST + SUPABASE_PASSWORD).');
    process.exit(1);
  }
  let files = process.argv.slice(2);
  if (!files.length) {
    files = [];
    for (const dir of ['docs', 'content']) {
      if (fs.existsSync(dir)) files = files.concat(walk(dir));
    }
    files = [...new Set(files)].sort();
  }
  console.log(`Ingesting ${files.length} file(s). Embeddings: ${isConfigured() ? 'ON' : 'OFF (full-text only)'}`);
  for (const p of files) {
    try {
      const r = await ingestFile(p);
      console.log(`  ${r.path}: ${r.chunks} chunks, ${r.fresh} new, ${r.embedded} embedded`);
    } catch (e) {
      console.error(`  FAILED ${p}: ${e.message}`);
    }
  }
  process.exit(0);
}

if (require.main === module) main();
module.exports = { ingestFile, chunkMarkdown, inferCategory, inferAccess };
