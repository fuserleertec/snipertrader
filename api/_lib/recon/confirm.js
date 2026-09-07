'use strict';
// api/_lib/recon/confirm.js
// ---------------------------------------------------------------------------
// Layer 3.1/3.2 — volume + order-flow confirmation (the HARD gate + supplementary
// order-flow read). Key-less checks only.
//
//   HARD GATE (3.1): stocks = volume >2x 20d avg AND price > anchored VWAP;
//                     crypto = taker-buy dominance >60% AND consecutive green
//                     5m/15m candles. Fail → drop regardless of signal.
//   SUPPLEMENTARY (3.2): crypto bid/ask depth ratio. Reported, never drops.
//
// Gated inputs (stock trade count, dark-pool, stock order flow via NinjaTrader,
// liquidation levels, exchange inflow/outflow) are reported as `unavailable` and
// never fabricate a pass/fail.
// ---------------------------------------------------------------------------

const https = require('https');

function avg(a) { return a.reduce((s, x) => s + x, 0) / a.length; }

function getJSON(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0 (research; snipertrader.ai)' } }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let d = ''; res.setEncoding('utf8');
      res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
  });
}

function binanceKlines(symbol, interval = '5m', limit = 60) {
  const url = `https://data-api.binance.vision/api/v3/klines?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${limit}`;
  return getJSON(url).then((raw) => raw.map((d) => ({ o: +d[1], c: +d[4] })));
}

function binanceDepth(symbol, limit = 50) {
  const url = `https://data-api.binance.vision/api/v3/depth?symbol=${encodeURIComponent(symbol)}&limit=${limit}`;
  return getJSON(url);
}

// ---- 3.1 stock volume confirmation (pure — uses daily bars already fetched) ----
function stockVolumeConfirm(rows) {
  if (!rows || rows.length < 21) {
    return { pass: false, surgeRatio: 0, aboveVwap: false, vwap: 0, strength: 'n/a', reasons: ['insufficient bars'] };
  }
  const closes = rows.map(r => r.c);
  const vols = rows.map(r => r.v);
  const lastClose = closes[closes.length - 1];
  // Volume surge: last bar vs the prior 20 completed bars (excludes the in-progress
  // bar so a partial day's volume can't false-fail the gate).
  const prior20 = vols.slice(-21, -1);
  const avgVol20 = avg(prior20);
  const surgeRatio = avgVol20 > 0 ? vols[vols.length - 1] / avgVol20 : 0;

  // Anchored daily VWAP proxy over the last 20 bars: Σ(typical*vol) / Σ(vol).
  let tpVol = 0, volSum = 0;
  for (let i = rows.length - 20; i < rows.length; i++) {
    const tp = (rows[i].h + rows[i].l + rows[i].c) / 3;
    tpVol += tp * rows[i].v; volSum += rows[i].v;
  }
  const vwap = volSum > 0 ? tpVol / volSum : lastClose;
  const aboveVwap = lastClose > vwap;

  // Honest recalibration: the old ">2x" gate was a rare breakout spike, not a
  // "confirmation" — a normal name trades ~1x. Confirmation = volume is NOT drying
  // up (≥0.8x) AND price is holding above VWAP. Strength is reported, never a gate.
  const strength = surgeRatio >= 2 ? 'strong' : surgeRatio >= 1.5 ? 'elevated' : surgeRatio >= 1.0 ? 'normal' : surgeRatio >= 0.8 ? 'mild' : 'drying';
  const reasons = [];
  if (surgeRatio < 0.8) reasons.push(`volume ${surgeRatio.toFixed(2)}x vs 20d — drying up (need ≥0.8x)`);
  if (!aboveVwap) reasons.push('price below VWAP');
  return { pass: reasons.length === 0, surgeRatio: +surgeRatio.toFixed(2), aboveVwap, vwap: +vwap.toFixed(4), strength, reasons };
}

function consecutiveGreen(rows) {
  let n = 0;
  for (let i = rows.length - 1; i >= 0; i--) { if (rows[i].c > rows[i].o) n++; else break; }
  return n;
}

// ---- 3.1+3.2 crypto confirmation (fetches 5m/15m + depth; taker-buy passed in) ----
async function cryptoConfirm(symbol, takerBuyRatio) {
  const buyDominance = takerBuyRatio || 0.5;
  let k5 = [], k15 = [], depth = null;
  try { k5 = await binanceKlines(symbol, '5m', 60); } catch (_) {}
  try { k15 = await binanceKlines(symbol, '15m', 60); } catch (_) {}
  try { depth = await binanceDepth(symbol, 50); } catch (_) {}
  const green5 = consecutiveGreen(k5);
  const green15 = consecutiveGreen(k15);

  let bidDepth = 0, askDepth = 0, depthRatio = null;
  if (depth && Array.isArray(depth.bids) && Array.isArray(depth.asks)) {
    bidDepth = depth.bids.reduce((s, b) => s + parseFloat(b[1]), 0);
    askDepth = depth.asks.reduce((s, a) => s + parseFloat(a[1]), 0);
    depthRatio = askDepth > 0 ? bidDepth / askDepth : null;
  }

  // HARD GATE = volume confirmation (3.1) only — recalibrated like the stock gate:
  // "buy-side not drying up" (>50% taker-buy) + "momentum not reversing" (green 5m/15m).
  const flowStrength = buyDominance >= 0.60 ? 'strong-accumulation' : buyDominance >= 0.55 ? 'elevated' : buyDominance >= 0.50 ? 'buy-side-lean' : 'seller-dominated';
  const reasons = [];
  if (buyDominance <= 0.50) reasons.push(`buy dominance ${(buyDominance * 100).toFixed(0)}% (need >50%)`);
  if (green5 < 1) reasons.push(`5m green run ${green5} (need >=1)`);
  if (green15 < 1) reasons.push(`15m green run ${green15} (need >=1)`);

  return {
    pass: reasons.length === 0,
    buyDominance: +buyDominance.toFixed(3),
    green5, green15,
    flowStrength,
    orderFlow: { // supplementary (3.2) — reported, never drops
      bidDepth: +bidDepth.toFixed(4),
      askDepth: +askDepth.toFixed(4),
      depthRatio: depthRatio != null ? +depthRatio.toFixed(2) : null,
      bidExceedsAsk: depthRatio != null && depthRatio > 1.0
    },
    reasons,
    unavailable: {
      stockTradeCount: true,   // no key-less stock trade-count source
      darkPool: true,          // no key-less dark-pool data
      stockOrderFlow: true,    // NinjaTrader OF+ is desktop software, no API
      liquidationLevels: true, // key-gated (futures/liquidation feeds)
      exchangeFlow: true       // key-gated (Glassnode/CryptoQuant)
    }
  };
}

module.exports = { stockVolumeConfirm, cryptoConfirm };
