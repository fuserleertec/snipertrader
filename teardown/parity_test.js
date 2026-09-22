const fs = require('fs');
const engine = fs.readFileSync(__dirname + '/../assets/market_engine.js', 'utf8');

// load the shared engine (single source of truth): strip 'use strict', keep the
// pure-analysis functions up to (but excluding) the fetch functions
let code = engine.replace(/'use strict';/g, '');
code = code.slice(code.indexOf('const CRYPTO'));
code = code.slice(0, code.indexOf('async function fetchBinance'));

eval(code); // defines analyzeSymbol, structure, ensemble, cone, tradeLevels, conviction, ...

const raw = JSON.parse(fs.readFileSync(__dirname + '/raw_ohlcv.json', 'utf8'));
const pyData = JSON.parse(fs.readFileSync(__dirname + '/results.json', 'utf8'));
const py = pyData.results;
const cond = pyData.conditional;   // conditional cone buckets, embedded in results.json
const pyMap = {};
py.forEach(r => pyMap[r.symbol] = r);

// snapshot cross-section (mirror Python analyze()): median/MAD of each symbol's 120d momentum (skip 20d).
// Literals match compute_engine's MOM_WINDOW=120 / MOM_SKIP=20 (const in eval'd block doesn't leak here).
const latestRocs = [];
for (const sym in raw) {
  const closes = raw[sym].bars.map(b => b.c);
  if (closes.length >= 121) latestRocs.push(closes[closes.length-1-20]/closes[closes.length-1-120]-1);
}
const med = median(latestRocs), mad = median(latestRocs.map(r => Math.abs(r-med)));
const u = { cs_median: med, cs_mad: mad };

let allMatch = true;
for (const sym of ['AAPL', 'NVDA', 'BTCUSDT', 'CL', 'GC', 'DOGEUSDT', 'AMD']) {
  const bars = raw[sym].bars.map(b => ({ o: b.o, h: b.h, l: b.l, c: b.c, v: b.v }));
  const js = analyzeSymbol(sym, bars, u, cond);
  const p = pyMap[sym];
  const ok = js.conviction === p.conviction
    && js.ensemble.consensus_pct === p.ensemble.consensus_pct
    && js.trade.direction === p.trade.direction
    && js.structure.trend === p.structure.trend
    && js.trade.rr === p.trade.rr
    && (js.cone ? (js.cone.bull === p.cone.bull && js.cone.scope === p.cone.scope && js.cone.n === p.cone.n) : p.cone === null);
  if (!ok) allMatch = false;
  console.log((ok ? 'MATCH' : 'DIFF ') + ' ' + sym +
    '  conv ' + js.conviction + '/' + p.conviction +
    '  cons ' + js.ensemble.consensus_pct + '/' + p.ensemble.consensus_pct +
    '  trend ' + js.structure.trend + '/' + p.structure.trend +
    '  dir ' + js.trade.direction + '/' + p.trade.direction +
    '  rr ' + js.trade.rr + '/' + p.trade.rr +
    '  cone ' + (js.cone ? js.cone.bull + '/' + js.cone.scope + '/' + js.cone.n : 'null') +
    '  vs  ' + (p.cone ? p.cone.bull + '/' + p.cone.scope + '/' + p.cone.n : 'null'));
}
console.log(allMatch ? '\nALL MATCH — JS port is faithful to the Python engine' : '\nMISMATCH — investigate');
