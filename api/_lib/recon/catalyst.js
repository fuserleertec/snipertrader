'use strict';
// api/_lib/recon/catalyst.js
// ---------------------------------------------------------------------------
// Layer 3.4 — DIRECTIONAL catalyst scoring (0-100), key-less sources only:
//   + Google News RSS headline classification — now scored by DIRECTION. A
//     bullish catalyst event adds points; a bearish one subtracts. So the
//     system reads *which way* the catalyst points, not merely that one exists
//     (the prior bug: "FDA rejects drug" scored the same +30 as "FDA approves").
//   + SEC Form 4 insider strength (passed in, buy-side scaled to +20)
//   + GitHub commit recency (crypto, small curated repo map; +10)
// 13F, short interest, Discord, and on-chain whale tracking are KEY-GATED →
// reported as unavailable (0 points), never fabricated.
//
// Ceilings (directional, honest): stock = bull event 40 + insider 20 = 60;
// crypto = bull event 40 + github 10 = 50. This makes the decision gate
// (catalyst ≥ 50) REACHABLE, so a BUY can actually fire on a strong
// directional catalyst + conviction + volume — instead of being mathematically
// impossible because presence-only scoring topped out at 45/40 < 50.
// ---------------------------------------------------------------------------

const https = require('https');

const CATALYSTS = {
  stock: [
    { key: 'FDA/approval', pts: 40, re: /\b(fda|approval|approved|clearance|cleared|designation)\b/i },
    { key: 'earnings', pts: 40, re: /\b(earnings|quarterly results|revenue|profit|guidance)\b/i },
    { key: 'contract-win', pts: 40, re: /\b(contract|awarded|selected|wins?|backlog)\b/i },
    { key: 'partnership', pts: 20, re: /\b(partnership|collaborat\w*|teams? up|alliance|integration)\b/i },
    { key: 'analyst-action', pts: 20, re: /\b(upgrade[sd]?|downgrade[sd]?|price target|initiat\w*|rating)\b/i }
  ],
  crypto: [
    { key: 'exchange-listing', pts: 40, re: /\b(listing|listed|to be listed|new listing|trading pair|delist\w*)\b/i },
    { key: 'upgrade-mainnet', pts: 30, re: /\b(upgrade|mainnet|hard fork|testnet|network launch)\b/i },
    { key: 'partnership', pts: 20, re: /\b(partnership|collaborat\w*|integration|integrates|adopt\w*)\b/i }
  ]
};

// Direction lexicon — count bullish vs bearish terms per headline, majority wins.
// A heuristic (documented, not a sentiment model); conservative enough that a
// headline with no directional vocabulary scores 'neutral' rather than guessing.
const BULL_RE = /\b(beats?\b|tops\b|surges?\b|soars?\b|wins?\b|won\b|approved|approval|cleared|clearance|upgrade[sd]?|bullish|rall(?:y|ies|ied)|record (?:high|profit|revenue)|awarded|selected|outperform|raises?\b|raised|strong|jumps?\b|climbs?\b|gains?\b|partnership|collaborat\w*|alliance|listing|listed|mainnet|launch\w*|adopt\w*|integrat\w*|breakthrough|positive|buyback|buyout|takeover)\b/i;

const BEAR_RE = /\b(miss(?:es|ed)?\b|drop[sd]?\b|plunges?\b|falls?\b|fell\b|reject[sd]?|denies?\b|denied|downgrade[sd]?|bearish|lawsuit|probe|investigat\w*|halt[sd]?|delist\w*|bankrupt\w*|fraud|loss(?:es)?\b|warn\w*|slump\w*|tumbles?\b|crash|recall\b|weak|negative|sell[ -]?off|downturn|delay[sd]?|suspension|scam|exploit|hack\w*|breach\b|guidance cut|below expectations|disappoint\w*|decline[sd]?)\b/i;

function polarity(text) {
  const b = (text.match(BULL_RE) || []).length;
  const r = (text.match(BEAR_RE) || []).length;
  if (b > r) return 'bull';
  if (r > b) return 'bear';
  return 'neutral';
}

// Curated repo map for major coins (GitHub commit-recent proxy). Unmapped = null.
const GITHUB_MAP = {
  BTCUSDT: 'bitcoin/bitcoin', ETHUSDT: 'ethereum/go-ethereum', SOLUSDT: 'solana-labs/solana',
  BNBUSDT: 'bnb-chain/bsc', ADAUSDT: 'IntersectMBO/cardano-node', DOGEUSDT: 'dogecoin/dogecoin',
  AVAXUSDT: 'ava-labs/avalanchego', LINKUSDT: 'smartcontractkit/chainlink', DOTUSDT: 'paritytech/polkadot-sdk',
  LTCUSDT: 'litecoin-project/litecoin', UNIUSDT: 'Uniswap/v3-core', ATOMUSDT: 'cosmos/cosmos-sdk'
};

function getText(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0 (research; snipertrader.ai)' } }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let d = ''; res.setEncoding('utf8'); res.on('data', (c) => (d += c)); res.on('end', () => resolve(d));
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
  });
}

// Fetch Google News RSS titles for a query.
async function newsTitles(query) {
  const q = encodeURIComponent(query);
  const url = `https://news.google.com/rss/search?q=${q}&hl=en-US&gl=US&ceid=US:en`;
  try {
    const xml = await getText(url);
    const titles = [];
    const re = /<title>([^<]*)<\/title>/g;
    let m;
    while ((m = re.exec(xml)) !== null) {
      const t = m[1].replace(/&amp;/g, '&').replace(/&#39;/g, "'").trim();
      if (t && t !== 'Google News') titles.push(t);
    }
    return titles.slice(0, 40);
  } catch (_) {
    return [];
  }
}

// Classify titles against the catalyst table → DIRECTIONAL dominant event.
// Each detected event takes the majority polarity of the headlines that matched
// it; bullish → +pts, bearish → −pts, tie → 0 (ambiguous catalyst isn't a
// catalyst). The dominant event is the single largest-magnitude one (no summing,
// to avoid inflating one story across near-duplicate headlines). `direction` is
// the aggregate headline polarity (majority of non-neutral), used as the
// bull/bear veto downstream.
function classifyNews(titles, assetType) {
  const table = CATALYSTS[assetType] || [];
  const pols = titles.map(polarity);
  const nBull = pols.filter(p => p === 'bull').length;
  const nBear = pols.filter(p => p === 'bear').length;
  const direction = nBull > nBear ? 'bull' : (nBear > nBull ? 'bear' : 'neutral');

  let best = { key: null, pts: 0, dir: 'neutral' };
  const matched = [];
  for (const c of table) {
    const hits = titles.filter(t => c.re.test(t));
    if (!hits.length) continue;
    const hp = hits.map(polarity);
    const hb = hp.filter(p => p === 'bull').length;
    const hr = hp.filter(p => p === 'bear').length;
    const dir = hb > hr ? 'bull' : (hr > hb ? 'bear' : 'neutral');
    matched.push({ key: c.key, dir });
    const signed = dir === 'bull' ? c.pts : (dir === 'bear' ? -c.pts : 0);
    if (Math.abs(signed) > Math.abs(best.pts)) best = { key: c.key, pts: signed, dir };
  }
  return { points: best.pts, dominant: best.key, dominantDir: best.dir, direction, matched };
}

// GitHub recency proxy: any commit in the last 7 days.
async function githubActive(repo) {
  if (!repo) return null;
  try {
    const since = new Date(Date.now() - 7 * 86400000).toISOString();
    const d = await new Promise((resolve, reject) => {
      const url = `https://api.github.com/repos/${repo}/commits?since=${encodeURIComponent(since)}&per_page=1`;
      const req = https.get(url, { headers: { 'User-Agent': 'snipertrader-recon', 'Accept': 'application/vnd.github+json' } }, (res) => {
        let b = ''; res.on('data', (c) => (b += c)); res.on('end', () => { try { resolve(JSON.parse(b)); } catch (e) { reject(e); } });
      });
      req.on('error', reject); req.setTimeout(15000, () => req.destroy(new Error('timeout')));
    });
    return Array.isArray(d) && d.length > 0;
  } catch (_) { return null; }
}

// assetType: 'stock' | 'crypto'. insiderStrength: 0..1 (stocks).
async function catalystScore({ symbol, assetType = 'stock', insiderStrength = 0 }) {
  const breakdown = { news: 0, newsDirection: 'neutral', newsDominant: null, newsDominantDir: null, insider: 0, github: null, fund13f: null, shortInterest: null };
  let score = 0;

  // News (directional dominant event).
  const query = assetType === 'crypto' ? `${symbol.replace(/USDT$/, '')} crypto` : `${symbol} stock`;
  const titles = await newsTitles(query);
  const nw = classifyNews(titles, assetType);
  breakdown.news = nw.points;
  breakdown.newsDirection = nw.direction;
  breakdown.newsDominant = nw.dominant;
  breakdown.newsDominantDir = nw.dominantDir;
  score += nw.points;

  // Insider (stocks) — scale the 0..1 buy-strength to +20.
  if (assetType === 'stock' && insiderStrength > 0) {
    breakdown.insider = Math.round(insiderStrength * 20);
    score += breakdown.insider;
  }

  // GitHub (crypto) — +10 if a mapped repo committed in the last 7 days.
  if (assetType === 'crypto') {
    const repo = GITHUB_MAP[symbol] || null;
    if (repo) {
      const active = await githubActive(repo);
      breakdown.github = active; // true | false | null
      if (active === true) score += 10;
    }
  }

  score = Math.max(0, Math.min(100, Math.round(score)));
  // Overall direction: news leads; a neutral news tape defaults to insider-buy
  // (bull) if insider buying is present, else neutral.
  let direction = nw.direction;
  if (direction === 'neutral' && breakdown.insider > 0) direction = 'bull';
  return { score, min50Met: score >= 50, direction, breakdown };
}

module.exports = { catalystScore, classifyNews, polarity, GITHUB_MAP };
