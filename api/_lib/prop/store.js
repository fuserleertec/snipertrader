'use strict';
/**
 * prop/store.js — persisted dataset for the Prop-Firm Intelligence pipeline.
 *
 * The canonical dataset is `data/prop_firms.json` (committed to the repo and
 * served to the static page as a no-JS fallback). A serverless function CANNOT
 * rewrite the git repo at runtime, so `save()` best-effort writes the repo file
 * (works in local dev + on the GitHub Actions runner) and always mirrors to
 * /tmp (works everywhere, per-instance). The API reads /tmp first (freshest),
 * then the committed file.
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..', '..');
const DATA_PATH = path.join(ROOT, 'data', 'prop_firms.json');
const TMP_CACHE = '/tmp/prop_firms_cache.json';

let cache = null;

function deepClone(o) { return JSON.parse(JSON.stringify(o)); }

function load() {
  if (cache) return deepClone(cache);
  let data = null;
  if (fs.existsSync(TMP_CACHE)) {
    try { data = JSON.parse(fs.readFileSync(TMP_CACHE, 'utf8')); } catch (_) { data = null; }
  }
  if (!data && fs.existsSync(DATA_PATH)) {
    try { data = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8')); } catch (_) { data = null; }
  }
  if (!data || !Array.isArray(data.firms)) data = { firms: [], meta: {} };
  cache = data;
  return deepClone(data);
}

/**
 * Persist. Returns true if the repo file was written (i.e. we're on a writable
 * FS such as local dev or GH Actions), false if only /tmp could be written.
 */
function save(data) {
  cache = data;
  let wroteRepo = false;
  try { fs.writeFileSync(DATA_PATH, JSON.stringify(data, null, 2)); wroteRepo = true; } catch (_) { /* read-only FS */ }
  try { fs.writeFileSync(TMP_CACHE, JSON.stringify(data)); } catch (_) { /* no /tmp either */ }
  return wroteRepo;
}

module.exports = { load, save, deepClone, DATA_PATH, TMP_CACHE };
