'use strict';
// GET /api/recon/health — cheap liveness + cache-state probe (no re-scrape).
const { health } = require('./picks');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/recon/health' }); return; }
  const h = health();
  // env probe (booleans only — never values) to diagnose key wiring in the runtime.
  h.env = { alpaca: !!process.env.ALPACA_API_KEY, alpacaSecret: !!process.env.ALPACA_SECRET_KEY, polygon: !!process.env.POLYGON_API_KEY };
  res.json(h);
};
