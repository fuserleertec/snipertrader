'use strict';
/**
 * api/_lib/traderedge/stream.js — Layer 1: append-only temporal event stream.
 *
 * Events are immutable rows in `traderedge_events`. Each carries honest
 * provenance (`source`) and a `fingerprint_version` so Layer 5 can version
 * the trader when the person drifts.
 */
const db = require('./db');

const VALID_TYPES = new Set([
  'preflight', 'trade', 'outcome', 'override', 'intervention', 'regime'
]);

async function ingest(event) {
  const type = VALID_TYPES.has(event.type) ? event.type : 'outcome';
  const ts = (event.ts && !Number.isNaN(Date.parse(event.ts)))
    ? new Date(event.ts).toISOString() : new Date().toISOString();
  const row = await db.query(
    `insert into traderedge_events (ts, trader_id, fingerprint_version, type, source, payload)
     values ($1, $2, $3, $4, $5, $6)
     returning event_id, ts`,
    [
      ts,
      String(event.traderId || 'local-trader').slice(0, 120),
      Math.max(1, Number(event.fingerprintVersion) || 1),
      type,
      String(event.source || 'self-report').slice(0, 40),
      JSON.stringify(event.payload || {})
    ]
  );
  return row.rows[0];
}

async function list(traderId, limit = 50) {
  const row = await db.query(
    `select event_id, ts, type, source, fingerprint_version, payload
     from traderedge_events where trader_id = $1
     order by ts desc limit $2`,
    [String(traderId || 'local-trader').slice(0, 120), Math.min(500, Number(limit) || 50)]
  );
  return row.rows;
}

async function count(traderId) {
  const row = await db.query(
    `select count(*)::int as n from traderedge_events where trader_id = $1`,
    [String(traderId || 'local-trader').slice(0, 120)]
  );
  return row.rows[0].n;
}

module.exports = { ingest, list, count, VALID_TYPES };
