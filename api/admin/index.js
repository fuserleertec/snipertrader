'use strict';
// Vercel serverless function: GET /api/admin  (and /api/admin/all)
// Returns the full admin dashboard payload. Dispatches through handlers.js.
const { buildAdmin } = require('./handlers');
module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PATCH, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  const url = new URL(req.url, 'http://localhost');
  buildAdmin(req, res, url);
};
