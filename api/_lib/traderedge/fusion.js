'use strict';
/**
 * api/_lib/traderedge/fusion.js — Layer 4: confidence-weighted fusion gate.
 *
 * Decides whether the evidence is strong enough for Layer 3 to act, so the
 * graph never fires on noise. A weak single signal → no actuation; correlated
 * multi-signal evidence in a known-bad subgraph → actuate.
 *
 * Honesty rules:
 *  - Self-reported signals get a 0.7 weight; device-sourced get 1.0.
 *  - A MISSING sensor (sensorMask bit false) contributes weight 0 — absence
 *    of a sensor must never manufacture a red flag (partial fingerprint).
 *  - Evidence is a capped weighted sum; actuation threshold = 0.5.
 */

// signalId → { weight, needs }  (needs: which sensor gates the signal)
const SIGNALS = {
  revenge:        { weight: 1.00, needs: null },           // state === REVENGE
  anxious:        { weight: 0.50, needs: null },           // state === ANXIOUS
  stressHigh:     { weight: 0.40, needs: 'stress' },       // stress >= 7
  sleepLow:       { weight: 0.40, needs: 'sleep' },        // sleep <= 5
  losingStreak:   { weight: 0.50, needs: null },           // losingStreak >= 3
  sizeUp:         { weight: 0.60, needs: null },           // size increase detected
  planDeviation:  { weight: 0.50, needs: null },           // deviated from plan
  highVol:        { weight: 0.30, needs: null }            // regime amplifier
};

// sensorMask: { hrv, hr, sleep, focus, stress, eyetrack } → boolean (present?)
// sourceMask: same keys → 'device' | 'self-report' | null
function sensorWeight(signalId, needs, sensorMask, sourceMask) {
  if (!needs) return 1.0;                 // behavioural signal, no sensor needed
  if (!sensorMask || !sensorMask[needs]) return 0.0;  // sensor missing → no evidence
  const src = (sourceMask && sourceMask[needs]) || 'self-report';
  return src === 'device' ? 1.0 : 0.7;    // self-report discounted
}

function score(bundle) {
  const b = bundle || {};
  const sensorMask = b.sensorMask || { stress: true, sleep: true, hr: true }; // defaults = self-report sliders present
  const sourceMask = b.sourceMask || {};

  const state = String(b.state || 'NEUTRAL').toUpperCase();
  const flags = {
    revenge:       state === 'REVENGE',
    anxious:       state === 'ANXIOUS',
    stressHigh:    Number(b.stress) >= 7,
    sleepLow:      Number(b.sleep) <= 5,
    losingStreak:  Number(b.losingStreak) >= 3,
    sizeUp:        !!b.sizeUp,
    planDeviation: !!b.planDeviation,
    highVol:       /high|volatile/i.test(String(b.regime || ''))
  };

  let evidence = 0;
  const hits = [];
  for (const [id, spec] of Object.entries(SIGNALS)) {
    if (!flags[id]) continue;
    const w = spec.weight * sensorWeight(id, spec.needs, sensorMask, sourceMask);
    if (w > 0) { evidence += w; hits.push({ signal: id, weight: w }); }
  }
  evidence = Math.min(1.0, evidence);

  return {
    actuate: evidence >= 0.5,
    evidence,
    hits,
    threshold: 0.5,
    sensorMask,
    sourceMask
  };
}

module.exports = { score, SIGNALS };
