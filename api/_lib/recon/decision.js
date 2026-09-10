'use strict';
// api/_lib/recon/decision.js
// ---------------------------------------------------------------------------
// Layer 5 — trade decision matrix (5.1), position sizing (5.2), exit rules (5.3).
// SIMULATION ONLY: emits decision + sizing + exits for audit. NEVER places orders.
//
// Honest handling of gated factors: whale (10%) is key-gated; stock order-flow
// (20%) is key-gated but NOW fills from the Alpaca/Polygon trade tape when a key
// is present (orderflow.js). The weighted score is renormalized over AVAILABLE
// factors and both the raw score (gated=0) and `missingFactors` are reported —
// so a BUY can only fire on the signals we actually have, never padded ones.
// ---------------------------------------------------------------------------

const SIM_EQUITY = 25000; // simulated portfolio equity (no live account exists)

function round2(x) { return Math.round(Number(x) * 100) / 100; }
function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }

// 5.1 — weighted decision matrix.
// c = { score, confirmation, catalyst, takerBuyRatio, dumpSignals }
function decide(c, assetType) {
  const conv = clamp(c.score || 0, 0, 100);
  const volumePass = !!(c.confirmation && c.confirmation.pass);
  const catalyst = c.catalyst && Number.isFinite(c.catalyst.score) ? clamp(c.catalyst.score, 0, 100) : 0;
  const dumpTriggered = !!(c.dumpSignals && c.dumpSignals.length);

  // Order flow: crypto uses taker-buy as a proxy; stocks use the KEY-GATED
  // Alpaca/Polygon trade-tape aggressor imbalance (orderflow.js) when a key is
  // present — otherwise it stays null and is renormalized out + reported.
  let orderFlow = null;
  if (assetType === 'crypto' && Number.isFinite(c.takerBuyRatio)) {
    orderFlow = clamp((c.takerBuyRatio - 0.5) * 2 * 100, 0, 100); // 0.5 → 0, 1.0 → 100
  } else if (c.orderFlow && c.orderFlow.available && Number.isFinite(c.orderFlow.buyPressure)) {
    orderFlow = clamp(c.orderFlow.buyPressure * 100, 0, 100); // 0.5 → 50, 1.0 → 100
  }
  const whale = null; // key-gated

  const factors = {
    conviction: { weight: 0.20, value: conv, min: 70, available: true },
    volume:     { weight: 0.30, value: volumePass ? 100 : 0, min: 1, available: true },
    orderFlow:  { weight: 0.20, value: orderFlow, min: null, available: orderFlow != null },
    catalyst:   { weight: 0.20, value: catalyst, min: 50, available: true },
    whale:      { weight: 0.10, value: null, min: null, available: false }
  };

  const available = Object.values(factors).filter(f => f.available);
  const availableWeight = available.reduce((s, f) => s + f.weight, 0);
  const rawScore = Object.values(factors).reduce((s, f) => s + f.weight * (f.available ? f.value : 0), 0);
  const weightedScore = availableWeight > 0
    ? available.reduce((s, f) => s + f.weight * f.value, 0) / availableWeight
    : 0;
  const missingFactors = Object.entries(factors).filter(([, f]) => !f.available).map(([k]) => k);

  const convPositive = conv >= 70;
  const catalystMet = catalyst >= 50;

  let signal = 'HOLD';
  if (dumpTriggered || (!convPositive && !volumePass)) {
    signal = 'SELL';
  } else if (weightedScore >= 75 && convPositive && volumePass && catalystMet) {
    signal = 'BUY';
  } else if (convPositive && !volumePass) {
    signal = 'HOLD'; // conviction positive but volume confirmation weakening
  }

  return {
    signal,
    weightedScore: +weightedScore.toFixed(1),  // renormalized over available factors
    rawScore: +rawScore.toFixed(1),            // gated factors = 0 (out of 100)
    maxAchievable: +availableWeight.toFixed(2), // fraction of total weight available
    missingFactors,
    factors: {
      conviction: round2(conv), volume: round2(volumePass ? 100 : 0),
      orderFlow: orderFlow == null ? null : round2(orderFlow),
      catalyst: round2(catalyst), whale: null
    },
    thresholdsMet: { conviction: convPositive, catalyst: catalystMet, volume: volumePass, orderFlow: null, whale: null },
    dumpTriggered,
    simulated: true
  };
}

// 5.2 — position sizing: (Equity × 0.05) × (Conviction/100) × (1/VolFactor).
function size({ equity = SIM_EQUITY, close, conviction, volPct }) {
  const volFactor = clamp((volPct || 0.03) * 100, 1, 10);
  const conv = clamp(conviction, 0, 100) / 100;
  const positionPct = 5 * conv * (1 / volFactor);
  const dollars = equity * 0.05 * conv * (1 / volFactor);
  return {
    equity,
    volFactor: +volFactor.toFixed(2),
    positionPct: +positionPct.toFixed(2),
    dollars: round2(dollars),
    shares: close > 0 ? Math.round(dollars / close) : 0
  };
}

// 5.3 — stop-loss & take-profit tiers.
function exits({ entry, assetType }) {
  const stopPct = assetType === 'crypto' ? 0.10 : 0.15;
  const stop = entry * (1 - stopPct);
  const tp1 = entry * 1.25, tp2 = entry * 1.50;
  return {
    stop: round2(stop), stopPct: +(stopPct * 100).toFixed(0),
    tp1: round2(tp1), tp1Action: 'sell 1/3',
    tp2: round2(tp2), tp2Action: 'sell 1/3',
    tp3: 'remaining 1/3 rides trailing stop 10%',
    rewardRisk: entry > stop ? +((tp1 - entry) / (entry - stop)).toFixed(2) : null
  };
}

// Full decision for one candidate.
function decideFull(c, assetType, { equity, close, volPct } = {}) {
  const d = decide(c, assetType);
  const entry = close || c.close || c.price || null;
  const s = size({ equity, close: entry, conviction: c.score || 0, volPct });
  const x = entry ? exits({ entry, assetType }) : null;
  // Risk per trade = position% × stop distance (must be ≤ 2% of portfolio).
  const riskPct = x ? +(s.positionPct * x.stopPct / 100).toFixed(3) : null;
  const risk = riskPct == null ? null : { pct: riskPct, ok: riskPct <= 2 };
  return { ...d, sizing: s, exits: x, risk };
}

module.exports = { decide, decideFull, size, exits, SIM_EQUITY };
