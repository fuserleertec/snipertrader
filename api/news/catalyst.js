'use strict';
// api/news/catalyst.js — GET /api/news/catalyst?symbol=NVDA
// LLM-scored news + SEC EDGAR catalyst for the Market Forecaster (one Vercel
// function; the heavy lifting lives in _lib/news/catalyst.js).
const { newsCatalyst } = require('../_lib/news/catalyst');

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/news/catalyst' }); return; }
  const url = new URL(req.url, 'http://localhost');
  const sym = (url.searchParams.get('symbol') || '').trim();
  if (!sym) { res.status(400).json({ error: 'missing symbol' }); return; }
  try {
    res.json(await newsCatalyst(sym));
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
