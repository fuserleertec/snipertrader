'use strict';
// Vercel serverless function: PATCH /api/admin/profile
// Exact match takes precedence over /api/admin/[resource].js on Vercel,
// so PATCH lands here. Dispatches through the same handler for parity.
const { buildAdmin } = require('../_lib/admin/handlers');
module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PATCH, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  const url = new URL(req.url, 'http://localhost');
  buildAdmin(req, res, url);
};
