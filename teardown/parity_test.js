const fs = require('fs');
const html = fs.readFileSync(__dirname + '/terminal_template.html', 'utf8');

// extract the engine <script> block (the one containing "LIVE ENGINE")
const blocks = html.match(/<script>([\s\S]*?)<\/script>/g);
const engineBlock = blocks.find(b => b.includes('LIVE ENGINE'));
// strip <script> tags and the leading comment, keep up to (but excluding) the fetch functions
let code = engineBlock.replace(/^<script>|<\/script>$/g, '');
code = code.slice(code.indexOf('const CRYPTO'));
code = code.slice(0, code.indexOf('async function fetchBinance'));

eval(code); // defines analyzeSymbol, structure, ensemble, cone, tradeLevels, conviction, ...

const raw = JSON.parse(fs.readFileSync(__dirname + '/raw_ohlcv.json', 'utf8'));
const py = JSON.parse(fs.readFileSync(__dirname + '/results.json', 'utf8')).results;
const pyMap = {};
py.forEach(r => pyMap[r.symbol] = r);

let allMatch = true;
for (const sym of ['AAPL', 'NVDA', 'BTCUSDT', 'CL', 'GC', 'DOGEUSDT', 'AMD']) {
  const bars = raw[sym].bars.map(b => ({ o: b.o, h: b.h, l: b.l, c: b.c, v: b.v }));
  const js = analyzeSymbol(sym, bars);
  const p = pyMap[sym];
  const ok = js.conviction === p.conviction
    && js.ensemble.consensus_pct === p.ensemble.consensus_pct
    && js.trade.direction === p.trade.direction
    && js.structure.trend === p.structure.trend
    && js.trade.rr === p.trade.rr
    && (js.cone ? js.cone.bull === p.cone.bull : p.cone === null);
  if (!ok) allMatch = false;
  console.log((ok ? 'MATCH' : 'DIFF ') + ' ' + sym +
    '  conv ' + js.conviction + '/' + p.conviction +
    '  cons ' + js.ensemble.consensus_pct + '/' + p.ensemble.consensus_pct +
    '  trend ' + js.structure.trend + '/' + p.structure.trend +
    '  dir ' + js.trade.direction + '/' + p.trade.direction +
    '  rr ' + js.trade.rr + '/' + p.trade.rr +
    '  cone.bull ' + (js.cone ? js.cone.bull : 'null') + '/' + (p.cone ? p.cone.bull : 'null'));
}
console.log(allMatch ? '\nALL MATCH — JS port is faithful to the Python engine' : '\nMISMATCH — investigate');
