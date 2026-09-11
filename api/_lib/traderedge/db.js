'use strict';
/**
 * api/_lib/traderedge/db.js — Supabase Postgres connection helper (pg).
 *
 * Connection config accepts EITHER:
 *   SUPABASE_DATABASE_URL                      (full postgres:// URI)
 *   SUPABASE_HOST / SUPABASE_PORT / SUPABASE_USER / SUPABASE_PASSWORD / SUPABASE_DB
 *
 * Separate vars are PREFERRED when present — they avoid URL-encoding pitfalls
 * for passwords containing special characters (e.g. '*'), and they let Vercel
 * store the password verbatim.
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

const SSL = { rejectUnauthorized: false };
const URL_CONN = process.env.SUPABASE_DATABASE_URL;
const HOST = process.env.SUPABASE_HOST;
const PASSWORD = process.env.SUPABASE_PASSWORD;

function cfg() {
  if (HOST && PASSWORD) {
    return {
      host: HOST,
      port: Number(process.env.SUPABASE_PORT) || 5432,
      user: process.env.SUPABASE_USER || 'postgres',
      password: PASSWORD,
      database: process.env.SUPABASE_DB || 'postgres',
      ssl: SSL
    };
  }
  return { connectionString: URL_CONN, ssl: SSL };
}

function isConfigured() { return !!(URL_CONN || (HOST && PASSWORD)); }

// Non-secret diagnostic of the resolved connection config (no password).
function diag() {
  return {
    separateVars: !!(HOST && PASSWORD),
    host: HOST || null,
    user: process.env.SUPABASE_USER || null,
    port: process.env.SUPABASE_PORT || null,
    database: process.env.SUPABASE_DB || null,
    hasUrl: !!URL_CONN
  };
}

let pool = null;
function getPool() {
  if (!pool) pool = new Pool({ ...cfg(), max: 4, connectionTimeoutMillis: 8000 });
  return pool;
}

/**
 * query(text, params) — serverless-safe query facade.
 * On Vercel: fresh Client per call. Locally: reuse the pool.
 */
async function query(text, params) {
  if (!isConfigured()) throw new Error('SUPABASE_DATABASE_URL (or SUPABASE_HOST + SUPABASE_PASSWORD) not configured');
  if (process.env.VERCEL) {
    const c = new Client({ ...cfg(), connectionTimeoutMillis: 8000 });
    await c.connect();
    try { return await c.query(text, params); }
    finally { await c.end(); }
  }
  return getPool().query(text, params);
}

module.exports = { query, isConfigured, cfg, diag };
