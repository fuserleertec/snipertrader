'use strict';
// api/_lib/recon/crypto_scan.js
// ---------------------------------------------------------------------------
// Layer 2 crypto leg — key-less screener over Binance daily klines.
//
// Binance's public market-data endpoint returns OHLCV + numberOfTrades +
// taker-buy base/quote volume per bar with NO API key, which means crypto
// actually has MORE order-flow-adjacent signal than stocks: trade-count surge
// and taker-buy ratio are real aggressive-flow proxies. Whale on-chain
// accumulation is the one crypto filter with NO key-less source (Whale Alert /
// Nansen / Glassnode are all key-gated) and is intentionally excluded.
// ---------------------------------------------------------------------------

const https = require('https');
const { coneSignal } = require('./kronos_cone');
const { cryptoDumpSignals } = require('./dump');

// Fixed, liquid USDT universe (deterministic + bounded; no extra discovery call).
const UNIVERSE = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT',
  'AVAXUSDT', 'LINKUSDT', 'DOTUSDT', 'LTCUSDT', 'UNIUSDT', 'ATOMUSDT', 'FILUSDT',
  'NEARUSDT', 'APTUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT', 'TIAUSDT',
  'SEIUSDT', 'PEPEUSDT', 'SHIBUSDT'
];

function avg(a) { return a.reduce((s, x) => s + x, 0) / a.length; }
function stddev(a) {
  const m = avg(a);
  return Math.sqrt(avg(a.map(x => (x - m) * (x - m))));
}

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

// Binance kline bar: [openTime, o, h, l, c, v, closeTime, quoteVol, numTrades,
//                     takerBuyBase, takerBuyQuote, ignore]
function binanceKlines(symbol, interval = '1d', limit = 60) {
  const url = `https://data-api.binance.vision/api/v3/klines?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${limit}`;
  return getJSON(url).then((raw) => raw.map((d) => ({
    o: +d[1], h: +d[2], l: +d[3], c: +d[4], v: +d[5],
    numTrades: +d[8], takerBuyBase: +d[9]
  })));
}

function bollinger(closes, period = 20, mult = 2) {
  if (!closes || closes.length < period) return null;
  const slice = closes.slice(-period);
  const mid = avg(slice);
  const sd = stddev(slice);
  return { mid, upper: mid + mult * sd, lower: mid - mult * sd, bandwidth: mid > 0 ? (2 * mult * sd) / mid : 0 };
}

// Score one symbol from its daily bars. Honest, transparent 0-100.
function analyze(symbol, rows) {
  if (!rows || rows.length < 40) return { symbol, error: 'insufficient bars' };
  const closes = rows.map(r => r.c);
  const vols = rows.map(r => r.v);
  const trades = rows.map(r => r.numTrades || 0);
  const lastClose = closes[closes.length - 1];

  // 1) Quiet accumulation: volume building while price is flat.
  const vol5 = avg(vols.slice(-5));
  const volPrior = avg(vols.slice(-20, -5));
  const volumeRatio = volPrior > 0 ? vol5 / volPrior : 1;
  const sma20 = avg(closes.slice(-20));
  const priceCompression = Math.abs(lastClose - sma20) / sma20;
  const volumeBuilding = volumeRatio > 1.25 && priceCompression < 0.03;

  // 2) Bollinger squeeze (coil): bandwidth tightening vs 20 bars ago.
  const bbNow = bollinger(closes);
  const bbPrev = bollinger(closes.slice(0, -20));
  const squeeze = !!(bbNow && bbPrev && bbNow.bandwidth < bbPrev.bandwidth * 0.8);
  const bandwidth = bbNow ? bbNow.bandwidth : null;

  // 3) RSI (oversold-bounce setup <40).
  const cone = coneSignal(rows);
  const rsi = cone.rsi;

  // 4) Trade-count surge (>2x = more transactions).
  const tc5 = avg(trades.slice(-5));
  const tcPrior = avg(trades.slice(-20, -5));
  const tradeSurge = tcPrior > 0 ? tc5 / tcPrior : 1;

  // 5) Taker-buy ratio: share of volume from aggressive buyers (last 5 bars).
  const tbv = rows.slice(-5).reduce((a, r) => a + (r.takerBuyBase || 0), 0);
  const vv = vols.slice(-5).reduce((a, b) => a + b, 0);
  const takerBuyRatio = vv > 0 ? tbv / vv : 0.5;

  // Composite (each filter contributes a bounded, honest delta).
  let score = 50;
  if (volumeBuilding) score += 15;
  if (squeeze) score += 10;
  if (rsi != null && rsi < 40) score += 15; else if (rsi != null && rsi > 70) score -= 15;
  if (tradeSurge > 2) score += 10;
  if (takerBuyRatio > 0.55) score += 10; else if (takerBuyRatio < 0.45) score -= 10;
  score += cone.upPct > 60 ? 10 : (cone.upPct < 40 ? -10 : 0);
  score = Math.max(0, Math.min(100, Math.round(score)));

  // Setup label (dominant signal).
  let setup = 'neutral';
  if (rsi != null && rsi < 40 && volumeBuilding) setup = 'oversold-accumulation';
  else if (squeeze) setup = 'breakout-coil';
  else if (volumeBuilding && takerBuyRatio > 0.55) setup = 'quiet-accumulation';
  else if (cone.distribution) setup = 'distribution-risk';
  else if (score >= 70) setup = 'bullish';

  return {
    symbol,
    price: +lastClose.toFixed(6),
    rsi: rsi != null ? +rsi.toFixed(1) : null,
    score,
    setup,
    volumeRatio: +volumeRatio.toFixed(2),
    priceCompression: +priceCompression.toFixed(4),
    volumeBuilding,
    bollingerSqueeze: squeeze,
    bandwidth: bandwidth != null ? +bandwidth.toFixed(4) : null,
    tradeSurge: +tradeSurge.toFixed(2),
    takerBuyRatio: +takerBuyRatio.toFixed(3),
    cone: {
      upPct: cone.upPct, p50ret: cone.p50ret, p25ret: cone.p25ret, p75ret: cone.p75ret, vol: cone.vol,
      nearLowerBound: cone.nearLowerBound, ict: cone.ict, distribution: cone.distribution
    },
    dumpSignals: cryptoDumpSignals({ rows, cone }),
    whaleAccumulation: null, // key-gated (Whale Alert/Nansen) — never fabricated
    note: null
  };
}

// Fetch the universe with bounded concurrency and return candidates sorted by score.
async function scanCrypto(limit = 24, concurrency = 5) {
  const out = [];
  const queue = UNIVERSE.slice(0, limit);
  const workers = Array.from({ length: Math.min(concurrency, queue.length) }, async () => {
    while (queue.length) {
      const sym = queue.shift();
      try {
        const rows = await binanceKlines(sym);
        const a = analyze(sym, rows);
        if (!a.error) out.push(a);
      } catch (_) { /* skip a failed pair; the grid stays honest */ }
    }
  });
  await Promise.all(workers);
  out.sort((a, b) => b.score - a.score);
  return out;
}

module.exports = { scanCrypto, analyze, UNIVERSE };
