// scripts/verify_engine.js — deterministic checks for the conviction engine.
// Run: node scripts/verify_engine.js
const E = require('../api/recon/engine.js');
const assert = require('assert');

let pass = 0, fail = 0;
function check(name, cond) { if (cond) { pass++; } else { fail++; console.error('FAIL:', name); } }

// 1) Weight sum = 1.0
const wsum = E.W.insider + E.W.technical + E.W.volume + E.W.catalyst;
check('weights sum to 1.0', Math.abs(wsum - 1.0) < 1e-9);

// 2) All-strong -> 100
check('all 1.0 -> 100', E.convictionScore({ insider: 1, technical: 1, volume: 1, catalyst: 1 }) === 100);
// 3) All-zero -> 0
check('all 0 -> 0', E.convictionScore({ insider: 0, technical: 0, volume: 0, catalyst: 0 }) === 0);

// 4) Weighted contribution (insider only = 30)
check('insider 1 others 0 -> 30', E.convictionScore({ insider: 1, technical: 0, volume: 0, catalyst: 0 }) === 30);
check('technical 1 others 0 -> 30', E.convictionScore({ insider: 0, technical: 1, volume: 0, catalyst: 0 }) === 30);
check('volume 1 others 0 -> 20', E.convictionScore({ insider: 0, technical: 0, volume: 1, catalyst: 0 }) === 20);
check('catalyst 1 others 0 -> 20', E.convictionScore({ insider: 0, technical: 0, volume: 0, catalyst: 1 }) === 20);

// 5) Tier boundaries (0-100 scale): 88/78/65
check('tier ultra @88', E.tierOf(88) === 'ultra');
check('tier high @87', E.tierOf(87) === 'high');
check('tier high @78', E.tierOf(78) === 'high');
check('tier moderate @77', E.tierOf(77) === 'moderate');
check('tier moderate @65', E.tierOf(65) === 'moderate');
check('tier rejected @64', E.tierOf(64) === 'rejected');

// 6) computeLevels: no inversion for a long (stop<entry<target) across a range
for (const e of [10, 225.16, 15.23, 0.5]) {
  const lv = E.computeLevels({ entry: e, atr: e * 0.05, swingLow: e * 0.9, swingHigh: e * 1.1, rr: 2.5 });
  check(`no inversion @${e}`, lv.stop < lv.entry && lv.entry < lv.target);
  check(`RR>=2.5 @${e}`, lv.rewardRisk >= 2.5 - 1e-6);
}
// moderate (rr=2.0) also sane
const lv2 = E.computeLevels({ entry: 46.25, atr: 2, swingLow: 40, swingHigh: 50, rr: 2.0 });
check('moderate RR>=2', lv2.rewardRisk >= 2.0 - 1e-6 && lv2.stop < lv2.entry && lv2.entry < lv2.target);

// 7) defensive: rr=0 must not break (engine forces 2.0)
const lv0 = E.computeLevels({ entry: 100, atr: 5, swingLow: 90, swingHigh: 110, rr: 0 });
check('rr=0 falls back to 2.0', lv0.rewardRisk >= 2.0 - 1e-6 && lv0.stop < lv0.entry && lv0.entry < lv0.target);

// 8) subScore clamps
check('subScore clamps >1', E.subScore(2) === 100);
check('subScore clamps <0', E.subScore(-1) === 0);

console.log(`\nverify_engine: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
