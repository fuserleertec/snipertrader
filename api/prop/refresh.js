'use strict';
// GET /api/prop/refresh — the cron entry point (invoked by Vercel Cron + the
// GitHub Actions fallback). Token-guarded in production. Crawls every firm,
// persists (repo file on a writable FS / GH Actions runner, /tmp elsewhere),
// and returns a summary.
const { refreshAll } = require('../_lib/prop/crawler');
const store = require('../_lib/prop/store');

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/prop/refresh' }); return; }

  const url = new URL(req.url, 'http://localhost');
  const token = url.searchParams.get('token');
  const expected = process.env.PROP_CRON_TOKEN || 'local-dev';
  if (token !== expected && process.env.NODE_ENV === 'production') {
    return res.status(401).json({ error: 'unauthorized' });
  }

  try {
    const { data, summary } = await refreshAll(store);
    const wroteRepo = store.save(data);
    res.json({
      ok: true,
      generatedAt: data.meta.last_refreshed,
      updated: summary.updated,
      failed: summary.failed,
      persisted: wroteRepo ? 'repo' : 'tmp-only',
      results: summary.results
    });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
