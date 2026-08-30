'use strict';
/**
 * prop/crawler.js — the autonomous daily crawler for Prop-Firm Intelligence.
 *
 * For each firm: fetch its public page(s) (zero-dep https, browser UA), strip
 * the HTML to text, and ask DeepSeek/Kimi (via _ai_providers) to extract the
 * published terms into a strict schema. Values the page does NOT state are left
 * null (never guessed; 0 is never accepted as a placeholder). Extracted records
 * are stamped `verified:false` + `confidence:'crawled'` + `last_refreshed`;
 * failures keep the prior seed values with `verified:false`.
 *
 * NOTE on bot-protection: some firms (e.g. Apex, E8) return 403 to a plain GET.
 * Those rows stay `verified:false` until a Firecrawl key or a browser-based
 * fetcher is configured — surfaced honestly in the row's `data_note`.
 */
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

// Zero-dependency .env loader (local dev only; Vercel injects real env vars).
// crawler.js requires _ai_providers directly (not via _core.js), so it loads
// api/.env itself. Does not overwrite existing env vars.
(function loadEnv() {
  try {
    const p = path.join(__dirname, '..', '..', '.env');
    if (!fs.existsSync(p)) return;
    fs.readFileSync(p, 'utf8').split(/\r?\n/).forEach((line) => {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
      if (!m) return;
      const k = m[1], v = m[2].replace(/^["']|["']$/g, '');
      if (process.env[k] === undefined) process.env[k] = v;
    });
  } catch (_) {}
})();

const { aiChat, isConfigured } = require('../../_ai_providers');

const UA = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'en-US,en;q=0.9'
};
const MAX_HTML = 5_000_000;
const MAX_TEXT = 20000;
// Homepage + a bounded probe of likely sub-pages (pricing/FAQ hold the terms).
const PROBE_PATHS = ['/en/faq', '/en/pricing', '/faq', '/pricing', '/en/programs', '/programs'];
const MAX_PAGES = 4;

/** Fetch a URL, following up to 4 redirects. Always resolves (never throws). */
function fetchHtml(url, redirects = 0) {
  return new Promise((resolve) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.get(url, { headers: UA }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location && redirects < 4) {
        res.resume();
        let next;
        try { next = new URL(res.headers.location, url).toString(); } catch (_) { next = null; }
        return resolve(next ? fetchHtml(next, redirects + 1) : { ok: false, status: res.statusCode, error: 'bad redirect' });
      }
      if (res.statusCode !== 200) { res.resume(); return resolve({ ok: false, status: res.statusCode, error: 'HTTP ' + res.statusCode }); }
      let d = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { if (d.length < MAX_HTML) d += c; });
      res.on('end', () => resolve({ ok: true, status: 200, html: d }));
    });
    req.on('error', (e) => resolve({ ok: false, status: 0, error: e.message }));
    req.setTimeout(25000, () => { req.destroy(); resolve({ ok: false, status: 0, error: 'timeout' }); });
  });
}

/** Strip scripts/styles/tags and collapse whitespace to a compact text block. */
function htmlToText(html) {
  if (!html) return '';
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&euro;/gi, '€')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Fetch the homepage plus up to MAX_PAGES-1 probe sub-pages; concatenate the
 * text of every page that returns 200. Returns { ok, status, text, pages }.
 */
async function fetchFirmText(firm) {
  const base = firm.website;
  const candidates = [base];
  for (const p of PROBE_PATHS) {
    if (candidates.length >= MAX_PAGES) break;
    try {
      const u = new URL(p, base).toString();
      if (u !== base && !candidates.includes(u)) candidates.push(u);
    } catch (_) {}
  }
  const pages = [];
  let firstStatus = null;
  let text = '';
  for (const u of candidates) {
    const r = await fetchHtml(u);
    if (firstStatus == null) firstStatus = r.status;
    if (r.ok && r.html) {
      const t = htmlToText(r.html);
      if (t) {
        pages.push(u);
        text = (text + '\n\n--- ' + u + ' ---\n\n' + t).slice(0, MAX_TEXT);
      }
    }
    if (text.length >= MAX_TEXT) break;
  }
  return { ok: pages.length > 0, status: firstStatus, text, pages };
}

const SCHEMA_HINT = `Return ONLY one valid JSON object (no markdown fences, no prose). Use null for anything the page does not state — never use 0 as a placeholder for missing data. Keys and types:
{
  "payout_split_trader_pct": <number 0-100 — the DEFAULT/base trader profit share (e.g. 80 for "80/20"), or null>,
  "payout_split_max_trader_pct": <number 0-100 — the MAXIMUM achievable trader share (e.g. 90 for "up to 90/10"), or null>,
  "payout_frequency": <"on-demand" | "bi-weekly" | "weekly" | "monthly" | null>,
  "payout_speed_days": <string like "1-2 days" | "24h" | "on-demand" | null>,
  "model": <"1-step" | "2-step" | "instant" | "multi-model" | null>,
  "profit_target_phase1_pct": <number or null>,
  "profit_target_phase2_pct": <number or null>,
  "max_drawdown_pct": <number or null>,
  "max_drawdown_type": <"static" | "trailing" | null>,
  "daily_drawdown_pct": <number or null>,
  "eval_fee_min_usd": <number — LOWEST entry fee in USD, or null>,
  "account_size_min": <number — smallest account size in USD, or null>,
  "account_size_max": <number — largest account size in USD, or null>,
  "active_deal_discount_pct": <number 0-100 — a CURRENTLY advertised discount/coupon/sale percentage, or null if none is stated>,
  "news_trading_allowed": <true | false | null>,
  "ea_trading_allowed": <true | false | null>,
  "weekend_holding_allowed": <true | false | null>,
  "scaling_enabled": <true | false | null>,
  "refund_fee": <true | false | null>
}`;

/** Tolerant JSON parse: strips markdown fences and leading/trailing prose. */
function parseJSON(s) {
  if (!s) return null;
  let t = String(s).trim();
  t = t.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  const first = t.indexOf('{');
  const last = t.lastIndexOf('}');
  if (first === -1 || last === -1) return null;
  t = t.slice(first, last + 1);
  try { return JSON.parse(t); } catch (_) { return null; }
}

function num(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }
// Positive-only number: 0 / negative are treated as "not stated" → null.
function posNum(v) { const n = num(v); return (n == null || n <= 0) ? null : n; }
function bool(v) { if (v === true || v === 'true') return true; if (v === false || v === 'false') return false; return null; }

/** Map raw LLM output onto the canonical firm record, preserving prior values. */
function normalize(firm, raw) {
  const f = JSON.parse(JSON.stringify(firm)); // deep copy, keep unknown fields
  const ps = f.payout_split || {};
  if (raw.payout_split_trader_pct != null || raw.payout_split_max_trader_pct != null) {
    let trader = posNum(raw.payout_split_trader_pct) ?? ps.trader ?? null;
    let maxTrader = posNum(raw.payout_split_max_trader_pct) ?? ps.max_trader ?? null;
    if (trader != null && maxTrader != null && maxTrader < trader) maxTrader = null; // incoherent
    f.payout_split = { trader, max_trader: maxTrader };
  }
  if (raw.payout_frequency != null) f.payout_frequency = raw.payout_frequency;
  if (raw.payout_speed_days != null) f.payout_speed = { label: raw.payout_speed_days, estimated: false };
  if (raw.model != null) f.model = raw.model;
  if (raw.profit_target_phase1_pct != null || raw.profit_target_phase2_pct != null) {
    const pt = f.profit_target || {};
    f.profit_target = {
      phase1: posNum(raw.profit_target_phase1_pct) ?? pt.phase1 ?? null,
      phase2: posNum(raw.profit_target_phase2_pct) ?? pt.phase2 ?? null
    };
  }
  if (raw.max_drawdown_pct != null || raw.max_drawdown_type != null || raw.daily_drawdown_pct != null) {
    const dd = f.max_drawdown || {};
    f.max_drawdown = {
      value: posNum(raw.max_drawdown_pct) ?? dd.value ?? null,
      type: raw.max_drawdown_type || dd.type || null,
      daily: posNum(raw.daily_drawdown_pct) ?? dd.daily ?? null
    };
  }
  if (raw.eval_fee_min_usd != null) f.eval_fee = { ...(f.eval_fee || {}), min_usd: posNum(raw.eval_fee_min_usd) };
  if (raw.account_size_min != null || raw.account_size_max != null) {
    f.account_sizes = {
      min: posNum(raw.account_size_min) ?? (f.account_sizes && f.account_sizes.min) ?? null,
      max: posNum(raw.account_size_max) ?? (f.account_sizes && f.account_sizes.max) ?? null
    };
  }
  // Deals: only accept a plausible discount in (0, 90]; always flagged unverified
  // (coupon codes require manual confirmation — never presented as "verified").
  if (raw.active_deal_discount_pct != null) {
    const d = num(raw.active_deal_discount_pct);
    if (d != null && d > 0 && d <= 90) {
      f.deal = { ...(f.deal || {}), active: true, discount_pct: d, verified: false };
    }
  }
  if (raw.news_trading_allowed != null || raw.ea_trading_allowed != null || raw.weekend_holding_allowed != null) {
    f.trading_styles = {
      ...(f.trading_styles || {}),
      news: bool(raw.news_trading_allowed),
      eas: bool(raw.ea_trading_allowed),
      weekend: bool(raw.weekend_holding_allowed)
    };
  }
  if (raw.scaling_enabled != null) f.scaling = { ...(f.scaling || {}), enabled: bool(raw.scaling_enabled) };
  if (raw.refund_fee != null) f.refund_fee = bool(raw.refund_fee);
  return f;
}

/**
 * Extract one firm's live terms. Resolves with `{ ok, firm?, status, error?, source? }`.
 * `firm` is the updated record (only on success); failures keep the caller's copy.
 */
async function extractFirm(firm) {
  const fetched = await fetchFirmText(firm);
  if (!fetched.ok || !fetched.text) {
    return {
      ok: false,
      status: fetched.status,
      error: 'no usable page text (HTTP ' + fetched.status + ')',
      firm: null,
      botBlocked: fetched.status === 403 || fetched.status === 0
    };
  }
  const provider = isConfigured('deepseek') ? 'deepseek' : (isConfigured('kimi') ? 'kimi' : null);
  if (!provider) {
    return { ok: false, status: fetched.status, error: 'no AI key configured (DEEPSEEK_API_KEY / KIMI_API_KEY) — kept seed values', firm: null };
  }
  try {
    const r = await aiChat({
      provider,
      messages: [
        { role: 'system', content: 'You are a precise financial-data extraction engine. Extract proprietary-trading-firm terms from the page text. ' + SCHEMA_HINT },
        { role: 'user', content: 'Firm: ' + firm.name + ' (' + firm.website + ')\n\nPAGE TEXT:\n' + fetched.text }
      ],
      options: { temperature: 0, maxTokens: 1600 }
    });
    const parsed = parseJSON(r.content);
    if (!parsed || typeof parsed !== 'object') {
      return { ok: false, status: fetched.status, error: 'unparseable model output', firm: null, source: provider };
    }
    const updated = normalize(firm, parsed);
    // LLM extraction is UNVALIDATED — never auto-stamp verified:true. A row
    // becomes verified:true only after human/cross-check review (see CRAWLED badge).
    updated.verified = false;
    updated.confidence = 'crawled';
    updated.last_refreshed = new Date().toISOString();
    updated.source_page = fetched.pages[0] || firm.website;
    updated.data_note = 'Extracted by LLM parser from ' + fetched.pages.join(', ');
    return { ok: true, status: fetched.status, firm: updated, source: provider };
  } catch (e) {
    return { ok: false, status: fetched.status, error: 'extract error: ' + (e.message || e), firm: null, source: provider };
  }
}

/**
 * Refresh every firm in the store sequentially (a 14-firm list doesn't need
 * concurrency). Returns a summary + the merged dataset.
 */
async function refreshAll(store, { onProgress } = {}) {
  const data = store.load();
  const firms = data.firms || [];
  const results = [];
  let updated = 0;
  let failed = 0;
  for (let i = 0; i < firms.length; i++) {
    const firm = firms[i];
    const r = await extractFirm(firm);
    results.push({ id: firm.id, name: firm.name, ok: r.ok, status: r.status, error: r.error || null });
    if (r.ok && r.firm) { firms[i] = r.firm; updated++; }
    else failed++;
    if (onProgress) onProgress(i + 1, firms.length, firm.id, r.ok);
  }
  data.firms = firms;
  data.meta = data.meta || {};
  data.meta.last_refreshed = new Date().toISOString();
  data.meta.refreshed_count = updated;
  data.meta.failed_count = failed;
  data.meta.refresh_source = updated > 0 ? 'llm-crawl' : 'seed';
  return { data, summary: { updated, failed, results } };
}

module.exports = { fetchHtml, htmlToText, fetchFirmText, extractFirm, refreshAll, normalize, parseJSON, UA };
