'use strict';
// api/_lib/recon/kronos_cone.js
// ---------------------------------------------------------------------------
// Kronos "Empirical Probability Cone" + ICT structure, reused from _core.js and
// folded into the recon scout as the deterministic technical-confirmation layer.
//
// HONEST LABEL: this is the SAME transparent Monte-Carlo simulation that powers
// the Kronos dashboard. It is a *directional projection* derived from the last
// ~20 daily returns — NOT a live order-flow / tape signal, and NOT a trained
// model. It only ever contributes a bounded share of the technical sub-score,
// and it is surfaced in the payload for audit.
// ---------------------------------------------------------------------------

const core = require('../../_core');

function avg(a) { return a.reduce((s, x) => s + x, 0) / a.length; }
function stddev(a) {
  const m = avg(a);
  return Math.sqrt(avg(a.map(x => (x - m) * (x - m))));
}
function clamp01(x) { return Math.max(0, Math.min(1, x)); }

// rows: daily bars [{o,h,l,c,v}, ...] (caller has already filtered null fields).
// Returns a 0..1 directional score plus an auditable breakdown, including the
// forward cone's P25/P50/P75 band returns and a "near lower bound" flag (current
// price at the low end of the projected path fan → asymmetric upside).
function coneSignal(rows, opts = {}) {
  const horizon = opts.horizon || 20;
  const paths = opts.paths || 32;
  const seed = opts.seed || 0x9E3779B1;
  const none = {
    score: 0.5, upPct: 50, p50ret: 0, p25ret: 0, p75ret: 0, nearLowerBound: false,
    drift: 0, vol: 0,
    ict: { obs: 0, fvgs: 0, liq: 0 }, rsi: null, priceVsMa20: 0, volRatio: 1,
    parabolic: false, distribution: false, reason: 'insufficient bars'
  };
  if (!Array.isArray(rows) || rows.length < 21) return none;

  const closes = rows.map(r => r.c);
  const lastClose = closes[closes.length - 1];

  // Empirical drift + vol from the trailing 20 daily returns (data-derived, honest).
  const rets = [];
  for (let i = closes.length - 21; i < closes.length - 1; i++) {
    rets.push(closes[i + 1] / closes[i] - 1);
  }
  const drift = avg(rets);
  const vol = Math.max(0.003, Math.min(0.06, stddev(rets)));

  const rng = core.mulberry32(seed >>> 0);
  const simPaths = core.genPaths(lastClose, rng, { paths, horizon, drift, temp: 1.0, vol }, vol);
  const bands = core.computeBands(simPaths);
  const stats = core.computeStats(lastClose, simPaths, bands);
  const bandEnd = bands.p50.length - 1;
  const p25ret = bandEnd >= 0 ? (bands.p25[bandEnd] / lastClose - 1) * 100 : 0;
  const p75ret = bandEnd >= 0 ? (bands.p75[bandEnd] / lastClose - 1) * 100 : 0;
  const nearLowerBound = stats.up >= 60; // ≥60% of paths end higher → price at the fan's low end

  const ict = core.detectICT(rows);
  const rsi = core.rsi(closes, 14);
  const ma20 = avg(closes.slice(-20));
  const priceVsMa20 = (lastClose / ma20 - 1) * 100;

  // Trailing-volume fade: last 3 bars vs the prior 17 (distribution = fading volume).
  const vols = rows.map(r => r.v).filter(v => Number.isFinite(v) && v > 0);
  const recentVol = vols.length >= 6 ? avg(vols.slice(-3)) : 0;
  const priorVol = vols.length >= 20 ? avg(vols.slice(-20, -3)) : 0;
  const volRatio = priorVol > 0 ? recentVol / priorVol : 1;

  // Dump-risk definition: overheated (RSI>72) + extended (>15% over MA20) + volume fading.
  const parabolic = rsi != null && rsi > 72 && priceVsMa20 > 15;
  const distribution = parabolic && volRatio < 1.0;

  // Directional score: neutral 0.5 → bullish ~0.9 → bearish ~0.2.
  // up% = share of simulated paths that end above the last close; ret = P50 % return.
  let score = clamp01(0.5 + ((stats.up - 50) / 50) * 0.35 + (stats.ret / 10) * 0.15);
  if (parabolic) score *= 0.5; // already-extended = late entry, not a fresh pre-run setup

  return {
    score: +score.toFixed(3),
    upPct: +stats.up.toFixed(1),
    p50ret: +stats.ret.toFixed(2),
    p25ret: +p25ret.toFixed(2),
    p75ret: +p75ret.toFixed(2),
    nearLowerBound,
    drift: +drift.toFixed(4),
    vol: +vol.toFixed(4),
    ict: { obs: ict.obs.length, fvgs: ict.fvgs.length, liq: ict.liq.length },
    rsi: rsi != null ? +rsi.toFixed(1) : null,
    priceVsMa20: +priceVsMa20.toFixed(1),
    volRatio: +volRatio.toFixed(2),
    parabolic,
    distribution,
    reason: null
  };
}

module.exports = { coneSignal };
