'use strict';
// Vercel serverless function: POST /api/review-loop/analyze
// Runs the Daily Stock Analysis engine (adapted from ZhuLinsen/daily_stock_analysis)
// over a watchlist of tickers. Returns a strict, validated JSON payload per ticker.
const { buildReviewLoop } = require('../_core');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'POST') {
    res.status(404).json({ error: 'not found — POST /api/review-loop/analyze with { tickers: ["AAPL","NVDA","TSLA"] }' });
    return;
  }
  buildReviewLoop(req, res);
};
