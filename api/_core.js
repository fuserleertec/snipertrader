'use strict';
/*
 * Kronos Foundation Model — shared backend core.
 * ------------------------------------------------------------------
 * Used by BOTH:
 *   - local dev (`node api/_server.js`, a long-lived http server), and
 *   - Vercel serverless functions (api/*.js, each exports `handler`).
 *
 * Keep all inference + data-proxy logic here so the two runtimes never
 * diverge. Zero dependencies (Node built-ins only).
 */
const https = require('https');
const fs = require('fs');
const path = require('path');

// Zero-dependency .env loader (does not overwrite existing process env vars).
// Only meaningful for local dev; Vercel injects secrets as real env vars.
(function loadEnv() {
  try {
    const p = path.join(__dirname, '.env');
    if (!fs.existsSync(p)) return;
    fs.readFileSync(p, 'utf8').split(/\r?\n/).forEach(line => {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
      if (!m) return;
      const k = m[1], v = m[2].replace(/^["']|["']$/g, '');
      if (process.env[k] === undefined) process.env[k] = v;
    });
  } catch (_) {}
})();

const { aiChat, isConfigured, PROVIDERS } = require('./_ai_providers');

const MAX_CTX = 512;
const TOK_PER_BAR = 3.0;
const MAX_BARS = Math.floor(MAX_CTX / TOK_PER_BAR); // 170 bars = 510 tok

/* ── rng + stats (identical to frontend for parity) ── */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function gauss(rng) {
  let u = 0, v = 0;
  while (u === 0) u = rng();
  while (v === 0) v = rng();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
function quantile(sorted, q) {
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor(q * sorted.length)));
  return sorted[idx];
}
function genHistory(n, rng) {
  let price = 100 + rng() * 50, bars = [];
  const vbase = 1200 + rng() * 5000;
  for (let i = 0; i < n; i++) {
    const o = price;
    const step = (rng() - 0.5) * 0.012 + 0.0004;
    const c = o * (1 + step + gauss(rng) * 0.011);
    const h = Math.max(o, c) * (1 + Math.abs(gauss(rng)) * 0.009);
    const l = Math.min(o, c) * (1 - Math.abs(gauss(rng)) * 0.009);
    const v = Math.round(vbase * (0.7 + 0.6 * rng()));
    bars.push({ o, h, l, c, v }); price = c;
  }
  return bars;
}
function genPaths(lastClose, rng, st) {
  const paths = [];
  for (let p = 0; p < st.paths; p++) {
    let price = lastClose; const path = [price];
    for (let t = 0; t < st.horizon; t++) {
      const step = st.drift + gauss(rng) * st.vol * st.temp;
      price = price * (1 + step); path.push(price);
    }
    paths.push(path);
  }
  return paths;
}
function computeBands(paths) {
  const H = paths[0].length - 1, out = { p5: [], p25: [], p50: [], p75: [], p95: [], spread: [] };
  for (let t = 1; t <= H; t++) {
    const col = paths.map(p => p[t]).sort((a, b) => a - b);
    out.p5.push(quantile(col, 0.05)); out.p25.push(quantile(col, 0.25));
    out.p50.push(quantile(col, 0.5)); out.p75.push(quantile(col, 0.75));
    out.p95.push(quantile(col, 0.95));
    out.spread.push((col[col.length - 1] - col[0]) / col[0]);
  }
  return out;
}
function computeStats(lastClose, paths, bands) {
  const end = bands.p50.length - 1;
  const ret = (bands.p50[end] / lastClose - 1) * 100;
  const up = paths.filter(p => p[p.length - 1] > lastClose).length / paths.length * 100;
  const var5 = (bands.p5[end] / lastClose - 1) * 100;
  const meanSpread = bands.spread.reduce((a, b) => a + b, 0) / bands.spread.length;
  const ent = Math.log(1 + meanSpread * 100 * paths.length) / Math.log(1 + 100);
  return { ret: +ret.toFixed(2), up: +up.toFixed(1), var5: +var5.toFixed(2), ent: +ent.toFixed(3) };
}

/* ── REAL MODEL HOOK (the seam for actual model inference) ── */
async function runModel({ history, config, requestedBars }) {
  const rng = mulberry32(config.seed >>> 0 || 0x9E3779B1);
  const synthetic = !(history && history.length);
  let bars = synthetic ? genHistory(config.bars, rng) : history;
  const truncated = synthetic && requestedBars > MAX_BARS;
  if (truncated) bars = bars.slice(-MAX_BARS);
  const lastClose = bars[bars.length - 1].c;
  const paths = genPaths(lastClose, rng, config);
  const bands = computeBands(paths);
  const stats = computeStats(lastClose, paths, bands);
  return {
    history: bars,
    paths,
    bands,
    stats,
    meta: { backend: 'kronos-reference', max_context: MAX_CTX, truncated }
  };
}

/* ── ALPACA equity k-lines (server-side only) ── */
const ALPACA_TF = { '1m': '1Min', '5m': '5Min', '15m': '15Min', '1h': '1Hour', '1d': '1Day', '4h': '4Hour' };
const ALPACA_TF_MS = { '1Min': 60e3, '5Min': 300e3, '15Min': 900e3, '1Hour': 3600e3, '4Hour': 14400e3, '1Day': 86400e3 };
const MAX_ALPACA = 512; // Kronos max_context ceiling
function alpacaBars({ symbol, timeframe, limit }) {
  return new Promise((resolve, reject) => {
    const key = process.env.ALPACA_API_KEY, sec = process.env.ALPACA_SECRET_KEY;
    if (!key || !sec) return reject(new Error('Alpaca credentials not configured — set ALPACA_API_KEY and ALPACA_SECRET_KEY'));
    const tf = ALPACA_TF[timeframe] || '1Hour';
    const sym = String(symbol || '').toUpperCase();
    const lim = Math.max(1, Math.min(MAX_ALPACA, parseInt(limit, 10) || MAX_ALPACA));
    const lookback = (ALPACA_TF_MS[tf] || 3600e3) * lim * 3;
    const start = new Date(Date.now() - lookback).toISOString();
    const q = `symbols=${encodeURIComponent(sym)}&timeframe=${tf}&limit=${lim}&adjustment=split&feed=iex&start=${encodeURIComponent(start)}`;
    const req = https.request({
      hostname: 'data.alpaca.markets',
      path: `/v2/stocks/bars?${q}`,
      method: 'GET',
      headers: { 'Apca-Api-Key-Id': key, 'Apca-Api-Secret-Key': sec, 'Accept': 'application/json' }
    }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        if (res.statusCode >= 400) {
          let m = 'Alpaca HTTP ' + res.statusCode;
          try { const e = JSON.parse(body); if (e && (e.message || e.error)) m = e.message || e.error; } catch (_) {}
          return reject(new Error(m));
        }
        try {
          const j = JSON.parse(body);
          const arr = (j.bars && j.bars[sym]) || [];
          const out = arr.map(b => ({
            timestamp: b.timestamp || (typeof b.t === 'string' ? b.t : new Date((b.t || 0) * 1000).toISOString()),
            open: +b.o, high: +b.h, low: +b.l, close: +b.c, volume: +b.v
          }));
          resolve(out);
        } catch (e) { reject(new Error('Alpaca response parse error: ' + e.message)); }
      });
    });
    req.on('error', e => reject(new Error('Alpaca request failed: ' + e.message)));
    req.setTimeout(15000, () => req.destroy(new Error('Alpaca timeout')));
    req.end();
  });
}

/* ── FORECAST handler ── */
function buildForecast(req, res) {
  let body = '';
  req.on('data', c => { body += c; if (body.length > 1e6) req.destroy(); });
  req.on('end', async () => {
    let payload;
    try { payload = JSON.parse(body || '{}'); }
    catch (e) { res.writeHead(400, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ error: 'invalid JSON' })); }
    const cfg = payload.config || {};
    const num = (v, d) => { const n = Number(v); return Number.isFinite(n) ? n : d; };
    const requestedBars = Math.max(1, Math.floor(num(cfg.bars, 80)));
    const config = {
      bars: Math.max(8, requestedBars),
      horizon: Math.max(4, Math.min(60, Math.floor(num(cfg.horizon, 24)))),
      paths: Math.max(1, Math.min(128, Math.floor(num(cfg.paths, 16)))),
      temp: Math.max(0.1, Math.min(2.5, num(cfg.temp, 1.0))),
      vol: Math.max(0.003, Math.min(0.06, num(cfg.vol, 0.018))),
      drift: Math.max(-0.005, Math.min(0.005, num(cfg.drift, 0.0002))),
      seed: Math.floor(num(cfg.seed, 0x9E3779B1)) >>> 0
    };
    try {
      const out = await runModel({ history: Array.isArray(payload.history) ? payload.history : null, config, requestedBars });
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(out));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: String(e && e.message || e) }));
    }
  });
}

/* ── STOCKS handler ── */
function buildStocks(req, res, url) {
  const symbol = (url.searchParams.get('symbol') || 'AAPL').trim();
  const timeframe = url.searchParams.get('timeframe') || url.searchParams.get('interval') || '1h';
  const limit = Math.max(1, Math.min(MAX_ALPACA, parseInt(url.searchParams.get('limit') || '512', 10) || MAX_ALPACA));
  alpacaBars({ symbol, timeframe, limit })
    .then(out => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(out)); })
    .catch(e => { res.writeHead(502, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: String(e && e.message || e) })); });
}

/* ── AI CHAT handler ── */
function buildChat(req, res) {
  let body = '';
  req.on('data', c => { body += c; if (body.length > 1e5) req.destroy(); });
  req.on('end', async () => {
    let payload;
    try { payload = JSON.parse(body || '{}'); }
    catch (e) { res.writeHead(400, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ error: 'invalid JSON' })); }
    const provider = String(payload.provider || 'deepseek').toLowerCase();
    if (!PROVIDERS[provider]) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: 'unknown provider — use deepseek or kimi' }));
    }
    if (!isConfigured(provider)) {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: PROVIDERS[provider].label + ' API key not configured on the server' }));
    }
    try {
      const r = await aiChat({
        provider,
        messages: Array.isArray(payload.messages) ? payload.messages : [{ role: 'user', content: String(payload.prompt || '') }],
        options: { model: payload.model, maxTokens: payload.maxTokens, temperature: payload.temperature }
      });
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ provider: PROVIDERS[provider].label, model: r.provider, content: r.content }));
    } catch (e) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: String(e && e.message || e) }));
    }
  });
}


/* ── ALPACA trading API (paper by default) ── */
function alpacaGet(pathname) {
  return new Promise((resolve, reject) => {
    const key = process.env.ALPACA_API_KEY, sec = process.env.ALPACA_SECRET_KEY;
    if (!key || !sec) return reject(new Error('Alpaca credentials not configured — set ALPACA_API_KEY and ALPACA_SECRET_KEY'));
    const host = process.env.ALPACA_TRADE_HOST || 'paper-api.alpaca.markets';
    const p = pathname.startsWith('/') ? pathname : '/' + pathname;
    const req = https.request({
      hostname: host,
      path: p,
      method: 'GET',
      headers: { 'Apca-Api-Key-Id': key, 'Apca-Api-Secret-Key': sec, 'Accept': 'application/json' }
    }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        if (res.statusCode >= 400) {
          let m = 'Alpaca HTTP ' + res.statusCode;
          try { const e = JSON.parse(body); if (e && (e.message || e.error)) m = e.message || e.error; } catch (_) {}
          return reject(new Error(m));
        }
        try { resolve(JSON.parse(body || '{}')); }
        catch (e) { reject(new Error('Alpaca response parse error: ' + e.message)); }
      });
    });
    req.on('error', e => reject(new Error('Alpaca request failed: ' + e.message)));
    req.setTimeout(15000, () => req.destroy(new Error('Alpaca timeout')));
    req.end();
  });
}

function toNum(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? n : (d === undefined ? 0 : d);
}

/* ── PROP ACCOUNT aggregator (GET /api/prop/account) ── */
function buildPropAccount(req, res, url) {
  Promise.all([
    alpacaGet('/v2/account'),
    alpacaGet('/v2/positions'),
    alpacaGet('/v2/orders?status=closed&limit=20&direction=desc'),
    alpacaGet('/v2/account/portfolio/history?period=1M&timeframe=1D')
  ]).then(([acct, positions, orders, history]) => {
    const equity = toNum(acct && acct.equity);
    const lastEquity = toNum(acct && acct.last_equity);
    const dayPnl = +(equity - lastEquity).toFixed(2);
    const payload = {
      broker: 'alpaca-paper',
      account: {
        id: (acct && acct.id) || '',
        number: (acct && acct.account_number) || '',
        status: (acct && acct.status) || '',
        equity,
        cash: toNum(acct && acct.cash),
        buying_power: toNum(acct && acct.buying_power),
        last_equity: lastEquity,
        day_pnl: dayPnl,
        portfolio_value: toNum(acct && (acct.portfolio_value || acct.equity)),
        trading_blocked: !!(acct && acct.trading_blocked)
      },
      positions: Array.isArray(positions) ? positions.map(p => ({
        symbol: p.symbol,
        qty: toNum(p.qty),
        side: p.side,
        market_value: toNum(p.market_value),
        unrealized_pl: toNum(p.unrealized_pl),
        avg_entry_price: toNum(p.avg_entry_price),
        current_price: toNum(p.current_price)
      })) : [],
      orders: Array.isArray(orders) ? orders.map(o => ({
        id: o.id,
        symbol: o.symbol,
        side: o.side,
        qty: toNum(o.filled_qty != null && o.filled_qty !== '' ? o.filled_qty : o.qty),
        filled_avg_price: toNum(o.filled_avg_price),
        filled_at: o.filled_at || o.updated_at || o.submitted_at || null,
        status: o.status,
        type: o.type
      })) : [],
      history: {
        timestamp: (history && history.timestamp) || [],
        equity: (history && history.equity) || [],
        profit_loss: (history && history.profit_loss) || []
      }
    };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(payload));
  }).catch(e => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: String(e && e.message || e) }));
  });
}

module.exports = {
  MAX_CTX, MAX_BARS,
  mulberry32, gauss, genHistory, genPaths, computeBands, computeStats, runModel,
  alpacaBars, alpacaGet, buildForecast, buildStocks, buildChat, buildPropAccount,
  aiChat, isConfigured, PROVIDERS
};
