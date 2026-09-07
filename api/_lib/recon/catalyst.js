'use strict';
// api/_lib/recon/catalyst.js
// ---------------------------------------------------------------------------
// Layer 3.4 — catalyst scoring (0-100), key-less sources only:
//   + Google News RSS headline keyword classification (dominant-event scoring)
//   + SEC Form 4 insider strength (passed in)
//   + GitHub commit recency (crypto, small curated repo map)
// 13F institutional positions, short interest, Discord, and on-chain whale
// tracking are KEY-GATED → reported as unavailable (0 points), never fabricated.
// ---------------------------------------------------------------------------

const https = require('https');

const CATALYSTS = {
  stock: [
    { key: 'FDA/approval', pts: 30, re: /\b(fda|approval|approved|clearance|cleared|designation)\b/i },
    { key: 'earnings-beat', pts: 30, re: /\b(earnings|profit|revenue)\b[^.]{0,60}\b(beat|beats|top|surge|soar)\b/i },
    { key: 'contract-win', pts: 30, re: /\b(contract|awarded|selected|wins?|deal)\b/i },
    { key: 'partnership', pts: 15, re: /\b(partnership|collaboration|teams? up|alliance)\b/i }
  ],
  crypto: [
    { key: 'exchange-listing', pts: 30, re: /\b(listing|listed|to be listed|new listing|trading pair)\b/i },
    { key: 'upgrade-mainnet', pts: 20, re: /\b(upgrade|mainnet|hard fork|testnet|network launch)\b/i },
    { key: 'partnership', pts: 15, re: /\b(partnership|collaboration|integration|integrates)\b/i }
  ]
};

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

// Classify titles against the catalyst table → dominant event points (no summing,
// to avoid inflating a single story across near-duplicate headlines).
function classifyNews(titles, assetType) {
  const table = CATALYSTS[assetType] || [];
  let best = { key: null, pts: 0 };
  const matched = [];
  for (const c of table) {
    if (titles.some(t => c.re.test(t))) {
      matched.push(c.key);
      if (c.pts > best.pts) best = { key: c.key, pts: c.pts };
    }
  }
  return { points: best.pts, dominant: best.key, matched };
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
  const breakdown = { news: 0, newsDominant: null, insider: 0, github: null, fund13f: null, shortInterest: null };
  let score = 0;

  // News (dominant single event).
  const query = assetType === 'crypto' ? `${symbol.replace(/USDT$/, '')} crypto` : `${symbol} stock`;
  const titles = await newsTitles(query);
  const nw = classifyNews(titles, assetType);
  breakdown.news = nw.points; breakdown.newsDominant = nw.dominant;
  score += nw.points;

  // Insider (stocks) — scale the 0..1 strength to the spec's +15.
  if (assetType === 'stock' && insiderStrength > 0) {
    breakdown.insider = Math.round(insiderStrength * 15);
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
  return { score, min50Met: score >= 50, breakdown };
}

module.exports = { catalystScore, classifyNews, GITHUB_MAP };
