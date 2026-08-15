'use strict';
/**
 * admin/store.js — demo data layer for the admin dashboard.
 *
 * IMPORTANT: This is a clearly-labeled DEMO data store. It is NOT production
 * telemetry. The platform has no user/session/license/billing database yet
 * (no Supabase/Firebase/Stripe bindings exist in this repo), so the admin
 * dashboard's domain concepts (discipline scores, day streaks, product keys,
 * invoices) are served from this seed + a JSON file mirror.
 *
 * To go live: replace load()/save() with calls to your real datastore and keep
 * the same payload shapes returned by handlers.js.
 *
 * Zero dependencies (Node built-ins only) so it runs both in the local dev
 * server (api/_server.js) and as a Vercel serverless function.
 */
const fs = require('fs');
const path = require('path');

const SEED_PATH = path.join(__dirname, 'seed.json');
const STORE_PATH = path.join(__dirname, 'store.json'); // created at runtime on first write

let cache = null;

function deepClone(o) { return JSON.parse(JSON.stringify(o)); }

function load() {
  if (cache) return cache;
  let data;
  if (fs.existsSync(STORE_PATH)) {
    try { data = JSON.parse(fs.readFileSync(STORE_PATH, 'utf8')); }
    catch (_) { data = null; }
  }
  if (!data) {
    data = JSON.parse(fs.readFileSync(SEED_PATH, 'utf8'));
  }
  // Stamp demo provenance on every response so the UI can label it honestly.
  data.meta = data.meta || {};
  data.meta.isDemo = true;
  data.meta.source = fs.existsSync(STORE_PATH) ? 'store.json (runtime mirror)' : 'seed.json (factory)';
  cache = data;
  return data;
}

function save(next) {
  cache = next;
  try {
    fs.writeFileSync(STORE_PATH, JSON.stringify(next, null, 2));
    return true;
  } catch (e) {
    // Read-only filesystem (Vercel serverless) — degrade to in-memory only.
    return false;
  }
}

module.exports = { load, save, deepClone, SEED_PATH, STORE_PATH };
