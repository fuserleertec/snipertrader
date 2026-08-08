'use strict';
// Vercel serverless function: GET /api/stocks/klines
const { buildStocks } = require('../_core');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'GET') {
    res.status(404).json({ error: 'not found — GET /api/stocks/klines' });
    return;
  }
  const url = new URL(req.url, 'http://localhost');
  buildStocks(req, res, url);
};
