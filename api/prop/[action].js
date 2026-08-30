'use strict';
// Consolidated Prop-Firm API — Vercel dynamic route (counts as ONE function).
// Dispatches on the path segment so the original URLs stay identical:
//   GET /api/prop/firms    -> ranked prop-firm intelligence feed
//   GET /api/prop/account  -> Alpaca paper-account hydration (via _core)
//   GET /api/prop/refresh  -> cron crawl/refresh (token-guarded in prod)
const { load } = require('../_lib/prop/store');
const { rank } = require('../_lib/prop/score');
const { buildPropAccount } = require('../_core');
const { refreshAll } = require('../_lib/prop/crawler');
const store = require('../_lib/prop/store');

function setCors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

// ── GET /api/prop/firms ──
function firms(url, res) {
  const data = load();
  let list = rank(data.firms || []);
  const market = url.searchParams.get('market');
  const model = url.searchParams.get('model');
  if (market) list = list.filter((f) => {
    const v = Array.isArray(f.market) ? f.market : [f.market];
    return v.some((x) => String(x || '').toLowerCase() === market.toLowerCase());
  });
  if (model) list = list.filter((f) => {
    const v = Array.isArray(f.model) ? f.model : [f.model];
    return v.some((x) => String(x || '').toLowerCase() === model.toLowerCase());
  });
  const q = url.searchParams.get('q');
  if (q) {
    const needle = q.toLowerCase();
    list = list.filter((f) =>
      (f.name || '').toLowerCase().includes(needle) ||
      (f.id || '').toLowerCase().includes(needle));
  }
  res.setHeader('Cache-Control', 'public, s-maxage=1800, stale-while-revalidate');
  res.json({
    generatedAt: new Date().toISOString(),
    meta: { ...(data.meta || {}), count: list.length, total: (data.firms || []).length },
    firms: list
  });
}

module.exports = async (req, res) => {
  setCors(res);
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  const url = new URL(req.url, 'http://localhost');
  const action = (url.pathname.split('/').pop() || '').toLowerCase();

  try {
    if (action === 'firms') {
      if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/prop/firms' }); return; }
      return firms(url, res);
    }
    if (action === 'account') {
      if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/prop/account' }); return; }
      return buildPropAccount(req, res, url);
    }
    if (action === 'refresh') {
      if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/prop/refresh' }); return; }
      const token = url.searchParams.get('token');
      const expected = process.env.PROP_CRON_TOKEN || 'local-dev';
      if (token !== expected && process.env.NODE_ENV === 'production') {
        return res.status(401).json({ error: 'unauthorized' });
      }
      const { data, summary } = await refreshAll(store);
      const wroteRepo = store.save(data);
      return res.json({
        ok: true,
        generatedAt: data.meta.last_refreshed,
        updated: summary.updated,
        failed: summary.failed,
        persisted: wroteRepo ? 'repo' : 'tmp-only',
        results: summary.results
      });
    }
    res.status(404).json({ error: 'unknown prop action: ' + action });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
