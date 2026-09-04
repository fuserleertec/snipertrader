// api/recon/picks.js
// GET /api/recon/picks
// Live, server-side multi-factor recon. Aggregates:
//   - Stocktwits trending + sentiment (key-less)
//   - Yahoo OHLCV technicals (key-less)
//   - SEC Form 4 insider (key-less, real)
//   - Congressional STOCK Act (Quiver-gated; neutral 0 if no key)
// Returns a JSON payload the static page renders. Caches results to /tmp (serverless
// read-only FS except /tmp) keyed by run window to avoid hammering upstreams.

const https = require('https');
const { convictionScore, tierOf, TIER_META, computeLevels } = require('../_lib/recon/engine');
const { insiderFor, insiderStrength } = require('../_lib/recon/insider');
const { congressionalRecent, congressionalStrength } = require('../_lib/recon/congressional');

const UA = { 'User-Agent': 'Mozilla/5.0 (research; snipertrader.ai recon pipeline)' };
const CACHE_TTL_MS = 30 * 60 * 1000;

// In-memory cache (module scope survives warm starts on a given instance)
let _cache = { ts: 0, payload: null };

function gjson(url, headers = UA, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let d = ''; res.setEncoding('utf8'); res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
  });
}

function yahoo(symbol) {
  return gjson(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=3mo&interval=1d`);
}

// Technical sub-score (0..1): breakout/BOS/swing structure + ATR expansion.
function technicalSignal(rows) {
  if (!rows || rows.length < 21) return { score: 0, atr: 0, swingLow: 0, swingHigh: 0, close: 0, triggers: [] };
  const closes = rows.map((r) => r.c), highs = rows.map((r) => r.h), lows = rows.map((r) => r.l);
  const cur = rows[rows.length - 1];
  const h20 = Math.max(...highs.slice(-21, -1));
  const swing10 = Math.max(...highs.slice(-11, -1));
  const swingLow10 = Math.min(...lows.slice(-11, -1));
  const atr = (Math.max(...highs.slice(-15)) - Math.min(...lows.slice(-15))) || cur.c * 0.03;
  const triggers = [];
  let score = 0;
  if (cur.c > h20) { triggers.push('BREAKOUT'); score += 0.85; }   // confirmed 20d breakout = strong
  if (cur.h > swing10) { triggers.push('BOS'); score += 0.5; }      // break-of-structure
  // bullish FVG: unfilled up-gap still holding
  for (let i = Math.max(0, rows.length - 12); i < rows.length - 2; i++) {
    if (rows[i + 2].l > rows[i].h && rows[i + 2].l - rows[i].h > rows[i].h * 0.003 && cur.l > rows[i].h) { triggers.push('FVG'); score += 0.3; break; }
  }
  // ATR expansion bonus (order-flow momentum)
  const recentRange = (highs[rows.length - 1] - lows[rows.length - 1]) / cur.c;
  if (recentRange > atr / cur.c * 0.9) score += 0.2;
  return { score: Math.min(1, score), atr, swingLow: swingLow10, swingHigh: swing10, close: cur.c, triggers };
}

function volumeSignal(rows) {
  if (!rows || rows.length < 16) return { score: 0, dollarVol: 0 };
  const vols = rows.map((r) => r.v).filter((v) => v);
  const avg = vols.slice(-15).reduce((a, b) => a + b, 0) / 15;
  const today = vols[vols.length - 1];
  const surge = avg > 0 ? today / avg : 1;
  const avgClose = rows.slice(-15).reduce((a, r) => a + r.c, 0) / 15;
  // Base credit for a normally-traded name (1x volume → 0.55); 3x+ surge → 1.0.
  const score = Math.max(0, Math.min(1, 0.55 + (surge - 1) / 2 * 0.45));
  return { score, dollarVol: avg * avgClose };
}

async function buildSymbol(symbol, exchange, congressional, capTag) {
  try {
    const j = await yahoo(symbol);
    const res = j.chart.result[0];
    const ts = res.timestamp, q = res.indicators.quote[0];
    const rows = [];
    for (let i = 0; i < ts.length; i++) {
      if (q.close[i] == null || q.high[i] == null) continue;
      rows.push({ t: ts[i], o: q.open[i], h: q.high[i], l: q.low[i], c: q.close[i], v: q.volume[i] });
    }
    const tech = technicalSignal(rows);
    const vol = volumeSignal(rows);
    const volScore = vol.score, dollarVol = vol.dollarVol;
    const ins = await insiderFor(symbol, 7);
    const insStr = insiderStrength(ins);
    const congStr = congressionalStrength(congressional, symbol);
    // insider sub-score = max(SEC Form 4, congressional) so either boosts it
    const insFinal = Math.max(insStr, congStr);
    // fundamental/catalyst: presence of recent Form 4 + positive structure as proxy
    const catScore = Math.min(1, (ins.present ? 0.5 : 0) + (tech.triggers.includes('BREAKOUT') ? 0.3 : 0) + (tech.score > 0.5 ? 0.2 : 0));

    const score = convictionScore({ insider: insFinal, technical: tech.score, volume: volScore, catalyst: catScore });
    const tier = tierOf(score);
    // For executable tiers use the tier's R:R; for moderate (paper) use 2.0 so the
    // displayed target is sane (moderate never auto-executes anyway).
    const rr = tier === 'moderate' ? 2.0 : TIER_META[tier].rr;
    const lv = computeLevels({ entry: tech.close, atr: tech.atr, swingLow: tech.swingLow, swingHigh: tech.swingHigh, rr });
    // Drop OTC microcaps (pump/fraud risk) — they are not investable recommendations.
    if ((exchange || '').toUpperCase() === 'OTC') return null;
    return {
      symbol, exchange, cap: capTag || 'large', tier, score,
      close: tech.close, atr: tech.atr, dollarVol,
      entry: lv.entry, stop: lv.stop, target: lv.target, rewardRisk: lv.rewardRisk,
      signals: { insider: round2(insFinal * 100), technical: round2(tech.score * 100), volume: round2(volScore * 100), catalyst: round2(catScore * 100) },
      triggers: tech.triggers,
      insiderDetail: { form4Buys: ins.buys || 0, form4Sells: ins.sells || 0, recentForms: ins.recentForms || 0, congressional: congressional && congressional.available },
      note: buildNote(symbol, ins, tech, volScore, score, tier)
    };
  } catch (e) {
    return null; // skip symbols that error
  }
}

function buildNote(symbol, ins, tech, vol, score, tier) {
  const parts = [];
  parts.push(`${symbol} conviction ${score}/100 (${TIER_META[tier].label})`);
  if (ins.buys > 0) parts.push(`SEC Form 4 buys: ${ins.buys}`);
  if (tech.triggers.length) parts.push(`chart: ${tech.triggers.join('/')}`);
  parts.push(`vol surge ${(vol * 100).toFixed(0)}%`);
  return parts.join(' · ');
}

function round2(x) { return Math.round(Number(x) * 100) / 100; }

// Cap classification for multi-cap balance. Uses the explicit seed cap tag when
// present; otherwise falls back to dollar-volume heuristic.
function capOf(b) {
  if (b.cap && ['small', 'mid', 'large'].includes(b.cap)) return b.cap;
  const dv = b.dollarVol || 0;
  if (dv < 20e6) return 'small';
  if (dv < 100e6) return 'mid';
  return 'large';
}

function tierRank(t) { return { ultra: 3, high: 2, moderate: 1, rejected: 0 }[t] || 0; }

async function run(force = false) {
  const now = Date.now();
  if (!force && _cache.payload && now - _cache.ts < CACHE_TTL_MS) return _cache.payload;

  const congressional = await congressionalRecent(7);
  // 1) seed universe: Stocktwits trending + explicit multi-cap watchlist.
  //    cap tag = intended capitalization bucket for balanced selection.
  let trending = [], watchlist = [];
  try { trending = (await gjson('https://api.stocktwits.com/api/2/trending/symbols.json')).symbols || []; } catch (_) {}
  try { watchlist = (await gjson('https://api.stocktwits.com/api/2/watchlist/symbols.json')).symbols || []; } catch (_) {}

  const twits = dedupe([...trending, ...watchlist])
    .filter((s) => !['CRYPTO', 'FX'].includes((s.exchange || '').toUpperCase()))
    .map((s) => ({ symbol: s.symbol, exchange: s.exchange || 'NASDAQ', cap: 'large' }));

  // Curated multi-cap momentum seeds (high-beta breakout candidates across caps).
  const smallSeeds = ['RKLB', 'ASTS', 'SOFI', 'SMCI', 'APP', 'RIVN', 'CAPR', 'NBIS', 'PLUG', 'CLOV', 'MARA', 'RIOT']
    .map((s) => ({ symbol: s, exchange: 'NASDAQ', cap: 'small' }));
  const midSeeds = ['PLTR', 'COIN', 'NVDA', 'TSM', 'ARM', 'SNOW', 'MSTR', 'DKNG', 'HOOD', 'RDDT']
    .map((s) => ({ symbol: s, exchange: 'NASDAQ', cap: 'mid' }));
  const largeSeeds = ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'AMD', 'AVGO', 'CRM', 'NFLX', 'LLY']
    .map((s) => ({ symbol: s, exchange: 'NASDAQ', cap: 'large' }));

  const universe = dedupe([...twits, ...smallSeeds, ...midSeeds, ...largeSeeds]).slice(0, 50);

  const built = [];
  const dropped = [];
  for (const u of universe) {
    const b = await buildSymbol(u.symbol, u.exchange, congressional, u.cap);
    if (!b) continue;
    if (b.tier === 'rejected') {
      let reason = 'Composite ' + b.score.toFixed(0) + '/100 below the 65 watchlist floor';
      if (b.insiderDetail.form4Buys === 0) reason += ' · no SEC Form 4 buys';
      if (!b.triggers.length) reason += ' · no chart breakout/BOS/FVG';
      dropped.push({ symbol: b.symbol, score: b.score, reason, bull: null });
      continue;
    }
    built.push(b);
  }

  // multi-cap balance: take top per cap bucket, then fill by score
  const top = selectBalanced(built, 12);
  const payload = {
    generatedAt: new Date().toISOString(),
    nextRefreshHint: '13:00 & 22:00 UTC (08:00 & 17:00 ET)',
    congressionalAvailable: !!(congressional && congressional.available),
    universeScanned: universe.length,
    picks: top,
    dropped,
    methodology: 'Multi-cap recon: Stocktwits sentiment + Yahoo technicals (ATR/swing) + SEC Form 4 insider; congressional STOCK Act when Quiver key is set. 0-100 conviction = Insider 30 / Technical 30 / Volume 20 / Catalyst 20. Simulated only; no orders placed.'
  };
  _cache = { ts: now, payload };
  return payload;
}

function dedupe(arr) {
  const seen = new Set(); const out = [];
  for (const a of arr) { if (!seen.has(a.symbol)) { seen.add(a.symbol); out.push(a); } }
  return out;
}

function selectBalanced(built, n) {
  const buckets = { small: [], mid: [], large: [] };
  for (const b of built) {
    const c = capOf(b);
    buckets[c].push(b);
  }
  for (const k of Object.keys(buckets)) buckets[k].sort((a, b) => b.score - a.score);
  const out = [];
  // round-robin to guarantee small/mid/large representation
  const order = ['small', 'mid', 'large'];
  let added = true;
  while (out.length < n && added) {
    added = false;
    for (const k of order) {
      if (buckets[k].length && out.length < n) { out.push(buckets[k].shift()); added = true; }
    }
  }
  // top up with highest remaining if a bucket was empty
  if (out.length < n) {
    const rest = built.filter((b) => !out.includes(b)).sort((a, b) => b.score - a.score);
    for (const b of rest) { if (out.length < n) out.push(b); }
  }
  return out;
}

// Health probe: cheap liveness + cache-state snapshot (no upstream re-scrape).
// On the long-lived local dev server this shares run()'s in-memory cache; on Vercel
// it is a liveness probe (separate instance, cache fields read cold/empty).
function health() {
  const now = Date.now();
  const p = _cache.payload;
  const cacheAgeMs = _cache.ts ? now - _cache.ts : null;
  return {
    status: 'ok',
    service: 'recon',
    uptimeSec: Math.round(process.uptime()),
    generatedAt: p ? p.generatedAt : null,
    cacheAgeMs,
    cacheFresh: cacheAgeMs !== null && cacheAgeMs < CACHE_TTL_MS,
    picks: p ? p.picks.length : 0,
    dropped: p ? p.dropped.length : 0,
    universeScanned: p ? p.universeScanned : 0,
    congressionalAvailable: p ? !!p.congressionalAvailable : false,
    nextRefreshHint: p ? p.nextRefreshHint : '08:00 & 17:00 ET',
    timestamp: new Date().toISOString(),
  };
}

module.exports = async (req, res) => {
  try {
    const payload = await run();
    res.setHeader('Cache-Control', 's-maxage=1800, stale-while-revalidate');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.json(payload);
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
module.exports.buildSymbol = buildSymbol;
module.exports.run = run;
module.exports.health = health;

// Test/diagnostic hook (harmless in prod; used by node test harness)
if (require.main === module) {
  const arg = process.argv[2];
  if (arg) {
    (async () => {
      const { buildSymbol } = require('./picks');
      const cong = await require('../_lib/recon/congressional').congressionalRecent(7);
      const r = await buildSymbol(arg, 'NASDAQ', cong);
      console.log(JSON.stringify(r, null, 2));
    })().catch((e) => { console.error('ERR', e); process.exit(1); });
  } else {
    run(true).then((p) => { console.log(JSON.stringify(p, null, 2)); }).catch((e) => { console.error(e); process.exit(1); });
  }
}
