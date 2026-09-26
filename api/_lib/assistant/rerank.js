'use strict';
/**
 * api/_lib/assistant/rerank.js — cross-encoder reranking of the candidate set.
 *
 * Retrieve ~20 candidates (RRF), then re-rank to the final top-K. Two paths:
 *  - Cohere Rerank (key-gated on COHERE_API_KEY): real cross-encoder quality.
 *  - Zero-dep heuristic (fallback): term overlap + exact-phrase + section bonus.
 *
 * Returns { chunks, mode } where mode is the path actually used ('cohere' |
 * 'heuristic') so the response never mislabels a fallback as a cross-encoder.
 */
const https = require('https');

const DEFAULT_TOP_N = Number(process.env.ASSISTANT_FINAL_K) || 5;

function isRerankerConfigured() { return !!process.env.COHERE_API_KEY; }

function cohereRerank(query, chunks, topN) {
  return new Promise((resolve, reject) => {
    const key = process.env.COHERE_API_KEY;
    if (!key) return reject(new Error('no COHERE_API_KEY'));
    const payload = JSON.stringify({
      model: process.env.COHERE_RERANK_MODEL || 'rerank-english-v3.0',
      query: String(query || ''),
      documents: chunks.map(c => c.content),
      top_n: topN,
      return_documents: false
    });
    const req = https.request(
      { hostname: 'api.cohere.com', path: '/v1/rerank', method: 'POST',
        headers: { 'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json' } },
      res => {
        let data = '';
        res.on('data', c => (data += c));
        res.on('end', () => {
          if (res.statusCode >= 400) return reject(new Error('cohere HTTP ' + res.statusCode));
          try {
            const json = JSON.parse(data);
            const score = new Map((json.results || []).map(r => [r.index, r.relevance_score]));
            const out = chunks.map((c, i) => ({ ...c, rerank_score: score.has(i) ? score.get(i) : 0 }));
            out.sort((a, b) => b.rerank_score - a.rerank_score);
            resolve(out.slice(0, topN));
          } catch (e) { reject(new Error('cohere parse error: ' + e.message)); }
        });
      }
    );
    req.on('error', e => reject(new Error('cohere request failed: ' + e.message)));
    req.setTimeout(15000, () => req.destroy(new Error('cohere timeout')));
    req.write(payload);
    req.end();
  });
}

function tokens(s) {
  return new Set(String(s || '').toLowerCase().split(/[^a-z0-9]+/).filter(Boolean));
}

function heuristicRerank(query, chunks, topN) {
  const qTok = tokens(query);
  const ql = String(query || '').toLowerCase().trim();
  const scored = chunks.map(c => {
    const text = `${c.section || ''} ${c.content || ''}`.toLowerCase();
    const cTok = tokens(text);
    let overlap = 0;
    for (const t of qTok) if (cTok.has(t)) overlap++;
    let score = overlap / Math.max(1, qTok.size);
    if (ql && text.includes(ql)) score += 0.5;                         // exact phrase
    if (c.section && tokens(c.section) && [...qTok].some(t => tokens(c.section).has(t))) score += 0.2; // heading match
    return { ...c, rerank_score: Math.round(score * 10000) / 10000 };
  });
  scored.sort((a, b) => b.rerank_score - a.rerank_score);
  return scored.slice(0, topN);
}

async function rerank(query, chunks, opts = {}) {
  const topN = opts.topN ?? DEFAULT_TOP_N;
  if (!chunks || !chunks.length) return { chunks: [], mode: 'heuristic' };
  if (isRerankerConfigured()) {
    try { return { chunks: await cohereRerank(query, chunks, topN), mode: 'cohere' }; }
    catch (_) { /* fall through to heuristic */ }
  }
  return { chunks: heuristicRerank(query, chunks, topN), mode: 'heuristic' };
}

module.exports = { rerank, cohereRerank, heuristicRerank, isRerankerConfigured };
