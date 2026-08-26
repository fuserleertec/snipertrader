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
function genPaths(lastClose, rng, st, volOverride) {
  const paths = [];
  const v = (volOverride !== undefined) ? volOverride : st.vol;
  for (let p = 0; p < st.paths; p++) {
    let price = lastClose; const path = [price];
    for (let t = 0; t < st.horizon; t++) {
      const step = st.drift + gauss(rng) * v * st.temp;
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
  const effVol = config.vol * (config.volInject || 1) * (1 + (config.newsShock || 0) / 100 * 0.8);
  const paths = genPaths(lastClose, rng, config, effVol);
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

/* ── MIROFISH SWARM + CONFLUENCE (honest server-side simulation) ──
   Mirrors the in-browser engine so the same-origin endpoint returns the
   full payload the multi-dimensional UI consumes. No live order flow. */
const SWARM_ARCHETYPES = [
  { id: 'MM',  name: 'Market Makers',     weight: 0.30, base: 0.50, color: 'cyan',   volatility: 0.6 },
  { id: 'SM',  name: 'Smart Money / ICT', weight: 0.30, base: 0.58, color: 'emerald', volatility: 0.4 },
  { id: 'RET', name: 'Retail Momentum',   weight: 0.20, base: 0.46, color: 'gold',    volatility: 1.2 },
  { id: 'QF',  name: 'Quant Funds',       weight: 0.20, base: 0.52, color: 'red',     volatility: 0.8 },
];
const clampN = (x, a, b) => Math.max(a, Math.min(b, x));
function computeSwarm(config) {
  const rng = mulberry32((config.seed >>> 0 || 0x9E3779B1) ^ 0x9E37);
  const swarmBias = config.swarmBias || 0;
  const newsShock = config.newsShock || 0;
  const agents = SWARM_ARCHETYPES.map(a => {
    const noise = (rng() - 0.5) * 0.12 * (1 + newsShock / 120);
    const longBias = clampN(a.base + swarmBias * 0.45 + noise, 0.02, 0.98);
    const activity = clampN(0.35 + 0.4 * Math.abs(swarmBias) + newsShock / 200 + rng() * 0.2, 0, 1);
    return { id: a.id, name: a.name, weight: a.weight, color: a.color,
      longBias: +longBias.toFixed(3), shortBias: +(1 - longBias).toFixed(3),
      activity: +activity.toFixed(3), vol: a.volatility };
  });
  const consensusUp = agents.reduce((s, a) => s + a.weight * a.longBias, 0);
  return { agents, consensusUp: +consensusUp.toFixed(3), netBias: +(consensusUp - 0.5).toFixed(3),
    aggAct: +agents.reduce((s, a) => s + a.weight * a.activity, 0).toFixed(3) };
}
function buildConfluence(bands, swarm) {
  const F = bands.p50.length;
  const bend = (swarm.netBias) * 2 * 0.10;
  const tailAmp = 0.05 + (swarm.newsShock || 0) / 100 * 0.30;
  const primary = [], secondary = [], tailRisk = [];
  for (let j = 0; j < F; j++) {
    const t = (j + 1) / F;
    const base = bands.p50[j];
    primary.push(+(base * (1 + bend * t)).toFixed(2));
    secondary.push(+(base * (1 - bend * 0.6 * t)).toFixed(2));
    const dir = swarm.netBias >= 0 ? -1 : 1;
    tailRisk.push(+(base * (1 + dir * tailAmp * t)).toFixed(2));
  }
  return { primary, secondary, tailRisk };
}
function detectICT(bars) {
  const n = bars.length, obs = [], fvgs = [], liq = [];
  for (let i = 2; i < n - 3; i++) {
    const up = bars[i + 1].c > bars[i + 1].o && bars[i + 2].c > bars[i + 2].o;
    const down = bars[i + 1].c < bars[i + 1].o && bars[i + 2].c < bars[i + 2].o;
    if (up && bars[i].c < bars[i].o) obs.push({ type: 'bull', price: bars[i].l, top: bars[i].h, bot: bars[i].l, idx: i });
    if (down && bars[i].c > bars[i].o) obs.push({ type: 'bear', price: bars[i].h, top: bars[i].h, bot: bars[i].l, idx: i });
  }
  for (let i = 0; i < n - 2; i++) {
    const gapBull = bars[i + 2].l - bars[i].h;
    if (gapBull > Math.abs(bars[i].c) * 0.0015) fvgs.push({ type: 'bull', top: bars[i + 2].l, bot: bars[i].h, idx: i });
    const gapBear = bars[i].l - bars[i + 2].h;
    if (gapBear > Math.abs(bars[i].c) * 0.0015) fvgs.push({ type: 'bear', top: bars[i].l, bot: bars[i + 2].h, idx: i });
  }
  for (let i = 2; i < n - 2; i++) {
    if (bars[i].h > bars[i - 1].h && bars[i].h > bars[i - 2].h && bars[i].h > bars[i + 1].h)
      liq.push({ type: 'sell', price: bars[i].h, idx: i });
    if (bars[i].l < bars[i - 1].l && bars[i].l < bars[i - 2].l && bars[i].l < bars[i + 1].l)
      liq.push({ type: 'buy', price: bars[i].l, idx: i });
  }
  return { obs: obs.slice(-4), fvgs: fvgs.slice(-4), liq: liq.slice(-4) };
}
/* Enriched model used by the multi-dimensional UI (adds mirofish/confluence/ict). */
async function runModelFull({ history, config, requestedBars }) {
  const base = await runModel({ history, config, requestedBars });
  const swarm = computeSwarm(config);
  const confluence = buildConfluence(base.bands, swarm);
  const ict = detectICT(base.history);
  return { ...base, mirofish: swarm, confluence, ict };
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
      seed: Math.floor(num(cfg.seed, 0x9E3779B1)) >>> 0,
      // MiroFish / confluence inputs (optional)
      volInject: Math.max(0.5, Math.min(3, num(cfg.volInject, 1))),
      swarmBias: Math.max(-1, Math.min(1, num(cfg.swarmBias, 0))),
      newsShock: Math.max(0, Math.min(100, num(cfg.newsShock, 0)))
    };
    try {
      const full = payload.mode === 'full' || payload.full === true;
      const out = full
        ? await runModelFull({ history: Array.isArray(payload.history) ? payload.history : null, config, requestedBars })
        : await runModel({ history: Array.isArray(payload.history) ? payload.history : null, config, requestedBars });
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

/* ─────────────────────────────────────────────────────────────────────────
 * DAILY ANALYSIS ENGINE  (adapted from ZhuLinsen/daily_stock_analysis)
 * -------------------------------------------------------------------------
 * Ported methodology (NOT a line-for-line copy of the A-share Python repo):
 *   - Multi-source price/technical context via Alpaca equity bars
 *     (the US-equity analogue of DSA's yfinance_fetcher priority path).
 *   - Technical indicators identical in spirit to DSA's analyzer:
 *     MA trend + MA distance, RSI(14), MACD, ATR, volume ratio.
 *   - The canonical DECISION_SCALE from DSA src/schemas/decision_scale.py:
 *     80-100 strong_buy · 60-79 buy · 40-59 watch(hold) ·
 *     20-39 reduce(sell) · 0-19 sell.  score + signal_key + action all
 *     expressed on the same scale.
 *   - LLM synthesis using the SAME dashboard quadrant contract DSA uses:
 *     core_conclusion (signal + score + one-line), data_perspective
 *     (technicals), intelligence (news/catalysts/risks), battle_plan
 *     (sniper entry/exit checkpoints, position sizing, risk checklist).
 *   - Strict, validated JSON output. When the AI key is absent or the model
 *     fails, a transparent deterministic heuristic path runs so the UI never
 *     breaks (mirrors DSA's data-fallback philosophy).
 * Reuses the existing alpacaBars() + aiChat()/PROVIDERS plumbing below.
 * ─────────────────────────────────────────────────────────────────────── */

/* ── technical indicators (vector math over OHLCV bars) ── */
function ema(arr, period) {
  const k = 2 / (period + 1);
  const out = [];
  let prev = arr[0];
  for (let i = 0; i < arr.length; i++) {
    prev = i === 0 ? arr[0] : arr[i] * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}
function sma(arr, period) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < arr.length; i++) {
    sum += arr[i];
    if (i >= period) sum -= arr[i - period];
    out.push(i >= period - 1 ? sum / period : null);
  }
  return out;
}
function rsi(close, period = 14) {
  if (close.length <= period) return null;
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = close[i] - close[i - 1];
    if (d >= 0) gain += d; else loss -= d;
  }
  gain /= period; loss /= period;
  if (loss === 0) return 100;
  const rs = gain / loss;
  return 100 - 100 / (1 + rs);
}
function macd(close, fast = 12, slow = 26, sig = 9) {
  if (close.length < slow + sig) return null;
  const ef = ema(close, fast), es = ema(close, slow);
  const dif = close.map((c, i) => c && es[i] != null ? ef[i] - es[i] : null).filter(v => v != null);
  const dea = ema(dif, sig);
  const hist = dif.map((d, i) => d - dea[i]);
  return { dif: +dif[dif.length - 1].toFixed(4), dea: +dea[dea.length - 1].toFixed(4), hist: +hist[hist.length - 1].toFixed(4) };
}
function calcATR(bars, period = 14) {
  if (bars.length <= period) return null;
  const tr = [bars[0].h - bars[0].l];
  for (let i = 1; i < bars.length; i++) {
    const pc = bars[i - 1].c;
    tr.push(Math.max(bars[i].h - bars[i].l, Math.abs(bars[i].h - pc), Math.abs(bars[i].l - pc)));
  }
  const atr = sma(tr, period).filter(v => v != null);
  return atr.length ? +atr[atr.length - 1].toFixed(4) : null;
}
function last(arr, n = 20) { return arr.slice(-n); }

/* ── DSA canonical decision scale (src/schemas/decision_scale.py) ── */
const DECISION_SCALE = [
  { min: 80, max: 100, signal: 'strong_buy', action: 'buy',  decision_type: 'buy',  label: 'STRONG BUY' },
  { min: 60, max: 79,  signal: 'buy',        action: 'buy',  decision_type: 'buy',  label: 'BUY' },
  { min: 40, max: 59,  signal: 'watch',      action: 'watch', decision_type: 'hold', label: 'WATCH' },
  { min: 20, max: 39,  signal: 'reduce',     action: 'reduce', decision_type: 'sell', label: 'REDUCE' },
  { min: 0,  max: 19,  signal: 'sell',       action: 'sell',  decision_type: 'sell', label: 'SELL' }
];
function scaleForScore(score) {
  const s = Math.max(0, Math.min(100, Math.round(score)));
  const band = DECISION_SCALE.find(b => s >= b.min && s <= b.max) || DECISION_SCALE[DECISION_SCALE.length - 1];
  return { score: s, signal: band.signal, action: band.action, decision_type: band.decision_type, label: band.label };
}

/* ── deterministic heuristic (no-AI fallback) ── */
function heuristicAnalysis(tkr, bars) {
  const clean = (bars || []).filter(b => b && Number.isFinite(b.c));
  const close = clean.map(b => b.c);
  const vol = clean.map(b => (Number.isFinite(b.v) ? b.v : 0));
  if (!close.length) return { ticker: tkr, name: tkr, price: null, change_pct: null, signal: 'watch', action: 'watch', decision_type: 'hold', score: 50, score_label: 'WATCH', one_liner: `${tkr}: insufficient price data (heuristic).`, data_perspective: 'No usable bars returned.', catalysts: [], risks: ['No price history available'], strategy_notes: 'Wait for valid market data before sizing.', entry: null, exit: null, position_pct: null, confidence: 'low', source: 'heuristic', generated_at: new Date().toISOString() };
  const lastClose = close[close.length - 1];
  const ma20 = sma(close, 20).filter(v => v != null);
  const ma60 = sma(close, 60).filter(v => v != null);
  const ma20v = ma20.length ? ma20[ma20.length - 1] : lastClose;
  const ma60v = ma60.length ? ma60[ma60.length - 1] : lastClose;
  const r = rsi(close, 14);
  const m = macd(close);
  const atr = calcATR(bars, 14);
  const avgVol = vol.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, vol.length);
  const volRatio = avgVol ? (vol[vol.length - 1] / avgVol) : 1;
  const maDist = ((lastClose / ma20v) - 1) * 100;
  const trendUp = lastClose > ma20v && ma20v > ma60v;

  // transparent 0-100 score, weighted like DSA's multi-factor blend
  let score = 50;
  score += trendUp ? 18 : -18;
  if (r != null) score += (r - 50) * 0.25;            // RSI tilt
  if (m && m.hist > 0) score += 8; else if (m) score -= 8;
  if (maDist > 0) score += Math.min(10, maDist); else score -= Math.min(10, -maDist);
  if (volRatio > 1.5) score += 4;                      // volume confirmation
  const sc = scaleForScore(score);

  const stop = atr ? +(lastClose - 1.5 * atr).toFixed(2) : +(lastClose * 0.97).toFixed(2);
  const target = atr ? +(lastClose + 2 * atr).toFixed(2) : +(lastClose * 1.04).toFixed(2);
  const risk = lastClose - stop;
  const posPct = risk > 0 ? +(1 / (risk / lastClose) * 0.01).toFixed(1) : 5; // ~1% risk sizing

  const dataPerspective = [
    `Trend: ${trendUp ? 'bullish (price > MA20 > MA60)' : 'bearish / below trend'}`,
    `MA20 ${ma20v.toFixed(2)} (${maDist >= 0 ? '+' : ''}${maDist.toFixed(2)}% vs price)`,
    `RSI(14): ${r != null ? r.toFixed(1) : 'n/a'}`,
    `MACD: ${m ? (m.hist >= 0 ? 'bullish cross' : 'bearish cross') : 'n/a'} (DIF ${m ? m.dif : 'n/a'}, DEA ${m ? m.dea : 'n/a'})`,
    `ATR(14): ${atr != null ? atr.toFixed(2) : 'n/a'} · Vol ratio: ${volRatio.toFixed(2)}x`
  ].join(' · ');

  return {
    ticker: tkr,
    name: tkr,
    price: +lastClose.toFixed(2),
    change_pct: +(((lastClose / close[0]) - 1) * 100).toFixed(2),
    signal: sc.signal,
    action: sc.action,
    decision_type: sc.decision_type,
    score: sc.score,
    score_label: sc.label,
    one_liner: `${tkr} reads ${sc.label} on ${trendUp ? 'up' : 'down'}trend momentum (heuristic).`,
    data_perspective: dataPerspective,
    catalysts: [],
    risks: [
      r != null && r > 70 ? 'RSI overbought (>70) — mean-reversion risk' :
      r != null && r < 30 ? 'RSI oversold (<30) — relief-risk if no base' : 'No abnormal risk flag from technicals'
    ],
    strategy_notes: `Sniper entry ${stop.toFixed(2)} (1.5 ATR stop) · target ${target.toFixed(2)} · size ~${posPct}% of book for 1% risk.`,
    entry: +stop.toFixed(2),
    exit: +target.toFixed(2),
    position_pct: posPct,
    confidence: 'low',
    source: 'heuristic',
    generated_at: new Date().toISOString()
  };
}

/* ── strict AI payload normalization + validation ── */
const SIGNALS = new Set(['strong_buy', 'buy', 'watch', 'reduce', 'sell']);
function cleanText(v, fb = '') {
  if (v == null) return fb;
  if (Array.isArray(v)) return v.map(x => (typeof x === 'string' ? x : (x && x.summary) || JSON.stringify(x))).join(' · ');
  return String(v);
}
function asArray(v) {
  if (Array.isArray(v)) return v.map(x => (typeof x === 'string' ? x : (x && x.summary) || String(x)));
  if (typeof v === 'string' && v.trim()) return [v.trim()];
  return [];
}
function normalizeDailyPayload(tkr, raw, bars, source) {
  const lastBar = (bars && bars.length) ? bars[bars.length - 1] : null;
  const lastClose = (lastBar && Number.isFinite(lastBar.c)) ? lastBar.c : null;
  const sc = scaleForScore(raw.score != null ? raw.score : 50);
  const sig = SIGNALS.has(raw.signal) ? raw.signal : sc.signal;
  const action = (raw.action && ['buy', 'watch', 'reduce', 'sell'].includes(raw.action)) ? raw.action : (sig === 'strong_buy' || sig === 'buy' ? 'buy' : sig === 'watch' ? 'watch' : 'sell');

  const dash = raw.dashboard || raw;
  const core = dash.core_conclusion || raw.core_conclusion || {};
  const intel = dash.intelligence || raw.intelligence || {};
  const plan = dash.battle_plan || raw.battle_plan || {};

  const num = (v) => (Number.isFinite(v) ? +v : null);

  return {
    ticker: tkr,
    name: cleanText(raw.name || core.name, tkr),
    price: num(raw.price) != null ? num(raw.price) : (lastClose != null ? +lastClose.toFixed(2) : null),
    change_pct: num(raw.change_pct),
    signal: sig,
    action,
    decision_type: (['buy', 'hold', 'sell'].includes(raw.decision_type) ? raw.decision_type : sc.decision_type),
    score: sc.score,
    score_label: sc.label,
    one_liner: cleanText(core.one_liner || raw.one_liner, `${tkr}: ${sc.label} (${sc.score}).`),
    data_perspective: cleanText(core.data_perspective || dash.data_perspective || raw.data_perspective, ''),
    catalysts: asArray(intel.catalysts || raw.catalysts),
    risks: asArray(intel.risks || raw.risks),
    strategy_notes: cleanText(plan.notes || plan.strategy || raw.strategy_notes, cleanText(plan.summary, '')),
    entry: num(plan.entry ?? raw.entry),
    exit: num(plan.exit ?? raw.exit),
    position_pct: num(plan.position_pct ?? raw.position_pct),
    confidence: ['low', 'medium', 'high'].includes(raw.confidence) ? raw.confidence : 'medium',
    source,
    generated_at: new Date().toISOString()
  };
}

/* ── LLM prompt: DSA dashboard contract, enforces tracked schema ── */
function buildDailyPrompt(tkr, ctx) {
  return [
    { role: 'system', content:
`You are the SniperTrader Daily Analysis engine, trained on ZhuLinsen/daily_stock_analysis methodology.
Score the stock on a 0-100 scale using the CANONICAL DECISION SCALE:
 - 80-100 strong_buy (action=buy)  · 60-79 buy (action=buy)  · 40-59 watch (action=watch, hold)
 - 20-39 reduce (action=sell)      · 0-19 sell (action=sell)
Return ONLY valid minified JSON (no markdown, no prose) matching EXACTLY this contract:
{"ticker":"${tkr}","name":string,"price":number,"change_pct":number,"signal":"strong_buy|buy|watch|reduce|sell","action":"buy|watch|reduce|sell","decision_type":"buy|hold|sell","score":0-100,"one_liner":string,"data_perspective":string,"catalysts":[string],"risks":[string],"strategy_notes":string,"entry":number|null,"exit":number|null,"position_pct":number|null,"confidence":"low|medium|high"}
Use the technical context to justify data_perspective. Keep each string tight (<160 chars).` },
    { role: 'user', content: `Analyze ${tkr} for tomorrow's session.\n\nTECHNICAL CONTEXT:\n${ctx}` }
  ];
}

function buildDailyContext(bars) {
  const clean = (bars || []).filter(b => b && Number.isFinite(b.c));
  const close = clean.map(b => b.c);
  const vol = clean.map(b => (Number.isFinite(b.v) ? b.v : 0));
  if (!close.length) return `No usable price bars returned for context.`;
  const lastClose = close[close.length - 1];
  const ma20 = sma(close, 20).filter(v => v != null);
  const ma60 = sma(close, 60).filter(v => v != null);
  const r = rsi(close, 14);
  const m = macd(close);
  const atr = calcATR(bars, 14);
  const avgVol = vol.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, vol.length);
  const volRatio = avgVol ? (vol[vol.length - 1] / avgVol) : 1;
  const hi = Math.max(...last(bars, 20).map(b => b.h));
  const lo = Math.min(...last(bars, 20).map(b => b.l));
  const recent = last(bars, 5).map(b =>
    `${b.timestamp ? b.timestamp.slice(0, 10) : ''} O${b.o} H${b.h} L${b.l} C${b.c} V${b.v}`).join(' | ');
  return [
    `Last close: ${lastClose}`,
    `20-bar range: ${lo.toFixed(2)} – ${hi.toFixed(2)}`,
    `MA20: ${ma20.length ? ma20[ma20.length - 1].toFixed(2) : 'n/a'} · MA60: ${ma60.length ? ma60[ma60.length - 1].toFixed(2) : 'n/a'}`,
    `RSI(14): ${r != null ? r.toFixed(1) : 'n/a'}`,
    `MACD: ${m ? `DIF ${m.dif} DEA ${m.dea} HIST ${m.hist}` : 'n/a'}`,
    `ATR(14): ${atr != null ? atr.toFixed(2) : 'n/a'}`,
    `Volume ratio: ${volRatio.toFixed(2)}x`,
    `Recent bars: ${recent}`
  ].join('\n');
}

/* ── deterministic synthetic bars (offline / no-Alpaca demo mode) ──
 * Mirrors the Kronos backend's `synthetic` flag. Used when synthetic:true
 * is requested OR when no Alpaca server-side key is configured, so the
 * engine stays demoable and the UI never breaks on missing creds. */
function syntheticBars(tkr, n = 120) {
  // seed from ticker so each symbol is stable but distinct
  let seed = 0; for (const ch of tkr) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
  const rng = mulberry32(seed || 1);
  let price = 80 + rng() * 220;
  const drift = (rng() - 0.42) * 0.006;     // slight upward bias like real legs
  const bars = [];
  for (let i = 0; i < n; i++) {
    const o = price;
    const c = o * (1 + drift + (rng() - 0.5) * 0.022);
    const h = Math.max(o, c) * (1 + rng() * 0.012);
    const l = Math.min(o, c) * (1 - rng() * 0.012);
    const v = Math.round((1e6 + rng() * 4e6) * (0.7 + 0.6 * rng()));
    bars.push({ timestamp: new Date(Date.now() - (n - i) * 86400000).toISOString(), o: +o.toFixed(2), h: +h.toFixed(2), l: +l.toFixed(2), c: +c.toFixed(2), v });
    price = c;
  }
  return bars;
}

/* ── main daily analysis orchestrator ── */
async function runDailyAnalysis({ ticker, provider, lookback = 120, synthetic = false }) {
  const tkr = String(ticker || '').toUpperCase().trim();
  if (!tkr) throw new Error('ticker is required');
  const wantSynth = synthetic || !process.env.ALPACA_API_KEY;
  let bars, usedSynth = wantSynth;
  if (wantSynth) {
    bars = syntheticBars(tkr, Math.max(30, Math.min(300, lookback)));
  } else {
    try {
      bars = await alpacaBars({ symbol: tkr, timeframe: '1d', limit: Math.max(30, Math.min(300, lookback)) });
    } catch (e) { bars = []; }
    // If Alpaca returned nothing usable (feed glitch / missing fields), degrade to synthetic
    // so the analysis never shows a hollow "insufficient data" result.
    const usable = (bars || []).filter(b => b && Number.isFinite(b.c)).length;
    if (usable < 2) { bars = syntheticBars(tkr, Math.max(30, Math.min(300, lookback))); usedSynth = true; }
  }
  if (!bars || bars.length < 2) throw new Error(`no price data returned for ${tkr}`);

  const ctx = buildDailyContext(bars);
  const prov = provider && PROVIDERS[provider] ? provider
             : isConfigured('deepseek') ? 'deepseek'
             : isConfigured('kimi') ? 'kimi' : null;

  if (prov) {
    try {
      const r = await aiChat({ provider: prov, messages: buildDailyPrompt(tkr, ctx), options: { temperature: 0.3, maxTokens: 900 } });
      const text = (r.content || '').replace(/```json|```/g, '').trim();
      const raw = JSON.parse(text);
      const out = normalizeDailyPayload(tkr, raw, bars, 'ai:' + prov);
      out.context = ctx;
      out.synthetic = usedSynth;
      return out;
    } catch (e) {
      // model failure → transparent fallback (DSA data-degradation philosophy)
      const h = heuristicAnalysis(tkr, bars);
      h.source = 'heuristic(fallback:' + (e && e.message || 'ai-error') + ')';
      h.context = ctx; h.synthetic = usedSynth;
      return h;
    }
  }
  const h = heuristicAnalysis(tkr, bars);
  h.context = ctx; h.synthetic = usedSynth;
  return h;
}

/* ── REVIEW LOOP handler ── */
function buildReviewLoop(req, res) {
  let body = '';
  req.on('data', c => { body += c; if (body.length > 1e5) req.destroy(); });
  req.on('end', async () => {
    let payload;
    try { payload = JSON.parse(body || '{}'); }
    catch (e) { res.writeHead(400, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ error: 'invalid JSON' })); }
    const tickers = Array.isArray(payload.tickers) ? payload.tickers
                  : (payload.ticker ? [payload.ticker] : [])
                      .map(t => String(t).trim()).filter(Boolean).slice(0, 15);
    if (!tickers.length) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: 'provide tickers[] (max 15)' }));
    }
    const provider = String(payload.provider || '').toLowerCase();
    const results = [];
    for (const t of tickers) {
      try { results.push(await runDailyAnalysis({ ticker: t, provider })); }
      catch (e) { results.push({ ticker: t, error: String(e && e.message || e), signal: 'error', score: 0, source: 'error' }); }
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ analyzed_at: new Date().toISOString(), count: results.length, results }));
  });
}

/* ── TRADEREDGE PRE-FLIGHT PROTOCOL (POST /api/traderedge/preflight) ── */
// Validates + normalizes the Pre-Flight payload, recomputes authorization
// server-side (never trusts the client's authorizationStatus), and persists
// the record to the admin oversight store (demo store — in-memory on Vercel
// read-only FS, mirror file locally). Returns a strict, validated response.
const NEURAL_STATES = ['FLOW', 'FOCUSED', 'NEUTRAL', 'ANXIOUS', 'REVENGE'];
const GATE_KEYS = [
  'gate01_level', 'gate02_liquidity', 'gate03_doji', 'gate04_close',
  'gate05_entry', 'gate06_bos', 'gate07_slLocked', 'gate08_drawdownOk', 'gate09_maxLossesOk'
];

function clampInt(v, lo, hi, d) {
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) return d;
  return Math.min(hi, Math.max(lo, n));
}
function str(v, max) {
  return String(v == null ? '' : v).slice(0, max);
}

function buildPreflight(req, res) {
  let body = '';
  req.on('data', c => { body += c; if (body.length > 1e5) req.destroy(); });
  req.on('end', () => {
    let p;
    try { p = JSON.parse(body || '{}'); }
    catch (e) { res.writeHead(400, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ error: 'invalid JSON' })); }

    const ns = (p && typeof p.neuralState === 'object') ? p.neuralState : {};
    const gr = (p && typeof p.guardrails === 'object') ? p.guardrails : {};

    const state = NEURAL_STATES.includes(ns.state) ? ns.state : 'NEUTRAL';
    const neuralState = {
      state,
      stressLevel: clampInt(ns.stressLevel, 1, 10, 3),
      sleepQuality: clampInt(ns.sleepQuality, 1, 10, 7),
      focusClarity: clampInt(ns.focusClarity, 1, 10, 8),
      heartRateBpm: clampInt(ns.heartRateBpm, 45, 220, 72),
      journalEntry: str(ns.journalEntry, 2000)
    };

    // Boolean gates — coerce truthy/falsy; server recomputes the count.
    const guardrails = {};
    let passed = 0;
    for (const k of GATE_KEYS) { guardrails[k] = !!gr[k]; if (guardrails[k]) passed++; }
    guardrails.passedGatesCount = passed;

    // Authoritative authorization (server-side, mirrors the frontend rules).
    const revenge = state === 'REVENGE';
    const guardBreach = !guardrails.gate07_slLocked || !guardrails.gate08_drawdownOk || !guardrails.gate09_maxLossesOk;
    const anyFailed = GATE_KEYS.some(k => !guardrails[k]);
    const safeState = state === 'FLOW' || state === 'FOCUSED';
    const authorizationStatus = (revenge || guardBreach || anyFailed || !(safeState && passed === 9))
      ? 'LOCKED_OUT' : 'AUTHORIZED';

    const record = {
      timestamp: p.timestamp && !Number.isNaN(Date.parse(p.timestamp)) ? new Date(p.timestamp).toISOString() : new Date().toISOString(),
      userId: str(p.userId, 120) || 'local-trader',
      neuralState,
      guardrails,
      authorizationStatus
    };

    // Persist to admin oversight store (honest demo layer).
    let persisted = false;
    try {
      const store = require('./_lib/admin/store');
      const data = store.load();
      const list = Array.isArray(data.preflights) ? data.preflights : (data.preflights = []);
      list.push(record);
      if (list.length > 500) list.splice(0, list.length - 500);
      persisted = store.save(data);
    } catch (e) { persisted = false; }

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      ...record,
      server: 'traderedge-preflight',
      receivedAt: new Date().toISOString(),
      persisted,
      warning: persisted ? undefined : 'record accepted but not persisted (read-only environment) — in-memory only this session'
    }));
  });
}

module.exports = {
  MAX_CTX, MAX_BARS,
  mulberry32, gauss, genHistory, genPaths, computeBands, computeStats, runModel, runModelFull,
  computeSwarm, buildConfluence, detectICT, SWARM_ARCHETYPES,
  alpacaBars, alpacaGet, buildForecast, buildStocks, buildChat, buildPropAccount,
  ema, sma, rsi, macd, calcATR, scaleForScore, heuristicAnalysis, syntheticBars, buildDailyContext,
  normalizeDailyPayload, buildDailyPrompt, runDailyAnalysis, buildReviewLoop,
  buildPreflight, NEURAL_STATES, GATE_KEYS,
  aiChat, isConfigured, PROVIDERS
};
