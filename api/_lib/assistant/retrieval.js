'use strict';
/**
 * api/_lib/assistant/retrieval.js — hybrid retrieval.
 *
 * pgvector cosine + Postgres full-text, fused with Reciprocal Rank Fusion (RRF).
 * When no embeddings provider is configured, falls back to full-text-only, so
 * the assistant still retrieves + cites sources with zero new keys.
 */
const db = require('../traderedge/db');

const HYBRID_SQL = `
WITH vector_search AS (
  SELECT c.id,
         row_number() over (order by c.embedding <=> $1::vector) AS rank,
         (c.embedding <=> $1::vector) AS distance
  FROM assistant_chunks c
  JOIN assistant_documents d ON d.id = c.document_id
  WHERE d.access = $4
    AND c.embedding IS NOT NULL
    AND ($5::text IS NULL OR d.category = $5)
  ORDER BY c.embedding <=> $1::vector
  LIMIT $2
),
keyword_search AS (
  SELECT c.id,
         row_number() over (order by ts_rank_cd(c.tsv, websearch_to_tsquery('english', $3)) desc) AS rank
  FROM assistant_chunks c
  JOIN assistant_documents d ON d.id = c.document_id
  WHERE d.access = $4
    AND c.tsv @@ websearch_to_tsquery('english', $3)
    AND ($5::text IS NULL OR d.category = $5)
  ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('english', $3)) desc
  LIMIT $2
)
SELECT c.id, c.content, c.section, d.title, d.source_path, d.category,
       v.distance AS distance,
       (k.id IS NOT NULL) AS matched_keyword,
       coalesce(1.0 / ($6 + v.rank), 0) + coalesce(1.0 / ($6 + k.rank), 0) AS rrf_score
FROM assistant_chunks c
JOIN assistant_documents d ON d.id = c.document_id
LEFT JOIN vector_search v ON v.id = c.id
LEFT JOIN keyword_search k ON k.id = c.id
WHERE v.id IS NOT NULL OR k.id IS NOT NULL
ORDER BY rrf_score DESC
LIMIT $7;
`;

const KEYWORD_SQL = `
SELECT c.id, c.content, c.section, d.title, d.source_path, d.category,
       null::float8 AS distance,
       true AS matched_keyword,
       ts_rank_cd(c.tsv, websearch_to_tsquery('english', $2)) AS rrf_score
FROM assistant_chunks c
JOIN assistant_documents d ON d.id = c.document_id
WHERE d.access = $1
  AND c.tsv @@ websearch_to_tsquery('english', $2)
  AND ($3::text IS NULL OR d.category = $3)
ORDER BY rrf_score DESC
LIMIT $4;
`;

function toVecString(v) { return '[' + v.map(n => Number(n)).join(',') + ']'; }

/**
 * OR-join whitespace-separated tokens so websearch_to_tsquery produces an OR of
 * lexemes instead of an AND. AND is too strict for natural-language questions
 * ("what courses does X offer?" — 'offer' is a content word no chunk may hold);
 * OR keeps recall while ts_rank_cd still prefers multi-term hits.
 */
function orQuery(q) {
  return String(q).trim().split(/\s+/).filter(Boolean).join(' or ');
}

/**
 * @param {string} query
 * @param {number[]|null} embedding — null/empty => full-text-only path
 * @param {object} [opts] { topK, finalK, rrfK, maxVectorDistance, category, access }
 */
async function hybridSearch(query, embedding, opts = {}) {
  const topK = opts.topK ?? 20;
  const finalK = opts.finalK ?? 5;
  const rrfK = opts.rrfK ?? 60;
  const maxDist = opts.maxVectorDistance ?? 0.65;
  const category = opts.category ?? null;
  const access = opts.access ?? 'public';
  const q = String(query || '').trim();
  if (!q) return [];

  const qOr = orQuery(q);
  const hasVector = Array.isArray(embedding) && embedding.length > 0;
  let rows;

  if (hasVector) {
    const res = await db.query(HYBRID_SQL, [
      toVecString(embedding), topK, qOr, access, category, rrfK, finalK
    ]);
    rows = res.rows;
    // Keep keyword hits unconditionally (exact acronyms / feature names);
    // drop weak vector-only matches.
    rows = rows.filter(r => r.matched_keyword || (r.distance != null && Number(r.distance) <= maxDist));
    rows = rows.slice(0, finalK);
  } else {
    const res = await db.query(KEYWORD_SQL, [access, qOr, category, finalK]);
    rows = res.rows;
  }

  return rows.map(r => ({
    id: Number(r.id),
    content: r.content,
    section: r.section,
    title: r.title,
    source_path: r.source_path,
    category: r.category,
    distance: r.distance == null ? null : Number(r.distance),
    matched_keyword: !!r.matched_keyword,
    rrf_score: Number(r.rrf_score)
  }));
}

module.exports = { hybridSearch };
