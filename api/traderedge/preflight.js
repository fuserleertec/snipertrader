'use strict';
// Vercel serverless function: POST /api/traderedge/preflight
// TraderEdge Pre-Flight Protocol — validates the consolidated neural-baseline +
// 9-gate payload, recomputes authorization server-side, and persists the record
// to the admin oversight store. See buildPreflight in api/_core.js.
const { buildPreflight } = require('../_core');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'POST') {
    res.status(404).json({ error: 'not found — POST /api/traderedge/preflight with the Pre-Flight payload' });
    return;
  }
  buildPreflight(req, res);
};
