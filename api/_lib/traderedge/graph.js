'use strict';
/**
 * api/_lib/traderedge/graph.js — Layer 2: relational graph with honest
 * Bayesian posteriors.
 *
 * Association edges carry a Beta(α,β) posterior for P(win | condition).
 * Prior = Beta(1,1) (uniform). Every edge exposes `n` (real observations)
 * and a Wilson 95% CI — never a bare percentage. `kind:"causal"` edges are
 * reserved for intervention-created counterfactuals (not computed in v1).
 */
const db = require('./db');

// ── Honest CI: Wilson score interval over a Beta(α,β) posterior ───────────
function wilson(alpha, beta) {
  const z = 1.959963984540054; // z_0.975
  const den = alpha + beta;    // posterior pseudo-count
  if (den <= 0) return { mean: 0.5, lower: 0, upper: 1 };
  const p = alpha / den;
  const d = 1 + z * z / den;
  const center = (p + z * z / (2 * den)) / d;
  const margin = z * Math.sqrt(p * (1 - p) / den + z * z / (4 * den * den)) / d;
  return {
    mean: p,
    lower: Math.max(0, center - margin),
    upper: Math.min(1, center + margin)
  };
}

function posteriorView(alpha, beta) {
  const n = Math.max(0, alpha + beta - 2); // real observations (prior subtracted)
  const ci = wilson(alpha, beta);
  return {
    alpha, beta,
    n,
    mean: ci.mean,
    ci95: [ci.lower, ci.upper],
    evidence: n < 5 ? 'none' : n < 20 ? 'low' : n < 60 ? 'moderate' : 'strong'
  };
}

async function ensureNode(nodeId, type, props = {}) {
  await db.query(
    `insert into traderedge_nodes (node_id, type, props, updated_at)
     values ($1, $2, $3, now())
     on conflict (node_id) do update set type = excluded.type, updated_at = now()`,
    [nodeId, type, JSON.stringify(props)]
  );
}

async function bumpEdge(fromNode, toNode, kind, win) {
  const edgeId = `${fromNode}->${toNode}`;
  // Ensure both endpoints exist (cheap upserts).
  await ensureNode(fromNode, 'condition', {});
  await ensureNode(toNode, 'outcome', {});

  // Read-modify-write the Beta posterior.
  const cur = await db.query(
    `select posterior from traderedge_edges where edge_id = $1`, [edgeId]
  );
  let post = { alpha: 1, beta: 1, n: 0, ci95: null };
  if (cur.rows.length) {
    try { post = Object.assign(post, cur.rows[0].posterior); } catch (_) {}
  }
  post.alpha = Math.max(1, Number(post.alpha) || 1);
  post.beta = Math.max(1, Number(post.beta) || 1);
  if (win) post.alpha += 1; else post.beta += 1;

  await db.query(
    `insert into traderedge_edges (edge_id, from_node, to_node, kind, posterior, updated_at)
     values ($1, $2, $3, $4, $5, now())
     on conflict (edge_id) do update
       set posterior = excluded.posterior, kind = excluded.kind, updated_at = now()`,
    [edgeId, fromNode, toNode, kind, JSON.stringify(post)]
  );
  return { edgeId, ...posteriorView(post.alpha, post.beta) };
}

/**
 * recordOutcome({ win, state, regime, traderId })
 *   state  — one of FLOW|FOCUSED|NEUTRAL|ANXIOUS|REVENGE
 *   regime — free-text label, lowercased (e.g. "trending_highvol")
 */
async function recordOutcome(o) {
  const state = String(o.state || 'NEUTRAL').toUpperCase();
  const regime = String(o.regime || 'unknown').toLowerCase().replace(/\s+/g, '_');
  const win = !!o.win;

  const byState = await bumpEdge(`ps:${state}`, 'out:win', 'association', win);
  const byRegime = await bumpEdge(`regime:${regime}`, 'out:win', 'association', win);
  return { byState, byRegime };
}

async function getPosteriors() {
  const rows = await db.query(
    `select edge_id, from_node, to_node, kind, posterior, updated_at
     from traderedge_edges order by updated_at desc`
  );
  return rows.rows.map(r => {
    let post = r.posterior || { alpha: 1, beta: 1 };
    return {
      edgeId: r.edge_id,
      from: r.from_node,
      to: r.to_node,
      kind: r.kind,
      ...posteriorView(post.alpha, post.beta)
    };
  });
}

module.exports = { recordOutcome, getPosteriors, ensureNode, wilson, posteriorView };
