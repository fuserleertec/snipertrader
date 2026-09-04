'use strict';
// GET /api/recon/health — cheap liveness + cache-state probe (no re-scrape).
const { health } = require('./picks');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/recon/health' }); return; }
  res.json(health());
};
