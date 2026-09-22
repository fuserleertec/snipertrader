'use strict';
// scripts/recon_track.js — forward-return feedback loop for the Pre-Run Terminal.
// -----------------------------------------------------------------------------
// The pipeline has NEVER been validated out-of-sample. This closes that loop:
//
//   1. Snapshot today's live picks (stocks + confirmed crypto) with their entry
//      prices and a benchmark price (SPY for stocks, BTC for crypto) recorded at
//      the same moment.
//   2. For every prior candidate, fetch its current price and settle forward
//      returns at +1d / +5d / +20d once enough time has elapsed.
//   3. Compare each settled return against the matched benchmark.
//   4. Write the ledger (data/recon_history.json) + a dashboard report
//      (data/recon_track_report.json), then commit + push ONLY those two files.
//
// Honest design:
//   - Forward-only. No look-ahead. First run records a baseline; results accrue.
//   - Delisted / unfetchable symbols are recorded as -100%, NOT silently dropped
//     (fixes the survivorship bias in the underlying universe).
//   - Benchmark-matched: each candidate is judged against SPY/BTC over the same
//     calendar window, not in a vacuum.
//
// Usage:
//   node scripts/recon_track.js            # record + evaluate + commit + push
//   node scripts/recon_track.js --no-push  # record + evaluate, write files only
// -----------------------------------------------------------------------------

const https = require('https');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PUSH = !process.argv.includes('--no-push');
const PICK_URL = 'https://www.snipertrader.ai/api/recon/picks';
const UA = { 'User-Agent': 'Mozilla/5.0 (snipertrader.ai track loop)' };

const REPO = path.resolve(__dirname, '..');
const HISTORY = path.join(REPO, 'data', 'recon_history.json');
const REPORT = path.join(REPO, 'data', 'recon_track_report.json');
const HORIZONS = [1, 5, 20];

function getJSON(url, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: UA }, (res) => {
      if (res.statusCode !== 200) { res.resume(); return reject(new Error('HTTP ' + res.statusCode + ' ' + url)); }
      let d = ''; res.setEncoding('utf8');
      res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.setTimeout(timeoutMs, () => req.destroy(new Error('timeout ' + url)));
  });
}

function yahooLast(symbol) {
  return getJSON(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=1d`)
    .then((j) => {
      const r = j.chart && j.chart.result && j.chart.result[0];
      const q = r && r.indicators && r.indicators.quote && r.indicators.quote[0];
      const closes = (q && q.close || []).filter((v) => v != null);
      return closes.length ? closes[closes.length - 1] : null;
    });
}

function binanceLast(symbol) {
  return getJSON(`https://data-api.binance.vision/api/v3/klines?symbol=${encodeURIComponent(symbol)}&interval=1d&limit=2`)
    .then((raw) => (raw && raw.length ? +raw[raw.length - 1][4] : null));
}

function currentPrice(symbol, assetType) {
  return (assetType === 'crypto' ? binanceLast(symbol) : yahooLast(symbol)).catch(() => null);
}

function mapLimit(items, limit, fn) {
  return new Promise((resolve) => {
    const out = new Array(items.length);
    let i = 0;
    const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (i < items.length) { const idx = i++; out[idx] = await fn(items[idx], idx); }
    });
    Promise.all(workers).then(() => resolve(out));
  });
}

function round2(x) { return Math.round(Number(x) * 100) / 100; }
function round6(x) { return Math.round(Number(x) * 1e6) / 1e6; }

// Pull the live picks the terminal is actually showing, keeping only candidates
// that carry a decision (BUY/HOLD/SELL) + an entry price.
async function fetchCandidates() {
  const d = await getJSON(PICK_URL, 90000); // cold Vercel cache runs a fresh ~30-60s scan — give it headroom
  const out = [];
  for (const p of d.picks || []) {
    out.push({ symbol: p.symbol, assetType: 'stock', signal: (p.decision && p.decision.signal) || 'HOLD', entry: round6(p.close), conviction: round2(p.score || 0) });
  }
  for (const c of d.crypto || []) {
    if (c.decision) out.push({ symbol: c.symbol, assetType: 'crypto', signal: c.decision.signal || 'HOLD', entry: round6(c.price), conviction: round2(c.score || 0) });
  }
  return out;
}

async function loadHistory() {
  try { return JSON.parse(fs.readFileSync(HISTORY, 'utf8')); }
  catch (_) { return { v: 1, started: new Date().toISOString(), snapshots: [] }; }
}

function assetTypeOf(history, symbol) {
  for (const s of history.snapshots) for (const c of s.candidates) if (c.symbol === symbol) return c.assetType;
  return 'stock';
}

async function evaluate(history, now) {
  // current benchmark prices (one fetch each, at the same moment as candidate prices)
  const [curSPY, curBTC] = await Promise.all([yahooLast('SPY').catch(() => null), binanceLast('BTCUSDT').catch(() => null)]);

  // unique symbols across history -> current price (concurrency 8)
  const syms = [...new Set(history.snapshots.flatMap((s) => s.candidates.map((c) => c.symbol)))];
  const prices = await mapLimit(syms, 8, async (sym) => ({ sym, price: await currentPrice(sym, assetTypeOf(history, sym)) }));
  const price = {};
  for (const p of prices) price[p.sym] = p.price;

  for (const snap of history.snapshots) {
    const days = (now - Date.parse(snap.ts)) / 86400000;
    for (const c of snap.candidates) {
      const cur = price[c.symbol];
      const ret = cur != null ? cur / c.entry - 1 : -1; // delisted/unfetchable -> -100%
      const bench = c.assetType === 'stock' ? (curSPY != null && snap.bench.SPY ? curSPY / snap.bench.SPY - 1 : null) : (curBTC != null && snap.bench.BTC ? curBTC / snap.bench.BTC - 1 : null);
      if (!c.settled) c.settled = { d1: null, d5: null, d20: null };
      for (const h of HORIZONS) {
        const key = 'd' + h;
        if (days >= h && c.settled[key] == null) {
          c.settled[key] = { ret: round2(ret), bench: bench == null ? null : round2(bench), days: round2(days) };
        }
      }
    }
  }
  return { curSPY, curBTC };
}

function mkH() { return { n: 0, hits: 0, sumRet: 0, sumBench: 0 }; }
function mkSig() { return { tracked: 0, d1: mkH(), d5: mkH(), d20: mkH() }; }

function buildReport(history, now, benchNow) {
  const H = { d1: mkH(), d5: mkH(), d20: mkH() };
  const sig = { BUY: mkSig(), HOLD: mkSig(), SELL: mkSig() };
  let total = 0, active = 0;
  const rows = [];
  for (const snap of history.snapshots) {
    for (const c of snap.candidates) {
      total++;
      const sk = (c.signal === 'BUY' || c.signal === 'SELL') ? c.signal : 'HOLD';
      sig[sk].tracked++;
      let settled = false;
      for (const h of HORIZONS) {
        const s = c.settled && c.settled['d' + h];
        if (s) {
          settled = true;
          for (const agg of [H['d' + h], sig[sk]['d' + h]]) {
            agg.n++; agg.sumRet += s.ret; if (s.bench != null) agg.sumBench += s.bench; if (s.ret > 0) agg.hits++;
          }
        }
      }
      if (!(c.settled && c.settled.d20)) active++;
      if (settled || snap === history.snapshots[history.snapshots.length - 1]) {
        rows.push({ symbol: c.symbol, assetType: c.assetType, signal: c.signal, entry: c.entry, conviction: c.conviction, ts: snap.ts, settled: c.settled });
      }
    }
  }
  const finalize = (x) => ({
    n: x.n,
    hitRate: x.n ? round2(x.hits / x.n * 100) : null,
    avgReturn: x.n ? round2(x.sumRet / x.n * 100) : null,
    avgBench: x.sumBench && x.n ? round2(x.sumBench / x.n * 100) : null,
    avgExcess: x.sumBench && x.n ? round2((x.sumRet - x.sumBench) / x.n * 100) : (x.n ? round2(x.sumRet / x.n * 100) : null)
  });
  const horiz = {};
  for (const h of HORIZONS) horiz['d' + h] = finalize(H['d' + h]);
  const signals = {};
  for (const k of ['BUY', 'HOLD', 'SELL']) {
    signals[k] = { tracked: sig[k].tracked, d1: finalize(sig[k].d1), d5: finalize(sig[k].d5), d20: finalize(sig[k].d20) };
  }
  rows.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
  return {
    generatedAt: new Date(now).toISOString(),
    status: total === 0 ? 'no-picks' : (history.snapshots.length === 1 && H.d1.n === 0 ? 'baseline' : 'tracking'),
    snapshots: history.snapshots.length,
    candidatesTracked: total,
    active,
    benchmarks: { SPY: benchNow.curSPY == null ? null : round2(benchNow.curSPY), BTC: benchNow.curBTC == null ? null : round2(benchNow.curBTC) },
    horizons: horiz,
    signals,
    recent: rows.slice(0, 30)
  };
}

function gitPush() {
  execSync('git add data/recon_history.json data/recon_track_report.json', { cwd: REPO });
  let hasChanges = true;
  try { execSync('git diff --cached --quiet', { cwd: REPO }); hasChanges = false; } catch (_) { hasChanges = true; }
  if (!hasChanges) { console.log('no changes to commit'); return; }
  execSync('git commit -m "recon: track-record update ' + new Date().toISOString().slice(0, 10) + '"', { cwd: REPO, stdio: 'inherit' });
  execSync('git push origin main', { cwd: REPO, stdio: 'inherit' });
  console.log('pushed data/recon_history.json + data/recon_track_report.json');
}

async function main() {
  const now = Date.now();
  console.log('[' + new Date(now).toISOString() + '] recon_track: fetching live picks…');
  const candidates = await fetchCandidates();
  console.log('candidates this cycle: ' + candidates.length);

  const history = await loadHistory();
  const benchSPY = await yahooLast('SPY').catch(() => null);
  const benchBTC = await binanceLast('BTCUSDT').catch(() => null);

  history.snapshots.push({
    ts: new Date(now).toISOString(),
    bench: { SPY: benchSPY == null ? null : round2(benchSPY), BTC: benchBTC == null ? null : round2(benchBTC) },
    candidates: candidates.map((c) => ({ ...c, settled: { d1: null, d5: null, d20: null } }))
  });

  const benchNow = await evaluate(history, now);
  const report = buildReport(history, now, benchNow);

  fs.writeFileSync(HISTORY, JSON.stringify(history, null, 2));
  fs.writeFileSync(REPORT, JSON.stringify(report, null, 2));
  console.log('wrote data/recon_history.json (' + history.snapshots.length + ' snapshots) + data/recon_track_report.json');
  console.log('report: ' + JSON.stringify(report.horizons));

  if (PUSH) { try { gitPush(); } catch (e) { console.error('git push failed: ' + (e.message || e)); process.exitCode = 1; } }
  else console.log('--no-push: files written, not committed');
}

main().catch((e) => { console.error('recon_track error: ' + (e.stack || e)); process.exit(1); });
