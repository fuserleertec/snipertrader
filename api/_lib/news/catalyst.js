'use strict';
// api/_lib/news/catalyst.js
// ---------------------------------------------------------------------------
// LLM-scored news + SEC EDGAR catalyst engine for the Market Forecaster.
// Real, key-less sources only:
//   + Google News RSS headlines (no key)
//   + SEC EDGAR recent filings — 8-K / 10-Q / 10-K / 20-F / Form 4 (no key)
// Scoring:
//   + DeepSeek structured-JSON (impact + sentiment + per-catalyst summary)
//     when DEEPSEEK_API_KEY is configured and headlines exist.
//   + falls back to the regex keyword heuristic in _lib/recon/catalyst.js
//     (never fabricates a headline, a score, or a sentiment).
// ---------------------------------------------------------------------------

const https = require('https');
const { aiChat, isConfigured } = require('../../_ai_providers');
const { classifyNews } = require('../recon/catalyst');
const { tickerToCik } = require('../recon/insider');

const UA = { 'User-Agent': 'Mozilla/5.0 (research; snipertrader.ai news-catalyst)' };

function getText(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: UA }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let d = ''; res.setEncoding('utf8'); res.on('data', (c) => (d += c)); res.on('end', () => resolve(d));
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
  });
}

function getJSON(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': UA['User-Agent'], 'Accept': 'application/json' } }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let d = ''; res.setEncoding('utf8'); res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
  });
}

// Google News RSS titles for a query.
async function newsTitles(query) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(query)}&hl=en-US&gl=US&ceid=US:en`;
  try {
    const xml = await getText(url);
    const titles = [];
    const re = /<title>([^<]*)<\/title>/g;
    let m;
    while ((m = re.exec(xml)) !== null) {
      const t = m[1].replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim();
      if (t && t !== 'Google News' && !/ - Google News$/.test(t)) titles.push(t);
    }
    return titles;
  } catch (_) { return []; }
}

// Near-duplicate removal: drop a title whose significant words mostly overlap an
// already-kept title (catches syndicated rewording of the same story).
function dedupe(titles) {
  const sig = (t) => new Set(String(t).toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim().split(' ').filter((w) => w.length > 2));
  const kept = [];
  for (const t of titles) {
    const a = sig(t); if (!a.size) continue;
    let dup = false;
    for (const k of kept) {
      const b = sig(k); if (!b.size) continue;
      let inter = 0; for (const w of a) if (b.has(w)) inter++;
      if (inter / Math.min(a.size, b.size) >= 0.8) { dup = true; break; }
    }
    if (!dup) kept.push(t);
  }
  return kept;
}

function detectAsset(symbol) {
  const s = (symbol || '').trim().toUpperCase().replace(/[^A-Z0-9.]/g, '');
  if (/USDT$|USDC$|BUSD$/.test(s)) return 'crypto';
  if (/^(CL|GC|ES|NQ|HG|SI|NG|ZN|ZB|ZF|PL|KC)1?!?$/.test(s)) return 'futures';
  return 'stock';
}

// Recent SEC EDGAR filings — form type, filing date, item codes, doc URL.
// Context for the LLM only; the LLM decides materiality, not the filing count.
async function recentFilings(symbol) {
  try {
    const cik = await tickerToCik(symbol);
    if (!cik) return [];
    const sub = await getJSON(`https://data.sec.gov/submissions/CIK${cik}.json`);
    const r = sub.filings.recent;
    const cutoff = Date.now() - 45 * 86400000;
    const KEEP = new Set(['8-K', '10-Q', '10-K', '20-F', 'SC 13D', 'SC 13G', '4']);
    const out = [];
    for (let i = 0; i < r.form.length && out.length < 8; i++) {
      const ts = Date.parse(r.filingDate[i]);
      if (isNaN(ts) || ts < cutoff) continue;
      if (!KEEP.has(r.form[i])) continue;
      const acc = (r.accessionNumber[i] || '').replace(/-/g, '');
      const doc = r.primaryDocument[i] || '';
      out.push({
        form: r.form[i],
        date: r.filingDate[i],
        items: (r.items && r.items[i]) || '',
        url: acc ? `https://www.sec.gov/Archives/edgar/data/${parseInt(cik, 10)}/${acc}/${doc}` : ''
      });
    }
    return out;
  } catch (_) { return []; }
}

const SYSTEM = `You are a market-catalyst analyst for a trading-education tool. You score news for ONE ticker.
Rules:
- Use ONLY the headlines and SEC filings provided. Do NOT invent events, prices, or facts.
- A headline about a DIFFERENT company that merely shares a word (e.g. "apple" = the fruit, not AAPL) is irrelevant -> relevance_score 0 and exclude it.
- If nothing is material, return an empty catalysts array, sentiment_bias NEUTRAL, market_impact_score 0.
- Output STRICT JSON only — no markdown fences, no commentary — matching this exact schema:
{
  "sentiment_bias": "BULLISH",
  "market_impact_score": 0,
  "catalysts": [
    {
      "headline": "exact headline text",
      "catalyst_event": "Earnings | Partnership | Contract | Regulatory | Listing | Analyst | Other",
      "relevance_score": 0.0,
      "market_impact_score": 0,
      "sentiment_bias": "BULLISH",
      "time_horizon": "INTRADAY",
      "executive_summary": "one plain-English sentence"
    }
  ]
}
- market_impact_score is 0-100 (0 none, 30 minor, 60 significant, 90+ market-moving).
- time_horizon is one of INTRADAY | SWING | POSITION | NONE.
- Return at most 3 catalysts (highest impact first), each with relevance_score >= 0.6.`;

function buildUserContent(symbol, assetType, titles, filings) {
  const head = titles.length ? titles.map((t, i) => `${i + 1}. ${t}`).join('\n') : '(no headlines returned)';
  const fil = filings.length
    ? filings.map((f) => `- ${f.form} ${f.date}${f.items ? ' [items ' + f.items + ']' : ''}`).join('\n')
    : '(no recent SEC filings)';
  return `TICKER: ${symbol}\nASSET: ${assetType}\n\nHEADLINES:\n${head}\n\nRECENT SEC FILINGS:\n${fil}`;
}

function normBias(s) { const v = String(s || '').toUpperCase(); return ['BULLISH', 'BEARISH', 'NEUTRAL'].includes(v) ? v : 'NEUTRAL'; }
function normHorizon(s) { const v = String(s || '').toUpperCase(); return ['INTRADAY', 'SWING', 'POSITION', 'NONE'].includes(v) ? v : 'NONE'; }
function clampInt(x, lo, hi) { const n = Math.round(Number(x)); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : 0; }
function clampNum(x, lo, hi) { const n = Number(x); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : 0; }

function coerceJSON(text) {
  if (!text) return null;
  let s = String(text).trim();
  s = s.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  const a = s.indexOf('{'), b = s.lastIndexOf('}');
  if (a === -1 || b === -1 || b <= a) return null;
  try {
    const obj = JSON.parse(s.slice(a, b + 1));
    if (!obj || typeof obj !== 'object') return null;
    const cats = Array.isArray(obj.catalysts) ? obj.catalysts.slice(0, 3).map((c) => ({
      headline: String(c.headline || '').slice(0, 300),
      catalyst_event: String(c.catalyst_event || 'Other').slice(0, 60),
      relevance_score: clampNum(c.relevance_score, 0, 1),
      market_impact_score: clampInt(c.market_impact_score, 0, 100),
      sentiment_bias: normBias(c.sentiment_bias),
      time_horizon: normHorizon(c.time_horizon),
      executive_summary: String(c.executive_summary || '').slice(0, 500)
    })).filter((c) => c.headline || c.executive_summary) : [];
    return {
      sentiment_bias: normBias(obj.sentiment_bias),
      market_impact_score: clampInt(obj.market_impact_score, 0, 100),
      catalysts: cats
    };
  } catch (_) { return null; }
}

async function llmScore(symbol, assetType, titles, filings) {
  const r = await aiChat({
    provider: 'deepseek',
    messages: [
      { role: 'system', content: SYSTEM },
      { role: 'user', content: buildUserContent(symbol, assetType, titles, filings) }
    ],
    options: { temperature: 0.1, maxTokens: 1200 }
  });
  return coerceJSON(r && r.content);
}

async function newsCatalyst(symbol) {
  const assetType = detectAsset(symbol);
  const base = assetType === 'crypto' ? symbol.replace(/USDT$|USDC$|BUSD$/, '') : symbol;
  const query = assetType === 'crypto' ? `${base} crypto`
    : assetType === 'futures' ? `${symbol} futures`
    : `${symbol} stock`;
  const titles = dedupe(await newsTitles(query)).slice(0, 30);
  const filings = assetType === 'stock' ? await recentFilings(symbol) : [];
  const asOf = new Date().toISOString();

  if (isConfigured('deepseek') && titles.length) {
    try {
      const llm = await llmScore(symbol, assetType, titles, filings);
      if (llm) return { symbol, assetType, engine: 'llm', provider: 'deepseek', asOf, headlines: titles, filings, ...llm };
    } catch (_) { /* fall through to heuristic */ }
  }

  const heur = classifyNews(titles, assetType);
  const impact = Math.max(0, Math.min(100, Math.round(Math.abs(heur.points) / 60 * 100)));
  return {
    symbol, assetType, engine: 'heuristic', provider: null, asOf, headlines: titles, filings,
    sentiment_bias: (heur.direction || 'neutral').toUpperCase(),
    market_impact_score: impact,
    catalysts: [],
    note: heur.dominant ? `dominant keyword signal: ${heur.dominant} (${heur.dominantDir})` : 'no directional keyword signal'
  };
}

module.exports = { newsCatalyst, detectAsset, dedupe, recentFilings, coerceJSON, newsTitles };
