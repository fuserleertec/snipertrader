'use strict';
// api/recon/[action].js — Vercel dynamic route (counts as ONE function).
// Consolidates the three former recon endpoints into a single dispatcher to
// stay within the 12-function Hobby cap:
//   GET /api/recon/picks     -> handlePicks (full multi-factor scan, cached)
//   GET /api/recon/refresh   -> run(true) + persist snapshot (cron / GH Actions)
//   GET /api/recon/health    -> liveness + cache-state probe
const fs = require('fs');
const path = require('path');
const { handlePicks, run, health } = require('../_lib/recon/run');

function setCors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

module.exports = async (req, res) => {
  setCors(res);
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  const url = new URL(req.url, 'http://localhost');
  const action = (url.pathname.split('/').pop() || '').toLowerCase();

  try {
    switch (action) {
      case 'picks': {
        if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/recon/picks' }); return; }
        return handlePicks(req, res);
      }
      case 'refresh': {
        if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/recon/refresh' }); return; }
        const token = req.query && req.query.token;
        const expected = process.env.RECON_CRON_TOKEN || 'local-dev';
        if (token !== expected && process.env.NODE_ENV === 'production') {
          return res.status(401).json({ error: 'unauthorized' });
        }
        const payload = await run(true);
        try { fs.writeFileSync('/tmp/recon_cache.json', JSON.stringify(payload)); } catch (_) {}
        try { fs.writeFileSync(path.join(__dirname, '..', '..', 'data', 'recon.json'), JSON.stringify(payload, null, 2)); } catch (_) {}
        return res.json({ ok: true, picks: payload.picks.length, generatedAt: payload.generatedAt });
      }
      case 'health': {
        if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/recon/health' }); return; }
        res.setHeader('Cache-Control', 'no-store');
        const h = health();
        // env probe (booleans only — never values) to diagnose key wiring at runtime.
        h.env = { alpaca: !!process.env.ALPACA_API_KEY, alpacaSecret: !!process.env.ALPACA_SECRET_KEY, polygon: !!process.env.POLYGON_API_KEY };
        return res.json(h);
      }
      default:
        return res.status(404).json({ error: 'unknown recon action: ' + action });
    }
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
