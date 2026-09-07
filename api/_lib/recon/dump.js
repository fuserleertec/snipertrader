'use strict';
// api/_lib/recon/dump.js
// ---------------------------------------------------------------------------
// Layer 4 — dump detection & exit signals. ALERTS ONLY — this never executes
// orders. Key-less signals composed from data already fetched. Gated sources
// (dark pool, short interest, whale distribution, holder count, liquidity-pool
// injections, X social euphoria) are reported as unavailable and never fabricate
// an alert.
// ---------------------------------------------------------------------------

function avg(a) { return a.reduce((s, x) => s + x, 0) / a.length; }

// Parabolic single-session spike: >50% day-over-day gain.
function parabolicGain(rows) {
  if (!rows || rows.length < 2) return null;
  const c = rows.map(r => r.c);
  const prev = c[c.length - 2], last = c[c.length - 1];
  if (!(prev > 0)) return null;
  const g = (last / prev - 1) * 100;
  return g > 50 ? +g.toFixed(1) : null;
}

// 70% rule: massive volume spike (>3x 20d avg) with minimal price move (<1.5%)
// = potential insider positioning before a pump/dump. (The "within one hour"
// refinement is expressible via Binance 1h klines but is not wired yet.)
function volumePriceDivergence(rows) {
  if (!rows || rows.length < 21) return null;
  const vols = rows.map(r => r.v);
  const closes = rows.map(r => r.c);
  const avg20 = avg(vols.slice(-20));
  const lastVol = vols[vols.length - 1];
  const spike = avg20 > 0 ? lastVol / avg20 : 0;
  const move = Math.abs(closes[closes.length - 1] / closes[closes.length - 2] - 1) * 100;
  if (spike > 3 && move < 1.5) return { spike: +spike.toFixed(2), move: +move.toFixed(2) };
  return null;
}

// Stocks/OTC dump signals.
function stockDumpSignals({ rows, cone, insider }) {
  const alerts = [];
  const pg = parabolicGain(rows);
  if (pg != null) alerts.push({ level: 'SELL', code: 'parabolic', msg: `+${pg}% single-session spike` });
  const vd = volumePriceDivergence(rows);
  if (vd) alerts.push({ level: 'SELL', code: 'volume-price-divergence', msg: `volume ${vd.spike}x with ${vd.move}% price move (70% rule — insider positioning)` });
  if (cone && cone.distribution) alerts.push({ level: 'REDUCE', code: 'volume-drying', msg: 'price up + volume fading (distribution)' });
  if (insider && insider.sells > insider.buys && insider.sells > 0) alerts.push({ level: 'EXIT', code: 'insider-selling', msg: `Form 4 sells ${insider.sells} > buys ${insider.buys}` });
  return alerts;
}

// Crypto dump signals.
function cryptoDumpSignals({ rows, cone }) {
  const alerts = [];
  const pg = parabolicGain(rows);
  if (pg != null) alerts.push({ level: 'SELL', code: 'parabolic', msg: `+${pg}% single-session spike` });
  const vd = volumePriceDivergence(rows);
  if (vd) alerts.push({ level: 'SELL', code: 'volume-price-divergence', msg: `volume ${vd.spike}x with ${vd.move}% price move (70% rule — insider positioning)` });
  if (cone && cone.rsi != null && cone.rsi > 85) alerts.push({ level: 'TAKE_PROFIT', code: 'rsi-overbought', msg: `RSI ${cone.rsi} > 85 (extreme overbought)` });
  if (cone && cone.distribution) alerts.push({ level: 'REDUCE', code: 'volume-drying', msg: 'price up + volume fading' });
  return alerts;
}

const GATED = [
  'Dark-pool selling (stocks) — no key-less source',
  'Short-interest collapse (stocks) — key-gated (FINRA, biweekly)',
  'Whale on-chain distribution (crypto) — key-gated (Arkham/Nansen/Whale Alert)',
  'Holder-count stagnation (crypto) — key-gated (on-chain)',
  'Liquidity-pool injections (crypto) — key-gated (DeFi on-chain)',
  'Social euphoria / "moon" tweet frequency — key-gated (X API)'
];

module.exports = { stockDumpSignals, cryptoDumpSignals, parabolicGain, volumePriceDivergence, GATED };
