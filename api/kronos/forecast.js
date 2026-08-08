'use strict';
// Vercel serverless function: POST /api/kronos/forecast
const { buildForecast } = require('../_core');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'POST') {
    res.status(404).json({ error: 'not found — POST /api/kronos/forecast' });
    return;
  }
  buildForecast(req, res);
};
