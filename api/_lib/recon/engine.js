// api/recon/engine.js
// Conviction Engine — pure, deterministic scoring core (no I/O).
// Recalibrated per directive: 0-100 scale, weights
//   Insider/Inside Buying 0.30 · Technical Trend/Order Flow 0.30 ·
//   Volume Surge 0.20 · Fundamental Catalyst 0.20.
// Trade levels anchor to dynamic technicals (ATR + swing highs/lows), with a
// hard inversion guard so Target can never sit below Entry for a long, nor Stop
// above Entry.

const W = { insider: 0.30, technical: 0.30, volume: 0.20, catalyst: 0.20 };

// Map a sub-signal strength (0..1) into a 0..100 sub-score.
// Each input factor is normalised to 0..1 by the fetcher, then weighted.
function subScore(x) { return clamp01(x) * 100; }

function clamp01(x) { return Math.max(0, Math.min(1, x)); }

// Composite conviction on a 0-100 scale.
function convictionScore(inputs) {
  // inputs: { insider:0..1, technical:0..1, volume:0..1, catalyst:0..1 }
  const ins = subScore(inputs.insider ?? 0);
  const tech = subScore(inputs.technical ?? 0);
  const vol = subScore(inputs.volume ?? 0);
  const cat = subScore(inputs.catalyst ?? 0);
  const total = ins * W.insider + tech * W.technical + vol * W.volume + cat * W.catalyst;
  return Math.round(clampRange(total, 0, 100) * 100) / 100;
}

// Tier mapping on the 0-100 scale.
function tierOf(score) {
  if (score >= 88) return 'ultra';
  if (score >= 78) return 'high';
  if (score >= 65) return 'moderate';
  return 'rejected';
}

const TIER_META = {
  ultra:    { label: 'Ultra-High', allocationPct: 12.0, riskPct: 2.0, rr: 2.5, accent: 'var(--emerald)' },
  high:     { label: 'High',       allocationPct: 8.0,  riskPct: 1.25, rr: 2.0, accent: 'var(--cyan)' },
  moderate: { label: 'Watchlist',  allocationPct: 0.0,  riskPct: 0.0,  rr: 0.0, accent: 'var(--gold)' },
  rejected: { label: 'Rejected',   allocationPct: 0.0,  riskPct: 0.0,  rr: 0.0, accent: 'var(--red)' }
};

// ATR-anchored trade levels with inversion guard.
//   stop  = entry - max(stopMult*ATR, minStopDist)   (never above entry)
//   target= entry + max(targetMult*ATR, stopDist*rr)  (never below entry; never below stop)
// Returns dollar levels + the realized reward:risk.
function computeLevels({ entry, atr, swingLow, swingHigh, rr = 2.0, stopMult = 1.0, targetMult = 1.0 }) {
  if (!(rr > 0)) rr = 2.0; // defensive: never compute with 0 R:R
  const e = Number(entry), a = Number(atr) > 0 ? Number(atr) : e * 0.03;
  let stop = e - Math.max(stopMult * a, e * 0.01);          // >=1% below entry hard floor
  if (swingLow && Number(swingLow) > 0) {
    // prefer structure: stop just under the swing low, but never above entry
    stop = Math.min(stop, Number(swingLow) - a * 0.25);
  }
  stop = Math.min(stop, e - e * 0.005);                      // guard: stop strictly below entry
  const risk = Math.max(e - stop, e * 0.001);

  let target = e + Math.max(targetMult * a, risk * rr);       // target at >= rr * risk
  if (swingHigh && Number(swingHigh) > 0) {
    // nudge toward a structural target if it yields a better R multiple
    const structT = Number(swingHigh) + a * 0.5;
    if (structT > target) target = structT;
  }
  target = Math.max(target, e + risk * rr, e * 1.005);       // guard: target strictly above entry & >= rr*risk

  const realizedRR = risk > 0 ? (target - e) / risk : 0;
  return {
    entry: round2(e),
    stop: round2(stop),
    target: round2(target),
    atr: round2(a),
    risk: round2(risk),
    rewardRisk: round2(realizedRR)
  };
}

function round2(x) { return Math.round(Number(x) * 100) / 100; }
function clampRange(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }

module.exports = {
  W, convictionScore, tierOf, TIER_META, computeLevels, subScore, clamp01, round2
};
