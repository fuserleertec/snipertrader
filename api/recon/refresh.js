// api/recon/refresh.js
// GET /api/recon/refresh  (invoked by Vercel Cron @ 13:00 & 22:00 UTC, and by
// GitHub Actions fallback). Recomputes the live recon and writes a static cache
// to /tmp (serverless read-only FS elsewhere) + returns the payload. The static
// page loads /api/recon/picks which reads this cache when warm.
//
// NOTE: A serverless function CANNOT write back into the git repo at runtime, so
// we persist the cache to /tmp (the only writable path) and also optionally push
// to a git branch from the GitHub Actions runner (which CAN write). See
// .github/workflows/recon.yml for the runner-side commit of data/recon.json.

const { run } = require('./picks');
const fs = require('fs');
const path = require('path');

const CACHE_FILE = '/tmp/recon_cache.json';
const ROOT = path.join(__dirname, '..', '..');
const DATA_PATH = path.join(ROOT, 'data', 'recon.json');

module.exports = async (req, res) => {
  const token = req.query && req.query.token;
  const expected = process.env.RECON_CRON_TOKEN || 'local-dev';
  if (token !== expected && process.env.NODE_ENV === 'production') {
    return res.status(401).json({ error: 'unauthorized' });
  }
  try {
    const payload = await run(true);
    // Persist to /tmp (always) AND the committed repo file (works on local dev /
    // GH Actions; best-effort on Vercel where the FS is read-only). Mirrors
    // prop/store.js so /api/recon/picks has a cold-start fallback.
    try { fs.writeFileSync(CACHE_FILE, JSON.stringify(payload)); } catch (_) {}
    try { fs.writeFileSync(DATA_PATH, JSON.stringify(payload, null, 2)); } catch (_) {}
    res.json({ ok: true, picks: payload.picks.length, generatedAt: payload.generatedAt });
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
