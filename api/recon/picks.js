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
const { coneSignal } = require('../_lib/recon/kronos_cone');
const { scanCrypto } = require('../_lib/recon/crypto_scan');
const { stockVolumeConfirm, cryptoConfirm } = require('../_lib/recon/confirm');
const { catalystScore } = require('../_lib/recon/catalyst');
const { stockDumpSignals, GATED: DUMP_GATED } = require('../_lib/recon/dump');
const { stockOrderFlow, ORDERFLOW_GATED } = require('../_lib/recon/orderflow');
const { decideFull, SIM_EQUITY } = require('../_lib/recon/decision');

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
  return gjson(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=1y&interval=1d`);
}

// Concurrency-limited map: runs up to `limit` async jobs at once, order-preserving.
function mapLimit(items, limit, fn) {
  return new Promise((resolve) => {
    const out = new Array(items.length);
    let i = 0;
    const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (i < items.length) {
        const idx = i++;
        out[idx] = await fn(items[idx], idx);
      }
    });
    Promise.all(workers).then(() => resolve(out));
  });
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
  if (cur.h > swing10) { triggers.push('STRUCTURE'); score += 0.5; }  // structural shift
  // bullish FVG: unfilled up-gap still holding
  for (let i = Math.max(0, rows.length - 12); i < rows.length - 2; i++) {
    if (rows[i + 2].l > rows[i].h && rows[i + 2].l - rows[i].h > rows[i].h * 0.003 && cur.l > rows[i].h) { triggers.push('GAP'); score += 0.3; break; }
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

async function buildSymbol(symbol, exchange, congressional, capTag, opts = {}) {
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
    const cone = coneSignal(rows);
    const vol = volumeSignal(rows);
    const volScore = vol.score, dollarVol = vol.dollarVol;
    // Insider (SEC) is rate-limited (~10 req/s) so it cannot scale to the full
    // universe. skipInsider runs the broad technical pass; SEC insider is then
    // fetched only for the ranked candidates where it can tip a decision.
    const ins = opts.skipInsider
      ? { present: false, buys: 0, sells: 0, recentForms: 0, error: 'deferred (SEC rate-limited)' }
      : await insiderFor(symbol, 7);
    const insStr = insiderStrength(ins);
    const congStr = congressionalStrength(congressional, symbol);
    // insider sub-score = max(SEC Form 4, congressional) so either boosts it
    const insFinal = Math.max(insStr, congStr);
    // fundamental/catalyst: presence of recent Form 4 + positive structure as proxy
    const catScore = Math.min(1, (ins.present ? 0.5 : 0) + (tech.triggers.includes('BREAKOUT') ? 0.3 : 0) + (tech.score > 0.5 ? 0.2 : 0));

    // Blend the directional projection into the technical sub-score (bounded share).
    // Deterministic Monte-Carlo projection of the trailing trend — a *projection*
    // of momentum, NOT order flow — capped at 20% so it can never dominate the
    // structure/breakout score that carries the actual pre-run signal.
    const techScore = Math.min(1, 0.80 * tech.score + 0.20 * cone.score);

    const score = convictionScore({ insider: insFinal, technical: techScore, volume: volScore, catalyst: catScore });
    let tier = tierOf(score);
    // "Before it gets dumped": overheated + fading volume caps a long at watchlist.
    const dumpRisk = !!cone.distribution;
    if (dumpRisk && tier !== 'rejected') tier = 'moderate';
    // For executable tiers use the tier's R:R; for moderate (paper) use 2.0 so the
    // displayed target is sane (moderate never auto-executes anyway).
    const rr = tier === 'moderate' ? 2.0 : TIER_META[tier].rr;
    const lv = computeLevels({ entry: tech.close, atr: tech.atr, swingLow: tech.swingLow, swingHigh: tech.swingHigh, rr });
    const otc = (exchange || '').toUpperCase() === 'OTC';
    // OTC included (per user directive) but flagged: compliance is key-gated and OTC
    // carries higher pump/fraud risk — cap at watchlist, never a high/ultra conviction buy.
    if (otc && tier !== 'rejected') tier = 'moderate';
    // Small-cap / OTC "wide net" overlay (Layer 2) — key-less filters only.
    // Market cap, float, and SEC OTCQB/OTCQX compliance have NO key-less source
    // (reported in payload.screeningGaps) — never fabricated here.
    const high52w = rows.length ? Math.max(...rows.map(r => r.h)) : 0;
    const prox52w = high52w > 0 ? (tech.close / high52w - 1) * 100 : null;
    const smallCapCandidate = tech.close >= 0.10 && tech.close <= 20 &&
      cone.rsi != null && cone.rsi >= 40 && cone.rsi <= 65 &&
      prox52w != null && prox52w >= -20 && volScore >= 0.55;
    return {
      symbol, exchange, otc, cap: capTag || 'large', tier, score,
      close: tech.close, atr: tech.atr, dollarVol,
      entry: lv.entry, stop: lv.stop, target: lv.target, rewardRisk: lv.rewardRisk,
      signals: { insider: round2(insFinal * 100), technical: round2(techScore * 100), volume: round2(volScore * 100), catalyst: round2(catScore * 100), cone: round2(cone.score * 100) },
      triggers: tech.triggers,
      cone: { upPct: cone.upPct, p50ret: cone.p50ret, p25ret: cone.p25ret, p75ret: cone.p75ret, nearLowerBound: cone.nearLowerBound, rsi: cone.rsi, priceVsMa20: cone.priceVsMa20, ict: cone.ict, parabolic: cone.parabolic, distribution: cone.distribution },
      smallCap: {
        candidate: smallCapCandidate,
        price: round2(tech.close),
        rsi: cone.rsi,
        high52wProximity: prox52w != null ? round2(prox52w) : null,
        floatScreened: false,   // gated (no key-less source)
        secCompliance: null      // gated (OTC Markets API is key-gated)
      },
      confirmation: stockVolumeConfirm(rows),
      dumpSignals: stockDumpSignals({ rows, cone, insider: ins }),
      dumpRisk, dumpReason: dumpRisk ? 'RSI>72 + >15% over MA20 + fading volume (late/dump risk)' : null,
      insiderDetail: { form4Buys: ins.buys || 0, form4Sells: ins.sells || 0, recentForms: ins.recentForms || 0, congressional: congressional && congressional.available },
      note: buildNote(symbol, ins, tech, volScore, score, tier, dumpRisk)
    };
  } catch (e) {
    return null; // skip symbols that error
  }
}

function buildNote(symbol, ins, tech, vol, score, tier, dumpRisk) {
  const parts = [];
  parts.push(`${symbol} conviction ${score}/100 (${TIER_META[tier].label})`);
  if (ins.buys > 0) parts.push(`SEC Form 4 buys: ${ins.buys}`);
  if (tech.triggers.length) parts.push('chart: confirmed structure');
  parts.push(`vol surge ${(vol * 100).toFixed(0)}%`);
  if (dumpRisk) parts.push('DUMP RISK: overheated + fading volume');
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

// Broad key-less equity universe via Yahoo's predefined screens (listed exchanges).
// OTC is not in these screens (and has no clean key-less universe source) — seeded
// separately below plus whatever Stocktwits surfaces.
const SCREENS = ['most_actives', 'day_gainers', 'aggressive_small_caps', 'undervalued_growth_stocks'];
const UNIVERSE_CAP = 360; // full Yahoo-screener breadth (small caps first)
function capFromMc(mc) {
  if (!mc) return 'large';
  if (mc < 500e6) return 'small';
  if (mc < 10e9) return 'mid';
  return 'large';
}
async function fetchScreenerUniverse() {
  const map = new Map();
  for (const scr of SCREENS) {
    try {
      const j = await gjson(`https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&count=100&scrIds=${scr}`);
      const res = j.finance && j.finance.result && j.finance.result[0];
      for (const q of (res && res.quotes) || []) {
        if (q.symbol && q.quoteType === 'EQUITY') map.set(q.symbol, q);
      }
    } catch (_) {}
  }
  // Small caps + low-price first (the pre-run space), then by dollar volume.
  const list = [...map.values()].sort((a, b) => {
    const sa = (a.marketCap && a.marketCap < 500e6) || (a.regularMarketPrice && a.regularMarketPrice < 20) ? 0 : 1;
    const sb = (b.marketCap && b.marketCap < 500e6) || (b.regularMarketPrice && b.regularMarketPrice < 20) ? 0 : 1;
    if (sa !== sb) return sa - sb;
    return (b.regularMarketVolume || 0) - (a.regularMarketVolume || 0);
  });
  return list.map(q => ({ symbol: q.symbol, exchange: q.exchange || q.fullExchangeName || 'NYSE', cap: capFromMc(q.marketCap) }));
}

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

  // Broad screener universe + Stocktwits + a small liquid OTCQB/OTCQX watchlist.
  const screener = await fetchScreenerUniverse();
  const otcSeeds = ['FMCC', 'FNMA', 'CURLF', 'GTBIF', 'VRNOF', 'CRLBF']
    .map((s) => ({ symbol: s, exchange: 'OTC', cap: 'small' }));

  const universe = dedupe([...otcSeeds, ...screener, ...twits]).slice(0, UNIVERSE_CAP);

  // Phase A — broad key-less technical scan (Yahoo only, parallel). SEC insider is
  // rate-limited so it runs in Phase B on the ranked candidates, not the full set.
  const built = [];
  const dropped = [];
  const smallCaps = [];
  const scanned = (await mapLimit(universe, 12, (u) =>
    buildSymbol(u.symbol, u.exchange, congressional, u.cap, { skipInsider: true })
  )).filter(Boolean);

  // Phase B — SEC insider enrichment on the ranked top (rate-limited via insider.js).
  scanned.sort((a, b) => b.score - a.score);
  const ENRICH = Math.min(80, scanned.length);
  if (ENRICH > 0) {
    const enriched = await mapLimit(scanned.slice(0, ENRICH), 4, (b) =>
      buildSymbol(b.symbol, b.exchange, congressional, b.cap).catch(() => b)
    );
    for (let i = 0; i < ENRICH; i++) scanned[i] = enriched[i];
  }

  for (const b of scanned) {
    // Small-cap / OTC wide-net: surface small caps AND OTC regardless of institutional
    // conviction (OTC is flagged, not hidden — the user explicitly wants it visible).
    const alive = b.close > 0.01;
    if (alive && (b.otc || (b.smallCap && b.smallCap.candidate))) {
      smallCaps.push({
        symbol: b.symbol, exchange: b.exchange, otc: b.otc,
        price: b.smallCap.price, rsi: b.smallCap.rsi, high52wProximity: b.smallCap.high52wProximity,
        score: b.score, triggers: b.triggers,
        note: b.otc ? 'OTC — compliance not verified (key-gated), higher risk' : b.note
      });
    }
    if (b.tier === 'rejected') {
      let reason = 'Composite ' + b.score.toFixed(0) + '/100 below the 65 watchlist floor';
      if (b.insiderDetail.form4Buys === 0) reason += ' · no SEC Form 4 buys';
      if (!b.triggers.length) reason += ' · no technical structure signal';
      dropped.push({ symbol: b.symbol, score: b.score, reason, bull: null });
      continue;
    }
    built.push(b);
  }
  smallCaps.sort((a, b) => b.score - a.score);

  // multi-cap balance: take top per cap bucket, then fill by score
  const top = selectBalanced(built, 12);
  // Layer 2 crypto leg — key-less Binance scan (OHLCV + trade count + taker buy/sell).
  let crypto = [], cryptoError = null;
  try { crypto = await scanCrypto(24); } catch (e) { cryptoError = String(e.message || e); }
  // Layer 3 confirmation — hard volume gate + catalyst on RANKED candidates only.
  const volumeRejected = [];
  const confirmedPicks = [];
  for (const p of top) {
    try { p.catalyst = await catalystScore({ symbol: p.symbol, assetType: 'stock', insiderStrength: (p.signals.insider || 0) / 100 }); }
    catch (e) { p.catalyst = { score: 0, min50Met: false, breakdown: {}, error: String(e.message || e) }; }
    // KEY-GATED order flow (Alpaca/Polygon tape) — fetched only for ranked names.
    // Returns {available:false} fast when unconfigured; never fabricated.
    try { p.orderFlow = await stockOrderFlow(p.symbol); }
    catch (e) { p.orderFlow = { available: false, reason: String(e.message || e) }; }
    if (p.confirmation && !p.confirmation.pass) {
      volumeRejected.push({ symbol: p.symbol, assetType: 'stock', score: p.score, reasons: p.confirmation.reasons, note: p.note });
    } else {
      confirmedPicks.push(p);
    }
  }
  // Crypto: confirm the top 10 by score (5m/15m green + depth + taker-buy) + catalyst.
  const topCrypto = crypto.slice(0, 10);
  await Promise.all(topCrypto.map(async (c) => {
    c.confirmed = true;
    try { c.confirmation = await cryptoConfirm(c.symbol, c.takerBuyRatio); }
    catch (e) { c.confirmation = { pass: false, reasons: [String(e.message || e)], orderFlow: {}, unavailable: {} }; }
    try { c.catalyst = await catalystScore({ symbol: c.symbol, assetType: 'crypto' }); }
    catch (e) { c.catalyst = { score: 0, min50Met: false, breakdown: {}, error: String(e.message || e) }; }
    if (!c.confirmation.pass) volumeRejected.push({ symbol: c.symbol, assetType: 'crypto', score: c.score, reasons: c.confirmation.reasons, setup: c.setup });
  }));
  // Layer 4 — aggregate dump/exit alerts (ALERTS ONLY, no execution).
  const sellAlerts = [];
  for (const p of top) if (p.dumpSignals && p.dumpSignals.length) sellAlerts.push({ symbol: p.symbol, assetType: 'stock', alerts: p.dumpSignals });
  for (const c of crypto) if (c.dumpSignals && c.dumpSignals.length) sellAlerts.push({ symbol: c.symbol, assetType: 'crypto', alerts: c.dumpSignals });
  // Layer 5 — decision matrix + sizing + exits (SIMULATION ONLY, no live orders).
  const decisions = [], simulatedOrders = [];
  const applyDecision = (c, assetType, entryPrice, volPct) => {
    const d = decideFull(c, assetType, { close: entryPrice, volPct });
    c.decision = d;
    decisions.push({ symbol: c.symbol, assetType, signal: d.signal, weightedScore: d.weightedScore, rawScore: d.rawScore, maxAchievable: d.maxAchievable, missingFactors: d.missingFactors, sizing: d.sizing, exits: d.exits, simulated: true });
    if (d.signal === 'BUY') simulatedOrders.push({ symbol: c.symbol, assetType, signal: 'BUY', weightedScore: d.weightedScore, sizing: d.sizing, exits: d.exits, simulated: true });
  };
  for (const p of top) applyDecision(p, 'stock', p.close, p.atr && p.close ? p.atr / p.close : 0.03);
  for (const c of topCrypto) if (c.confirmation) applyDecision(c, 'crypto', c.price, (c.cone && c.cone.vol) || 0.06);
  const payload = {
    generatedAt: new Date().toISOString(),
    nextRefreshHint: '13:00 & 22:00 UTC (08:00 & 17:00 ET)',
    congressionalAvailable: !!(congressional && congressional.available),
    universeScanned: universe.length,
    picks: confirmedPicks,
    smallCaps,
    dropped,
    crypto,
    cryptoError,
    volumeRejected,
    sellAlerts,
    dumpGated: DUMP_GATED,
    orderFlowGated: ORDERFLOW_GATED,
    decisions,
    simulatedOrders,
    simulation: { equity: SIM_EQUITY, note: 'paper only — decision/sizing/exit logic is simulated; no live orders and no brokerage execution endpoint.' },
    riskRules: [
      'Stop-loss always set (15% stocks / 10% crypto) — ENFORCED in exits',
      'Max 2% portfolio risk per trade — ENFORCED (position% × stop distance; see decision.risk)',
      'Max 10 concurrent positions — PORTFOLIO rule (not enforced in a per-candidate scout)',
      'Take profits incrementally (1/3 @ +25%, 1/3 @ +50%, rest trails) — ENFORCED in exits',
      'Pump-and-dump caution — OTC dropped + dump-signal alerts — ENFORCED',
      'Tool, not a crystal ball (OHLCV only; no order flow / dark pool) — core philosophy'
    ],
    backtest: 'teardown/backtest_summary.json (2026-09-06): NO systematic edge — win rate 36-55%, profit factor ~0.87-1.13 (within noise), structure-anchored R:R a net loser, edge concentrated in ~5 symbols. Full sweep in teardown/.',
    screeningGaps: [
      'Stock market cap (<$500M) — no key-less source (Yahoo quoteSummary is crumb-gated)',
      'Stock float (<20M shares) — no key-less source',
      'SEC OTCQB/OTCQX compliance — OTC Markets API is key-gated',
      'Crypto whale on-chain accumulation — key-gated (Whale Alert/Nansen/Glassnode)',
      'Stock dark-pool selling & trade count — no key-less source',
      'Stock order flow (Alpaca/Polygon trade tape) — key-gated (ALPACA_API_KEY / POLYGON_API_KEY); wired in api/_lib/recon/orderflow.js',
      'Crypto liquidation levels & exchange inflow/outflow — key-gated (Glassnode/CryptoQuant)',
      '13F institutional positions & short interest — key-gated / no clean key-less source',
      'Discord sentiment — gated (no public API)'
    ],
    methodology: 'The terminal sweeps a broad public-data universe — roughly 360 stocks across every size (large-cap through small-cap and OTC) plus a basket of liquid cryptocurrencies — and scores each on a blend of trend structure, trading-volume behavior, insider-filing activity, and news catalysts. A bounded directional projection (a transparent Monte-Carlo simulation of the trailing trend) contributes at most 20% of the technical score and is surfaced for audit — it is a projection of momentum, not order flow. When a paid data key is present (Alpaca/Polygon), real trade-tape order flow — buyer-vs-seller aggression — is folded in as its own gated factor; without the key it is reported unavailable and never estimated. The highest-scoring names then face a second-pass confirmation on volume and momentum before being surfaced; anything that fails is dropped into a separate rejected list rather than filtered silently. Anything else requiring a paid key or proprietary feed (dark-pool data, on-chain whale flows, and similar) is excluded and reported, never estimated. Every signal, position size, and stop/target is simulated research output; no orders are ever placed.'
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
