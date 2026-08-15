'use strict';
// Vercel serverless function: GET /api/admin/<resource>
// <resource> ∈ profile|overview|alerts|sessions|modules|licenses|
//              billing|notifications|security|downloads
const { buildAdmin } = require('./handlers');
module.exports = (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PATCH, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  const url = new URL(req.url, 'http://localhost');
  buildAdmin(req, res, url);
};
