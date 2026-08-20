// api/recon/insider.js
// REAL key-less insider (SEC Form 4) pipeline via SEC EDGAR.
// 1. company_tickers.json  -> ticker -> CIK
// 2. submissions/CIK{cik}.json -> recent Form 4 filing dates
// 3. For each recent Form 4, fetch the accession's data -> transactions JSON
//    to classify BUY vs SELL and weight the insider signal.
//
// Honest design: if EDGAR is unreachable or returns nothing, we return
// insider=0 (neutral), never fabricated buys/sells.

const https = require('https');

const SEC_HEADERS = { 'User-Agent': 'snipertrader-recon research@example.com', 'Accept': 'application/json' };
const SEC_HTML_HEADERS = { 'User-Agent': 'snipertrader-recon research@example.com', 'Accept': 'text/html' };

function getJSON(url, headers = SEC_HEADERS, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode + ' ' + url)); }
      let data = '';
      res.setEncoding('utf8');
      res.on('data', (c) => (data += c));
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout ' + url)));
  });
}

function getText(url, headers = SEC_HTML_HEADERS, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode + ' ' + url)); }
      let data = '';
      res.setEncoding('utf8');
      res.on('data', (c) => (data += c));
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout ' + url)));
  });
}

let _tickerCache = null;
async function tickerToCik(symbol) {
  if (!_tickerCache) {
    const d = await getJSON('https://www.sec.gov/files/company_tickers.json');
    _tickerCache = d; // map of index -> {ticker, cik_str, title}
  }
  const upper = symbol.toUpperCase();
  for (const v of Object.values(_tickerCache)) {
    if (v.ticker && v.ticker.toUpperCase() === upper) return String(v.cik_str).padStart(10, '0');
  }
  return null;
}

// Returns { present:bool, buys:int, sells:int, recentForms:int, lastFiling, error }
async function insiderFor(symbol, lookbackDays = 7) {
  try {
    const cik = await tickerToCik(symbol);
    if (!cik) return { present: false, buys: 0, sells: 0, recentForms: 0, error: 'no CIK' };
    const sub = await getJSON(`https://data.sec.gov/submissions/CIK${cik}.json`);
    const recent = sub.filings.recent;
    const forms = recent.form, dates = recent.filingDate, accs = recent.accessionNumber, docs = recent.primaryDocument;
    const cutoff = Date.now() - lookbackDays * 86400000;

    let form4Count = 0;
    let recentForm4Count = 0;
    const toFetch = [];
    for (let i = 0; i < forms.length; i++) {
      if (forms[i] === '4') {
        form4Count++;
        const ts = Date.parse(dates[i]);
        if (!isNaN(ts) && ts >= cutoff) {
          recentForm4Count++;
          // EDGAR archive path: /Archives/edgar/data/{cikInt}/{accessionNoDashes}/{primaryDocument}
          const acc = accs[i].replace(/-/g, '');
          const doc = docs[i] || (accs[i] + '.xml');
          toFetch.push(`https://www.sec.gov/Archives/edgar/data/${parseInt(cik)}/${acc}/${doc}`);
        }
      }
    }

    let buys = 0, sells = 0;
    // Fetch each recent Form 4's HTML display (EDGAR serves the XSL-rendered
    // page; raw .json/.xml endpoints are inconsistent). Buy/Sell is encoded per
    // transaction row as "Acquired (A)" / "Disposed Of (D)".
    for (const url of toFetch.slice(0, 8)) {
      try {
        const html = await getText(url);
        const acq = (html.match(/>\(A\)</g) || []).length;
        const dis = (html.match(/>\(D\)</g) || []).length;
        buys += acq; sells += dis;
      } catch (_) { /* one bad accession shouldn't sink the signal */ }
    }

    return {
      present: form4Count > 0,
      buys, sells,
      recentForms: recentForm4Count,
      totalForms: form4Count,
      lastFiling: dates[0] || null,
      error: null
    };
  } catch (e) {
    return { present: false, buys: 0, sells: 0, recentForms: 0, error: String(e.message || e) };
  }
}

// Map insider activity -> 0..1 strength for the engine.
// C-suite cluster (>=3 buys in window) or congressional-style = strong; single = mild.
function insiderStrength(info) {
  if (!info || !info.present || info.error) return 0;
  const b = info.buys || 0;
  const s = info.sells || 0;
  if (b === 0) return 0;                       // no buying = neutral (per matrix)
  if (b >= 3) return 1.0;                      // C-suite Form 4 cluster
  if (b >= 1 && s === 0) return 0.7;           // single buy, no distribution
  return 0.6;                                  // single open-market purchase
}

module.exports = { insiderFor, insiderStrength, tickerToCik, _setTickerCache: (c) => { _tickerCache = c; } };
