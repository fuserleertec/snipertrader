#!/usr/bin/env node
/*
 * Kronos Foundation Model — inference backend (reference server)
 * ------------------------------------------------------------
 * Pure Node, ZERO dependencies. Exposes:
 *     POST /api/kronos/forecast
 *
 * GitHub Pages is static and CANNOT run this. Host it separately
 * (VPS / serverless / Cloudflare Worker) and point the frontend's
 * API_BASE at it. The page degrades gracefully to local simulation
 * when the backend is unreachable.
 *
 * Request body:
 *   { "config": { bars, horizon, paths, temp, vol, drift, seed },
 *     "history"?: [ {o,h,l,c,v}, ... ] }   // optional real OHLCV window
 *
 * Response:
 *   { history, paths, bands:{p5,p25,p50,p75,p95,spread},
 *     stats:{ret,up,var5,ent}, meta:{backend,truncated} }
 */
'use strict';
const http = require('http');

const PORT = process.env.KRONOS_PORT || 8787;
const MAX_CTX = 512;
const TOK_PER_BAR = 3.0;
const MAX_BARS = Math.floor(MAX_CTX / TOK_PER_BAR); // 170 bars = 510 tok

/* ── rng + stats (kept identical to frontend for parity) ── */
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

/* ───────────────────────────────────────────────────────────
 *  REAL MODEL HOOK
 *  This is the seam where actual model inference plugs in.
 *  Input  : history (array of OHLCV) + config (sampling params)
 *  Output : { history, paths, bands, stats }  (bands shape must match)
 *  Replace the body with e.g. a fetch() to your model service,
 *  an ONNX runtime call, or an LLM tool-call. Keep the shape.
 * ─────────────────────────────────────────────────────────── */
async function runModel({ history, config, requestedBars }) {
  const rng = mulberry32(config.seed >>> 0 || 0x9E3779B1);
  const synthetic = !(history && history.length);
  let bars = synthetic ? genHistory(config.bars, rng) : history;
  // Enforce the 512-token ceiling. Synthetic bars are capped silently; flag it
  // when the *requested* count exceeded what the ceiling permits.
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

/* ── http server ── */
const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); return res.end(); }
  if (req.url !== '/api/kronos/forecast' || req.method !== 'POST') {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ error: 'not found — POST /api/kronos/forecast' }));
  }
  let body = '';
  req.on('data', c => { body += c; if (body.length > 1e6) req.destroy(); });
  req.on('end', async () => {
    let payload;
    try { payload = JSON.parse(body || '{}'); }
    catch (e) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: 'invalid JSON' }));
    }
    const cfg = payload.config || {};
    const num = (v, d) => { const n = Number(v); return Number.isFinite(n) ? n : d; };
    const requestedBars = Math.max(1, Math.floor(num(cfg.bars, 80)));
    const config = {
      bars: Math.max(8, requestedBars),   // runModel enforces the 512-tok ceiling
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
});
server.listen(PORT, () => console.log(`Kronos inference backend on http://localhost:${PORT}/api/kronos/forecast`));
