'use strict';
// api/_lib/recon/positioning.js
// ---------------------------------------------------------------------------
// Crypto positioning — funding rate + open interest + long/short ratio — via
// Gate.io's public futures API (key-less, US-accessible).
//
// Binance futures (the natural source) is geo-blocked from the US deploy region
// (451 "restricted location") and Binance Vision only mirrors SPOT (fapi/* → 404).
// Gate.io's `/futures/usdt/*` endpoints return the same positioning data with
// no key: funding-rate history, daily open-interest + long/short ratio +
// liquidations. Full coverage of the 24-symbol universe.
//
// These are LEADING signals, unlike the lagging OHLCV leg:
//   - funding rate  : who pays whom. Negative = shorts paying longs (squeeze
//     fuel). Extreme positive = overcrowded longs (mean-reversion / dump risk).
//   - open interest : OI building while price is flat = new positions quietly
//     accumulating (pre-run). OI falling = unwinding.
//   - long/short    : crowded short = squeeze potential; crowded long = risk.
// ---------------------------------------------------------------------------

const https = require('https');

function getJSON(url, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0 (snipertrader.ai positioning)' } }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode)); }
      let d = ''; res.setEncoding('utf8');
      res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout')));
  });
}

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const round6 = (x) => Math.round(Number(x) * 1e6) / 1e6;

// BTCUSDT -> BTC_USDT (Gate.io USDT-margined contract id)
function gateSymbol(symbol) {
  return String(symbol).replace(/USDT$/, '_USDT');
}

// Fetch funding + OI + long/short for one symbol and return an honest positioning
// snapshot + a bounded, transparent score delta (signed, clamped to ±15).
async function positioningFor(symbol) {
  const g = gateSymbol(symbol);
  const [fr, stats] = await Promise.all([
    getJSON(`https://api.gateio.ws/api/v4/futures/usdt/funding_rate?contract=${encodeURIComponent(g)}&limit=24`),
    getJSON(`https://api.gateio.ws/api/v4/futures/usdt/contract_stats?contract=${encodeURIComponent(g)}&interval=1d&limit=7`)
  ]);

  // funding: newest-first; rates[0] = latest. Average over the window = the trend.
  const rates = (fr || []).map((x) => +x.r).filter((v) => Number.isFinite(v));
  const curFunding = rates[0] != null ? rates[0] : 0;
  const avgFunding = rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : 0;

  // OI + long/short: sort ascending by time; cur = latest, prev = ~3 days earlier.
  const ois = (stats || [])
    .map((s) => ({ t: +s.time, oi: +s.open_interest, lsr: +s.lsr_account }))
    .filter((s) => s.oi > 0)
    .sort((a, b) => a.t - b.t);
  const cur = ois[ois.length - 1];
  const prev = ois.length >= 4 ? ois[ois.length - 4] : ois[0];
  const oiChangePct = cur && prev && prev.oi ? ((cur.oi - prev.oi) / prev.oi) * 100 : null;
  const lsrAccount = cur ? cur.lsr : null;

  // honest, bounded delta
  let delta = 0;
  const flags = [];
  if (avgFunding < -0.0001) { delta += 8; flags.push('funding-negative'); }        // shorts paying longs
  else if (avgFunding < 0) { delta += 4; flags.push('funding-mild-negative'); }
  else if (avgFunding > 0.0005) { delta -= 8; flags.push('funding-overheat'); }     // overcrowded longs
  if (oiChangePct != null) {
    if (oiChangePct > 5) { delta += 7; flags.push('oi-building'); }
    else if (oiChangePct < -5) { delta -= 5; flags.push('oi-unwinding'); }
  }
  if (lsrAccount != null) {
    if (lsrAccount < 0.6) { delta += 5; flags.push('crowded-short'); }
    else if (lsrAccount > 2.0) { delta -= 5; flags.push('crowded-long'); }
  }
  delta = Math.round(clamp(delta, -15, 15));

  return {
    source: 'gate.io',
    fundingRate: round6(curFunding),
    fundingAvg: round6(avgFunding),
    oi: cur ? cur.oi : null,
    oiChangePct: oiChangePct == null ? null : Math.round(oiChangePct * 100) / 100,
    lsrAccount: lsrAccount == null ? null : Math.round(lsrAccount * 100) / 100,
    delta,
    flags,
    note: 'funding ' + (curFunding * 100).toFixed(3) + '% · OI ' + (oiChangePct == null ? 'n/a' : (oiChangePct > 0 ? '+' : '') + oiChangePct.toFixed(1) + '%') + ' · L/S ' + (lsrAccount == null ? 'n/a' : lsrAccount.toFixed(2))
  };
}

module.exports = { positioningFor, gateSymbol };
