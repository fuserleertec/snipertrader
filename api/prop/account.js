'use strict';
// Vercel serverless function: GET /api/prop/account
const { buildPropAccount } = require('../_core');

module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  if (req.method !== 'GET') {
    res.status(404).json({ error: 'not found — GET /api/prop/account' });
    return;
  }
  const url = new URL(req.url, 'http://localhost');
  buildPropAccount(req, res, url);
};
