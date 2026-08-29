'use strict';
/**
 * prop/score.js — Sniper Score™ ranking core (pure, deterministic, no I/O).
 *
 * Weights follow the product spec exactly:
 *   Payout split % ................ 35%
 *   Eval cost + active deal ....... 25%
 *   Drawdown flexibility .......... 25%
 *   Payout speed .................. 15%
 *
 * Every sub-factor is normalised to 0..1 then weighted into a 0..100 composite.
 * Unknown/missing fields contribute a NEUTRAL 0.5 (never a fake good score), and
 * the record's `verified` flag is preserved so the UI can badge provisional rows.
 */

const W = { payout: 0.35, cost: 0.25, drawdown: 0.25, speed: 0.15 };

function clamp01(x) { const n = Number(x); return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0; }
function round2(x) { return Math.round(Number(x) * 100) / 100; }

// Payout split: trader's % of profits. 50% → 0, 100% → 1.
function payoutSub(f) {
  const p = f.payout_split || {};
  const trader = Math.max(Number(p.trader) || 0, Number(p.max_trader) || 0);
  if (!trader) return { score: 0.5, value: null, neutral: true };
  return { score: clamp01((trader - 50) / 50), value: trader, neutral: false };
}

// Eval cost + active deal: lower fee is better (normalised against $600 ceiling),
// an active discount adds up to +0.15 of the sub-score.
function costSub(f) {
  const fee = f.eval_fee && (f.eval_fee.min_usd != null ? f.eval_fee.min_usd : f.eval_fee.usd);
  let base;
  if (fee == null) base = 0.5;
  else base = clamp01(1 - Number(fee) / 600);
  const discount = f.deal && f.deal.active ? (Number(f.deal.discount_pct) || 0) : 0;
  const dealBoost = discount > 0 ? Math.min(0.15, (discount / 100) * 0.30) : 0;
  return { score: clamp01(base + dealBoost), value: fee == null ? null : Number(fee), discount: f.deal ? discount : null, neutral: fee == null };
}

// Drawdown flexibility: more max-DD room is better (4% → 0, 14% → 1).
// Static (non-trailing) DD is more forgiving than trailing; a generous daily DD helps.
function drawdownSub(f) {
  const dd = f.max_drawdown || {};
  const v = dd.value != null ? Number(dd.value) : null;
  let base;
  if (v == null) base = 0.5;
  else base = clamp01((v - 4) / 10);
  let bonus = 0;
  if (dd.type === 'static') bonus += 0.10;
  if (dd.type === 'trailing') bonus -= 0.05;
  if (dd.daily != null && Number(dd.daily) >= 5) bonus += 0.05;
  return { score: clamp01(base + bonus), value: v, type: dd.type || null, daily: dd.daily != null ? Number(dd.daily) : null, neutral: v == null };
}

// Payout speed: frequency + speed label → 0..1. `estimated` is preserved for honest UI.
function speedSub(f) {
  const freq = ((f.payout_frequency || '') + ' ' + ((f.payout_speed && f.payout_speed.label) || '')).toLowerCase();
  let s;
  if (/on-demand|instant|anytime|daily|same[- ]day/.test(freq)) s = 1.0;
  else if (/1[- ]2|24 ?h|48 ?h|1[- ]day|2[- ]day|fast/.test(freq)) s = 0.9;
  else if (/3[- ]5|weekly|bi[- ]?weekly/.test(freq)) s = 0.7;
  else if (/bi[- ]?weekly/.test(freq)) s = 0.55;
  else if (/monthly/.test(freq)) s = 0.4;
  else s = 0.3;
  return {
    score: s,
    frequency: f.payout_frequency || null,
    label: (f.payout_speed && f.payout_speed.label) || null,
    estimated: !!(f.payout_speed && f.payout_speed.estimated)
  };
}

/** Compute the Sniper Score + transparent breakdown for one firm record. */
function sniperScore(f) {
  const payout = payoutSub(f);
  const cost = costSub(f);
  const drawdown = drawdownSub(f);
  const speed = speedSub(f);
  const total =
    payout.score * W.payout +
    cost.score * W.cost +
    drawdown.score * W.drawdown +
    speed.score * W.speed;
  const score = Math.round(clamp01(total) * 100);
  // Completeness: fraction of the five key fields that are actually populated.
  const keys = [
    f.payout_split && (f.payout_split.trader || f.payout_split.max_trader),
    f.eval_fee && (f.eval_fee.min_usd != null || f.eval_fee.usd != null),
    f.max_drawdown && f.max_drawdown.value != null,
    f.model,
    f.profit_target
  ];
  const completeness = round2(keys.filter(Boolean).length / keys.length);
  return {
    score,
    completeness,
    breakdown: {
      payout: { weight: W.payout, sub: round2(payout.score * 100), value: payout.value },
      cost: { weight: W.cost, sub: round2(cost.score * 100), value: cost.value, discount: cost.discount },
      drawdown: { weight: W.drawdown, sub: round2(drawdown.score * 100), value: drawdown.value, type: drawdown.type },
      speed: { weight: W.speed, sub: round2(speed.score * 100), frequency: speed.frequency, estimated: speed.estimated }
    }
  };
}

/** Rank a list of firms: Sniper Score desc, then verified-first, then name. */
function rank(firms) {
  return (firms || [])
    .map((f) => ({ ...f, sniper: sniperScore(f) }))
    .sort((a, b) => {
      if (b.sniper.score !== a.sniper.score) return b.sniper.score - a.sniper.score;
      if (!!b.verified !== !!a.verified) return b.verified ? 1 : -1;
      return (a.name || '').localeCompare(b.name || '');
    });
}

module.exports = { W, sniperScore, rank, payoutSub, costSub, drawdownSub, speedSub, clamp01, round2 };
