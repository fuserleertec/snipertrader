// api/recon/congressional.js
// Congressional STOCK Act disclosure feed.
//
// HONEST DESIGN: there is NO working key-less congressional API (house/senate
// stockwatch.ai do not resolve; Senate EFD requires 403-forbidden POST). The
// only reliable programmatic source is Quiver Quantitative (requires a key).
//
// So this module is KEY-GATED: if QUIVER_API_KEY is present, it fetches real
// House/Senate recent trades. If not, it returns { available:false } and the
// engine treats congressional as a NEUTRAL 0 contribution — it NEVER invents
// rows, never returns fabricated buys, and never silently reports "no activity"
// as if it had actually checked.

const https = require('https');

function qget(path, apiKey) {
  return new Promise((resolve, reject) => {
    const url = `https://api.quiverquant.com/beta/${path}`;
    const req = https.get(url, { headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' } }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let d = '';
      res.setEncoding('utf8');
      res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => req.destroy(new Error('timeout')));
  });
}

// Returns { available, source, trades:[{ticker, senator, chamber, date, type, amount}], error }
async function congressionalRecent(days = 7) {
  const key = process.env.QUIVER_API_KEY;
  if (!key) {
    return { available: false, source: null, trades: [], error: 'no_api_key',
             note: 'Congressional STOCK Act feed requires a Quiver API key (no key-less source exists). Insider signal uses SEC Form 4 only.' };
  }
  try {
    const [house, senate] = await Promise.all([
      qget('live/congressional?minDate=' + isoDaysAgo(days), key),
      qget('live/senate?minDate=' + isoDaysAgo(days), key)
    ]);
    const trades = [];
    (house || []).forEach((r) => trades.push({ ticker: r.Ticker, rep: r.Representative || r.TransactionDate, chamber: 'HOUSE', date: r.TransactionDate, type: r.Transaction || r.Type, amount: r.Amount }));
    (senate || []).forEach((r) => trades.push({ ticker: r.Ticker, rep: r.Senator || r.TransactionDate, chamber: 'SENATE', date: r.TransactionDate, type: r.Transaction || r.Type, amount: r.Amount }));
    return { available: true, source: 'quiver', trades, error: null };
  } catch (e) {
    return { available: false, source: null, trades: [], error: String(e.message || e), note: 'Congressional fetch failed.' };
  }
}

function isoDaysAgo(n) {
  const d = new Date(Date.now() - n * 86400000);
  return d.toISOString().slice(0, 10);
}

// Congressional contribution to the insider sub-score (0..1). House/Senate buy
// within window counts as strong political interest (treated like a C-suite cluster).
function congressionalStrength(congressional, ticker) {
  if (!congressional || !congressional.available) return 0;
  const tk = (ticker || '').toUpperCase();
  const forTicker = (congressional.trades || []).filter((t) => (t.ticker || '').toUpperCase() === tk);
  if (!forTicker.length) return 0;
  const buys = forTicker.filter((t) => /buy|purchase/i.test(t.type || '')).length;
  if (buys >= 2) return 1.0;     // multi-member cluster
  if (buys >= 1) return 0.75;    // single member purchase
  return 0.5;
}

module.exports = { congressionalRecent, congressionalStrength };
