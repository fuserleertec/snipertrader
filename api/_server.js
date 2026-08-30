#!/usr/bin/env node
/*
 * Kronos backend — LOCAL DEV server (long-lived http server).
 * For production this repo deploys the same logic as Vercel serverless
 * functions (api/kronos/forecast.js, api/stocks/klines.js, api/ai/chat.js,
 * api/prop/account.js), all sharing api/_core.js. This file is for
 * `node api/_server.js` dev only.
 */
'use strict';
const http = require('http');
const { buildForecast, buildStocks, buildChat, buildReviewLoop, buildPreflight } = require('./_core');
const { buildAdmin } = require('./_lib/admin/handlers');
const propApi = require('./prop/[action]');

const PORT = process.env.KRONOS_PORT || 8787;

// Vercel-style res shim for the standalone prop handlers (they use res.json/res.status).
function vc(res) {
  if (!res.json) {
    res.json = function (o) { if (!res.headersSent) res.writeHead(res.statusCode || 200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(o)); };
    res.status = function (c) { res.statusCode = c; return res; };
  }
  return res;
}

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }

  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (url.pathname === '/api/stocks/klines' && req.method === 'GET') {
    return buildStocks(req, res, url);
  }
  if (url.pathname.startsWith('/api/prop/')) {
    return propApi(req, vc(res));
  }
  if (url.pathname === '/api/ai/chat' && req.method === 'POST') {
    return buildChat(req, res);
  }
  if (url.pathname === '/api/kronos/forecast' && req.method === 'POST') {
    return buildForecast(req, res);
  }
  if (url.pathname === '/api/review_loop/analyze' && req.method === 'POST') {
    return buildReviewLoop(req, res);
  }
  if (url.pathname === '/api/traderedge/preflight' && req.method === 'POST') {
    return buildPreflight(req, res);
  }
  if (url.pathname.startsWith('/api/admin')) {
    return buildAdmin(req, res, url);
  }
  if (url.pathname === '/api/debug/alpaca' && req.method === 'POST') {
    const { buildHandler } = require('./_debug_alpaca');
    return buildHandler('iex')(req, res);
  }
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'not found — POST /api/kronos/forecast' }));
});

server.listen(PORT, () => console.log(`Kronos inference backend on http://localhost:${PORT}/api/kronos/forecast`));
