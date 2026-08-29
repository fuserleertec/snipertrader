'use strict';
// GET /api/prop/firms — ranked prop-firm intelligence feed.
// Reads the committed data/prop_firms.json (or the /tmp crawl cache if fresher),
// computes the Sniper Score, applies optional query filters, and returns the
// ranked list. Public data → no auth. Supports: ?market=forex|futures|both,
// ?model=1-step|2-step|instant, ?q= (name search).
const { load } = require('../_lib/prop/store');
const { rank } = require('../_lib/prop/score');

const FILTER_KEYS = ['market', 'model'];

function matches(f, key, want) {
  const v = f[key];
  const list = Array.isArray(v) ? v : [v];
  return list.some((x) => String(x || '').toLowerCase() === String(want).toLowerCase());
}

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/prop/firms' }); return; }

  try {
    const url = new URL(req.url, 'http://localhost');
    const data = load();
    let firms = rank(data.firms || []);

    for (const key of FILTER_KEYS) {
      const want = url.searchParams.get(key);
      if (want) firms = firms.filter((f) => matches(f, key, want));
    }
    const q = url.searchParams.get('q');
    if (q) {
      const needle = q.toLowerCase();
      firms = firms.filter((f) => (f.name || '').toLowerCase().includes(needle) || (f.id || '').toLowerCase().includes(needle));
    }

    res.setHeader('Cache-Control', 'public, s-maxage=1800, stale-while-revalidate');
    res.json({
      generatedAt: new Date().toISOString(),
      meta: {
        ...(data.meta || {}),
        count: firms.length,
        total: (data.firms || []).length
      },
      firms
    });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
