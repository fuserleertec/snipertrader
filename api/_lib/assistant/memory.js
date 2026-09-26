'use strict';
/** api/_lib/assistant/memory.js — Postgres-backed session + message memory. */
const crypto = require('crypto');
const db = require('../traderedge/db');

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function ipHash(req) {
  try {
    const fwd = String((req.headers && req.headers['x-forwarded-for']) || '');
    const ip = (fwd.split(',')[0] || '').trim()
      || (req.socket && req.socket.remoteAddress)
      || 'unknown';
    return crypto.createHash('sha256').update(ip).digest('hex').slice(0, 32);
  } catch (_) { return null; }
}

/** Validates a client-supplied id, else mints a fresh one. Returns the id used. */
async function ensureSession(sessionId, req) {
  const sid = (typeof sessionId === 'string' && UUID_RE.test(sessionId))
    ? sessionId.toLowerCase()
    : crypto.randomUUID();
  await db.query(
    `insert into assistant_sessions (id, ip_hash)
     values ($1, $2)
     on conflict (id) do update set last_seen_at = now()`,
    [sid, ipHash(req)]
  );
  return sid;
}

async function loadHistory(sessionId, limit = 8) {
  const r = await db.query(
    `select role, content from assistant_messages
     where session_id = $1 order by created_at desc limit $2`,
    [sessionId, limit]
  );
  return r.rows.slice().reverse().map(x => ({ role: x.role, content: x.content }));
}

async function saveMessage(sessionId, role, content, extra = {}) {
  const r = await db.query(
    `insert into assistant_messages
       (session_id, role, content, sources, retrieved_chunk_ids, latency_ms)
     values ($1, $2, $3, $4, $5, $6)
     returning id`,
    [
      sessionId, role, content,
      extra.sources ? JSON.stringify(extra.sources) : null,
      extra.chunkIds || null,
      extra.latencyMs != null ? extra.latencyMs : null
    ]
  );
  return r.rows[0].id;
}

async function saveFeedback(messageId, rating, reason, comment) {
  await db.query(
    `insert into assistant_feedback (message_id, rating, reason, comment)
     values ($1, $2, $3, $4)`,
    [messageId, rating, reason || null, comment || null]
  );
}

module.exports = { ensureSession, loadHistory, saveMessage, saveFeedback, ipHash };
