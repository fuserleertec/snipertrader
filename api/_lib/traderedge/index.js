'use strict';
/**
 * api/_lib/traderedge/index.js — ATPE engine facade + HTTP handlers.
 * Exposes ingest / graph / intervene / outcome as (req, res) handlers for the
 * `api/traderedge/[action].js` dynamic route. The existing `preflight` action
 * stays byte-compatible by delegating to `_core.buildPreflight`.
 */
const stream = require('./stream');
const graphMod = require('./graph');
const policy = require('./policy');

function respond(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

function readBody(req, maxBytes = 1e5) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', c => { body += c; if (body.length > maxBytes) reject(new Error('payload too large')); });
    req.on('end', () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch (e) { reject(new Error('invalid JSON')); }
    });
    req.on('error', reject);
  });
}

// POST /api/traderedge/ingest — append an event to the stream
async function ingest(req, res) {
  let body;
  try { body = await readBody(req); } catch (e) { return respond(res, 400, { error: e.message }); }
  try {
    const ev = await stream.ingest(body);
    respond(res, 200, { ok: true, eventId: ev.event_id, ts: ev.ts });
  } catch (e) {
    respond(res, 500, { error: 'stream ingest failed', detail: e.message });
  }
}

// GET /api/traderedge/graph — current posteriors + recent events
async function graphHandler(req, res) {
  let traderId = 'local-trader';
  try {
    const url = new URL(req.url, 'http://localhost');
    traderId = url.searchParams.get('traderId') || 'local-trader';
  } catch (_) {}
  try {
    const [posteriors, events] = await Promise.all([
      graphMod.getPosteriors(),
      stream.list(traderId, 25)
    ]);
    respond(res, 200, {
      ok: true,
      posteriors,
      recentEvents: events,
      honest: 'association edges only — no causal claims yet (see blueprint §6, §11)'
    });
  } catch (e) {
    respond(res, 500, { error: 'graph read failed', detail: e.message });
  }
}

// POST /api/traderedge/intervene — fusion-gated, graduated intervention
async function intervene(req, res) {
  let body;
  try { body = await readBody(req); } catch (e) { return respond(res, 400, { error: e.message }); }
  try {
    const out = await policy.intervene(body);
    // log the intervention event to the stream (closed loop)
    if (out.level > 0) {
      await stream.ingest({
        type: 'intervention', source: 'platform',
        traderId: body.traderId, payload: {
          interventionId: out.interventionId, level: out.level,
          action: out.action, evidence: out.evidence
        }
      }).catch(() => {});
    }
    respond(res, 200, { ok: true, ...out });
  } catch (e) {
    respond(res, 500, { error: 'intervention failed', detail: e.message });
  }
}

// POST /api/traderedge/outcome — log result + update posteriors (closes loop)
async function outcome(req, res) {
  let body;
  try { body = await readBody(req); } catch (e) { return respond(res, 400, { error: e.message }); }
  try {
    const result = await graphMod.recordOutcome(body);
    await stream.ingest({
      type: 'outcome', source: body.source || 'self-report',
      traderId: body.traderId,
      payload: { win: !!body.win, state: body.state, regime: body.regime, pnl: body.pnl, impulsive: !!body.impulsive }
    }).catch(() => {});
    // if an intervention preceded this outcome, record the trader's response
    if (body.interventionId && body.decision) {
      await policy.respond(body.interventionId, body.decision, body.note).catch(() => {});
    }
    respond(res, 200, { ok: true, ...result });
  } catch (e) {
    respond(res, 500, { error: 'outcome record failed', detail: e.message });
  }
}

// POST /api/traderedge/override — explicit override becomes labeled training data
async function override(req, res) {
  let body;
  try { body = await readBody(req); } catch (e) { return respond(res, 400, { error: e.message }); }
  try {
    await stream.ingest({
      type: 'override', source: 'platform', traderId: body.traderId,
      payload: { interventionId: body.interventionId, note: body.note, at: new Date().toISOString() }
    });
    if (body.interventionId) await policy.respond(body.interventionId, 'override', body.note).catch(() => {});
    respond(res, 200, { ok: true });
  } catch (e) {
    respond(res, 500, { error: 'override failed', detail: e.message });
  }
}

module.exports = { ingest, graph: graphHandler, intervene, outcome, override, readBody, respond, stream, graphMod, policy };
