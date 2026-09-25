/* node assets/catalog.test.js — locks the approved price sheet. */
var assert = require('assert');
var C = require('./catalog.js');

assert.strictEqual(C.engines.length, 5);
assert.strictEqual(C.intelligence.length, 3);
assert.strictEqual(C.bundles.length, 4);
assert.strictEqual(C.comingSoon.length, 3);

assert.strictEqual(C.engines.map(function (e) { return e.name; }).join('|'),
  'No Repaint Pivot|USME ICT Core|USME VWAP Suite|Meridian Engine|Meridian OFI Engine');
assert.strictEqual(C.engines[4].includesStackedImbalance, true);

function expectAnnual(id, monthly, annual, twoFree, pct) {
  var item = C.findSellable(id) || C.byId(C.courses, id) || C.byId(C.bundles, id);
  assert.strictEqual(item.monthly, monthly, id + ' monthly');
  assert.strictEqual(item.annual, annual, id + ' annual');
  var offer = C.annualOffer(monthly, annual);
  assert.strictEqual(offer.twoMonthsFree, twoFree, id + ' two months free');
  assert.strictEqual(offer.pct, pct, id + ' annual pct ' + offer.pct);
}

expectAnnual('pivot', 79, 599, false, 37);
expectAnnual('ict', 199, 1999, false, 16);
expectAnnual('vwap', 249, 2490, true, 17);
expectAnnual('meridian', 449, 4490, true, 17);
expectAnnual('ofi', 599, 5990, true, 17);
expectAnnual('preflight', 49, 490, true, 17);
expectAnnual('forecaster', 49, 490, true, 17);
expectAnnual('radar', 79, 790, true, 17);
expectAnnual('intel-suite', 119, 1190, true, 17);
expectAnnual('academy', 247, 2297, false, 23);

var expectedBundle = {
  starter: { monthly: 129, annual: 1290, listMo: 177, pctMo: 27 },
  'smart-money': { monthly: 449, annual: 4490, listMo: 567, pctMo: 21 },
  'flagship-ofi': { monthly: 649, annual: 6490, listMo: 718, pctMo: 10 },
  'full-suite': { monthly: 999, annual: 9990, listMo: 1694, pctMo: 41 }
};

C.bundles.forEach(function (b) {
  var exp = expectedBundle[b.id];
  assert.ok(exp, b.id);
  assert.strictEqual(b.monthly, exp.monthly);
  assert.strictEqual(b.annual, exp.annual);
  var math = C.bundleMath(b, 'monthly');
  assert.strictEqual(math.vsParts.list, exp.listMo, b.id + ' list');
  assert.strictEqual(math.vsParts.pct, exp.pctMo, b.id + ' pct');
  assert.strictEqual(C.annualOffer(b.monthly, b.annual).twoMonthsFree, true, b.id);
});

assert.strictEqual(C.intelligenceSuite.bestValue, true);
assert.strictEqual(C.byId(C.bundles, 'flagship-ofi').bestValue, true);
assert.strictEqual(C.byId(C.bundles, 'full-suite').bestValue, true);
assert.strictEqual(C.byId(C.bundles, 'starter').bestValue, false);

var up = C.meridianUpgrade('monthly');
assert.strictEqual(up.credit, 449);
assert.strictEqual(up.due, 150);
var upY = C.meridianUpgrade('annual');
assert.strictEqual(upY.credit, 4490);
assert.strictEqual(upY.due, 1500);

assert.strictEqual(C.byId(C.courses, 'challenge').once, 297);
assert.strictEqual(C.byId(C.courses, 'masterplan').once, 447);
assert.strictEqual(C.byId(C.courses, 'futures').once, 797);
assert.strictEqual(C.byId(C.courses, 'complete').once, 1297);
assert.strictEqual(C.byId(C.comingSoon, 'funded-path').once, 597);
assert.strictEqual(C.byId(C.comingSoon, 'usme-edu').once, 1497);
assert.strictEqual(C.byId(C.comingSoon, 'meridian-mastery').once, 697);

assert.ok(C.paymentPlaceholders.items.ofi.monthly.indexOf('TODO_STRIPE_PRICE_') === 0);
assert.ok(C.paymentPlaceholders.items['ofi-upgrade'].proration.indexOf('TODO') === 0);

console.log('catalog.test.js ok');
