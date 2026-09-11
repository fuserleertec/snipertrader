'use strict';
// TraderEdge ATPE — Vercel dynamic route (counts as ONE function, preserving
// the 12-fn Hobby cap). Dispatches on the path segment so URLs stay identical:
//   POST /api/traderedge/preflight  -> existing buildPreflight (byte-compatible)
//   POST /api/traderedge/ingest     -> append event to the temporal stream (L1)
//   GET  /api/traderedge/graph      -> current Bayesian posteriors (L2)
//   POST /api/traderedge/intervene  -> fusion-gated graduated intervention (L3/L4)
//   POST /api/traderedge/outcome    -> log result + update posteriors (closes loop)
//   POST /api/traderedge/override   -> deliberate override (labeled training data)
const { buildPreflight } = require('../_core');
const engine = require('../_lib/traderedge');

function setCors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

module.exports = async (req, res) => {
  setCors(res);
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  const url = new URL(req.url, 'http://localhost');
  const action = (url.pathname.split('/').pop() || '').toLowerCase();

  try {
    switch (action) {
      case 'preflight':
        if (req.method !== 'POST') { res.status(404).json({ error: 'not found — POST /api/traderedge/preflight' }); return; }
        return buildPreflight(req, res);
      case 'ingest':
        if (req.method !== 'POST') { res.status(404).json({ error: 'not found — POST /api/traderedge/ingest' }); return; }
        return engine.ingest(req, res);
      case 'graph':
        if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/traderedge/graph' }); return; }
        return engine.graph(req, res);
      case 'intervene':
        if (req.method !== 'POST') { res.status(404).json({ error: 'not found — POST /api/traderedge/intervene' }); return; }
        return engine.intervene(req, res);
      case 'outcome':
        if (req.method !== 'POST') { res.status(404).json({ error: 'not found — POST /api/traderedge/outcome' }); return; }
        return engine.outcome(req, res);
      case 'override':
        if (req.method !== 'POST') { res.status(404).json({ error: 'not found — POST /api/traderedge/override' }); return; }
        return engine.override(req, res);
      case 'diag':
        if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/traderedge/diag' }); return; }
        return engine.diag(req, res);
      default:
        res.status(404).json({ error: 'unknown traderedge action: ' + action });
    }
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
