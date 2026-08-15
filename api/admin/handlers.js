'use strict';
/**
 * admin/handlers.js — request handlers for the admin dashboard API.
 *
 * Routes (all under /api/admin, require demo auth token):
 *   GET  /api/admin/all            → entire dashboard payload (one round-trip)
 *   GET  /api/admin/<resource>     → profile | overview | alerts | sessions
 *                                     | modules | licenses | billing
 *                                     | notifications | security | downloads
 *   PATCH /api/admin/profile        → update whitelisted profile fields
 *
 * Auth: demo token via `Authorization: Bearer <tok>` or `?token=<tok>`.
 * Valid token = process.env.ADMIN_DEMO_TOKEN or the default below.
 * This is a DEMO gate — wire real session/JWT auth before production.
 *
 * All payloads carry meta.isDemo=true so the frontend labels data honestly.
 */
const store = require('./store');

const DEMO_TOKEN = process.env.ADMIN_DEMO_TOKEN || 'demo-admin-token';

const PUBLIC_RESOURCES = [
  'profile', 'overview', 'alerts', 'sessions', 'modules',
  'licenses', 'billing', 'notifications', 'security', 'downloads'
];

const PROFILE_FIELDS = ['displayName', 'email', 'timezone', 'primaryMarket', 'tradingStyle'];

function sendJSON(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

function isAuthed(req, url) {
  const auth = req.headers && req.headers['authorization'];
  let tok = null;
  if (auth && /^Bearer\s+/i.test(auth)) tok = auth.replace(/^Bearer\s+/i, '').trim();
  if (!tok) tok = url.searchParams.get('token');
  return tok === DEMO_TOKEN;
}

function withAuth(req, res, url, fn) {
  if (!isAuthed(req, url)) {
    return sendJSON(res, 401, { error: 'Unauthorized — admin token required (demo token: ADMIN_DEMO_TOKEN).' });
  }
  return fn();
}

function readBody(req, limit = 1e5) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', c => { body += c; if (body.length > limit) req.destroy(); });
    req.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch (e) { reject(new Error('invalid JSON body')); }
    });
    req.on('error', reject);
  });
}

function buildAdmin(req, res, url) {
  const seg = (url.pathname.replace(/^\/api\/admin\/?/, '').split('/')[0] || '').toLowerCase();

  // CORS preflight
  if (req.method === 'OPTIONS') { res.statusCode = 204; return res.end(); }

  if (req.method === 'GET') {
    return withAuth(req, res, url, () => {
      const data = store.load();
      if (seg === '' || seg === 'all') {
        return sendJSON(res, 200, data);
      }
      if (PUBLIC_RESOURCES.includes(seg)) {
        // Return the sub-object; if missing, 404 with error shape.
        if (data[seg] === undefined) {
          return sendJSON(res, 404, { error: 'unknown resource: ' + seg });
        }
        return sendJSON(res, 200, { ...data.meta, [seg]: data[seg] });
      }
      return sendJSON(res, 404, { error: 'unknown admin route: /api/admin/' + seg });
    });
  }

  if (req.method === 'PATCH' && seg === 'profile') {
    return withAuth(req, res, url, async () => {
      let patch;
      try { patch = await readBody(req); }
      catch (e) { return sendJSON(res, 400, { error: e.message }); }
      const data = store.load();
      const next = store.deepClone(data);
      let changed = false;
      PROFILE_FIELDS.forEach(f => {
        if (typeof patch[f] === 'string' && patch[f].length <= 200) {
          next.profile[f] = patch[f];
          changed = true;
        }
      });
      if (!changed) return sendJSON(res, 400, { error: 'no valid profile fields supplied' });
      const persisted = store.save(next);
      return sendJSON(res, 200, {
        ...next.meta,
        profile: next.profile,
        persisted: persisted, // false on read-only FS (e.g. Vercel serverless)
        warning: persisted ? undefined : 'changes not persisted (read-only environment) — in-memory only this session'
      });
    });
  }

  return sendJSON(res, 405, { error: 'method not allowed: ' + req.method });
}

module.exports = { buildAdmin, isAuthed, DEMO_TOKEN };
