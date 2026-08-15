'use strict';
/* TEMPORARY diagnostic endpoint — DO NOT keep in production.
 * Exposes raw Alpaca bars response to debug the feed=iex "undefined close" issue.
 * Remove after investigation. */
const https = require('https');

function rawAlpaca({ symbol, timeframe = '1Day', limit = 120, feed = 'iex' }) {
  return new Promise((resolve) => {
    const key = process.env.ALPACA_API_KEY, sec = process.env.ALPACA_SECRET_KEY;
    if (!key || !sec) return resolve({ status: null, bodyLen: 0, raw: null, rawText: '', error: 'no Alpaca creds on env' });
    const sym = String(symbol || '').toUpperCase();
    const TF_MS = { '1Day': 86400e3 };
    const lookback = (TF_MS[timeframe] || 86400e3) * limit * 3;
    const start = new Date(Date.now() - lookback).toISOString();
    const q = `symbols=${encodeURIComponent(sym)}&timeframe=${timeframe}&limit=${limit}&adjustment=split&feed=${feed}&start=${encodeURIComponent(start)}`;
    const req = https.request({
      hostname: 'data.alpaca.markets',
      path: `/v2/stocks/bars?${q}`,
      method: 'GET',
      headers: { 'Apca-Api-Key-Id': key, 'Apca-Api-Secret-Key': sec, 'Accept': 'application/json' }
    }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        let parsed = null;
        try { parsed = JSON.parse(body); } catch (_) {}
        resolve({ status: res.statusCode, bodyLen: body.length, raw: parsed, rawText: body.slice(0, 2000) });
      });
    });
    req.on('error', e => resolve({ error: 'request failed: ' + e.message }));
    req.setTimeout(15000, () => req.destroy(new Error('Alpaca timeout')));
    req.end();
  });
}

function buildHandler(feed) {
  return function (req, res) {
    let body = '';
    req.on('data', c => { body += c; if (body.length > 1e4) req.destroy(); });
    req.on('end', async () => {
      let payload = {};
      try { payload = JSON.parse(body || '{}'); } catch (_) {}
      const symbol = String(payload.symbol || 'AAPL');
      const r = await rawAlpaca({ symbol, feed });
      // summarize the bar field shapes if present
      let sample = null, badClose = 0, total = 0;
      if (r.raw && r.raw.bars && r.raw.bars[symbol]) {
        const arr = r.raw.bars[symbol];
        total = arr.length;
        sample = arr.slice(0, 2).map(b => ({ keys: Object.keys(b), t: b.t, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v }));
        badClose = arr.filter(b => b.c === undefined || b.c === null || Number.isNaN(+b.c)).length;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ feed, symbol, status: r.status, error: r.error || null, bodyLen: r.bodyLen,
        totalBars: total, badCloseCount: badClose, sample, rawText: r.rawText }, null, 1));
    });
  };
}

// both feeds exposed for comparison
module.exports = { buildHandler };
