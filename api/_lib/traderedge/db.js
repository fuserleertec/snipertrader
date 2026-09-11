'use strict';
/**
 * api/_lib/traderedge/db.js — Supabase Postgres connection helper (pg).
 *
 * Connects to SUPABASE_DATABASE_URL. Local dev uses a long-lived Pool; Vercel
 * serverless uses a short-lived Client per call (pools don't survive the
 * invocation). Mirrors the zero-dep .env loader already used in _core.js.
 */
const { Pool, Client } = require('pg');

// Local-dev .env loader (no-op on Vercel, which injects real env vars).
(function loadEnv() {
  try {
    const fs = require('fs'), path = require('path');
    const p = path.join(__dirname, '..', '..', '.env'); // api/.env
    if (!fs.existsSync(p)) return;
    fs.readFileSync(p, 'utf8').split(/\r?\n/).forEach(line => {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
      if (!m) return;
      if (process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
    });
  } catch (_) {}
})();

const CONN = process.env.SUPABASE_DATABASE_URL;
const SSL = { rejectUnauthorized: false };

let pool = null;
function getPool() {
  if (!pool) pool = new Pool({ connectionString: CONN, ssl: SSL, max: 4, connectionTimeoutMillis: 8000 });
  return pool;
}

/**
 * query(text, params) — serverless-safe query facade.
 * On Vercel: fresh Client per call. Locally: reuse the pool.
 */
async function query(text, params) {
  if (!CONN) throw new Error('SUPABASE_DATABASE_URL not configured');
  if (process.env.VERCEL) {
    const c = new Client({ connectionString: CONN, ssl: SSL, connectionTimeoutMillis: 8000 });
    await c.connect();
    try { return await c.query(text, params); }
    finally { await c.end(); }
  }
  return getPool().query(text, params);
}

function isConfigured() { return !!CONN; }

module.exports = { query, isConfigured, CONN };
