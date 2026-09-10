'use strict';
// api/_lib/recon/orderflow.js
// ---------------------------------------------------------------------------
// Layer 2.5 — KEY-GATED stock order-flow leg (aggressor imbalance from the tape).
//
// HONEST LABEL: real order flow — who is aggressively buying vs selling — is the
// one input that actually answers "is this building before the crowd notices."
// It has NO key-less source for US equities, so it is KEY-GATED:
//   - Alpaca   (ALPACA_API_KEY + ALPACA_SECRET_KEY) → /v2/stocks/{sym}/trades
//   - Polygon  (POLYGON_API_KEY)                    → /v2/ticks/stocks/trades/{sym}/{date}
// When no key is present — or the key lacks a data subscription — the leg returns
// { available:false, reason } and contributes NOTHING. It is never fabricated and
// never estimated. The decision matrix (decision.js) renormalizes over AVAILABLE
// factors, so a stock's max score is transparently lower without it.
//
// Aggressor side is inferred with the tick rule (uptick = buyer-initiated,
// downtick = seller-initiated, flat = inherit the last direction). This is the
// standard, documented approximation for public tapes that don't carry exchange
// aggressor flags; it is a proxy, not a guarantee.
// ---------------------------------------------------------------------------

const https = require('https');

// Prior sessions of Polygon tape to fetch (REST tick history is a full-day dump,
// so the latest available date is the prior session — an honest baseline, not
// intraday-real-time).
const POLYGON_LOOKBACK_DAYS = 1;

function getJSON(url, headers, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers }, (res) => {
      if (res.statusCode !== 200) {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => reject(new Error('HTTP ' + res.statusCode + (body ? ' ' + body.slice(0, 120) : ''))));
        res.resume();
        return;
      }
      let d = '';
      res.setEncoding('utf8');
      res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
  });
}

// Aggressor classification via the tick rule over a sorted trade tape.
// trades: [{ p:number, s:number }] (price, size). Extra fields ignored.
// Returns null when there is not enough classified volume to be meaningful.
function tapeImbalance(trades) {
  if (!Array.isArray(trades) || trades.length < 2) return null;
  let buyVol = 0, sellVol = 0;
  let prevPrice = null, prevSide = null;
  for (const tr of trades) {
    const p = Number(tr.p), s = Number(tr.s) || 0;
    if (!(p > 0) || !(s > 0)) continue;
    let side;
    if (prevPrice == null) side = null;
    else if (p > prevPrice) side = 'buy';
    else if (p < prevPrice) side = 'sell';
    else side = prevSide; // flat print → inherit the last direction
    if (side === 'buy') buyVol += s;
    else if (side === 'sell') sellVol += s;
    prevPrice = p;
    prevSide = side;
  }
  const total = buyVol + sellVol;
  if (total <= 0) return null;
  return {
    buyVolume: Math.round(buyVol),
    sellVolume: Math.round(sellVol),
    buyPressure: +(buyVol / total).toFixed(4), // 0..1; >0.5 = buyer-aggressive
    delta: Math.round(buyVol - sellVol),       // signed share imbalance
    tradeCount: trades.length
  };
}

// Alpaca latest/real-time trades (feed configurable; default IEX for free plans).
async function alpacaTrades(symbol) {
  const key = process.env.ALPACA_API_KEY, sec = process.env.ALPACA_SECRET_KEY;
  if (!key || !sec) return { available: false, reason: 'no ALPACA_API_KEY/ALPACA_SECRET_KEY' };
  const feed = process.env.ALPACA_DATA_FEED || 'iex';
  const url = `https://data.alpaca.markets/v2/stocks/${encodeURIComponent(String(symbol).toUpperCase())}/trades?feed=${feed}&limit=1000`;
  const j = await getJSON(url, {
    'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': sec, 'Accept': 'application/json'
  });
  const trades = (j && j.trades) || [];
  if (!trades.length) return { available: false, reason: `no trades returned (${feed} feed may require a data subscription)` };
  const im = tapeImbalance(trades);
  if (!im) return { available: false, reason: 'insufficient classified trades' };
  return { available: true, source: `alpaca-${feed}`, ...im };
}

// Polygon prior-session tape (REST tick history; not intraday-real-time).
async function polygonTrades(symbol) {
  const key = process.env.POLYGON_API_KEY;
  if (!key) return { available: false, reason: 'no POLYGON_API_KEY' };
  const d = new Date();
  d.setDate(d.getDate() - POLYGON_LOOKBACK_DAYS);
  const date = d.toISOString().slice(0, 10);
  const url = `https://api.polygon.io/v2/ticks/stocks/trades/${encodeURIComponent(String(symbol).toUpperCase())}/${date}?limit=1000&apiKey=${encodeURIComponent(key)}`;
  const j = await getJSON(url, { Accept: 'application/json' });
  const results = (j && j.results) || [];
  if (!results.length) return { available: false, reason: 'no polygon ticks for the prior session' };
  const im = tapeImbalance(results.map((r) => ({ p: r.p, s: r.s })));
  if (!im) return { available: false, reason: 'insufficient classified polygon trades' };
  return { available: true, source: 'polygon-prior-session', ...im };
}

// Dispatcher: first available provider wins; otherwise honest unavailable + reasons.
async function stockOrderFlow(symbol) {
  const reasons = [];
  for (const fn of [alpacaTrades, polygonTrades]) {
    try {
      const r = await fn(symbol);
      if (r.available) return r;
      if (r.reason) reasons.push(r.reason);
    } catch (e) {
      reasons.push(String((e && e.message) || e));
    }
  }
  return { available: false, reason: reasons.length ? reasons.join('; ') : 'no order-flow provider configured' };
}

// What stays gated even when a key exists (honest disclosure for the payload).
const ORDERFLOW_GATED = [
  'Options / dark-pool order flow (no key-less or keyed source wired)',
  'Odd-lot & hidden-liquidity breakdown (not in the standard trade tape)',
  'Options gamma / liquidation levels (options chain key-gated, not wired)'
];

module.exports = { stockOrderFlow, tapeImbalance, ORDERFLOW_GATED };
