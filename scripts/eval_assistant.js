'use strict';
/**
 * scripts/eval_assistant.js — eval harness for the SniperTrader.ai site assistant.
 *
 * Measures three things against the live retrieval + LLM stack:
 *   1. Retrieval quality — recall@5 + MRR on golden (query → chunk) pairs.
 *   2. Groundedness — do answerable questions produce cited ([n]) answers?
 *   3. Refusal accuracy — do unanswerable questions get declined, not fabricated?
 *
 * Zero-dep. Requires the same libs the live endpoint uses. Run from repo root:
 *   node scripts/eval_assistant.js            # report, exit 0
 *   node scripts/eval_assistant.js --strict   # exit 1 if any metric < threshold
 *
 * HONESTY: recall@5/MRR are only as meaningful as the corpus. With a thin
 * public corpus (see the header line) these are smoke tests, not a real eval —
 * the numbers get teeth as docs/public/ grows.
 */
const db = require('../api/_lib/traderedge/db');
const { hybridSearch } = require('../api/_lib/assistant/retrieval');
const { embedOne, isConfigured: embeddingsOn } = require('../api/_lib/assistant/embeddings');
const { rerank, isRerankerConfigured } = require('../api/_lib/assistant/rerank');
const { aiChat, isConfigured: llmOn } = require('../api/_ai_providers');
const { SYSTEM_PROMPT, buildContext } = require('../api/_lib/assistant/prompt');
const { rewriteQuery } = require('../api/_lib/assistant/query');

const FINAL_K = 5;
const CANDIDATE_K = 20;
const THRESHOLD = Number(process.env.EVAL_MIN_SCORE) || 0.5;

// Golden retrieval pairs: { q, access, expect: { title, contains } }.
// `contains` is matched against section+content (the same text retrieval sees).
const RETRIEVAL_SET = [
  { q: 'What is the VWAP Suite?',                 access: 'public',   expect: { title: 'platform-overview.md', contains: 'VWAP Suite' } },
  { q: 'What courses does SniperTrader.ai offer?', access: 'public',  expect: { title: 'platform-overview.md', contains: 'USME/ICT' } },
  { q: 'What AI tools are available?',            access: 'public',   expect: { title: 'platform-overview.md', contains: 'Chart AI' } },
  { q: 'What is SniperTrader.ai?',                access: 'public',   expect: { title: 'platform-overview.md', contains: 'trading-education' } },
  { q: 'calculator',                              access: 'public',   expect: { title: 'platform-overview.md', contains: 'Calculator' } },
  { q: 'What are the color tokens?',              access: 'internal', expect: { title: 'design-tokens.md', contains: 'color tokens' } },
  { q: 'What is the brand voice?',                access: 'internal', expect: { title: 'voice-and-tone.md', contains: 'brand keywords' } },
  { q: 'keyboard accessibility',                  access: 'internal', expect: { title: 'accessibility-audit.md', contains: 'keyboard operability' } },
  { q: 'API contract',                            access: 'internal', expect: { title: 'admin-portal.md', contains: 'API contract' } },
];

// Answerable questions (public, since the chat endpoint serves access='public').
const ANSWERABLE_SET = [
  'What is the VWAP Suite?',
  'What courses does SniperTrader.ai offer?',
  'What AI tools are available?',
];

// Unanswerable from the corpus — must be declined, not invented.
const REFUSAL_SET = [
  'How much does the VWAP Elite course cost?',
  'What is the CEO\'s personal email address?',
  'What will Bitcoin\'s price be tomorrow?',
];

const CITATION_RE = /\[\d+\]/;
const REFUSAL_RE = /do(?:es)?n't have|do(?:es)? not have|do(?:es)?n't cover|do(?:es)? not cover|no pricing|not covered|not available|can(?:not|'t) (?:answer|provide|share|confirm|help)|does(?:n't| not) provide|don't have that detail/i;

function ci(s) { return String(s || '').toLowerCase(); }

async function retrievalEval() {
  const results = [];
  for (const item of RETRIEVAL_SET) {
    const q = item.q;
    let embedding = null;
    if (embeddingsOn()) { try { embedding = await embedOne(q); } catch (_) {} }
    const candidates = await hybridSearch(q, embedding, { access: item.access, finalK: CANDIDATE_K });
    const { chunks } = await rerank(q, candidates, { topN: FINAL_K });
    const idx = chunks.findIndex(c =>
      c.title === item.expect.title &&
      ci(c.section + ' ' + c.content).includes(ci(item.expect.contains))
    );
    results.push({
      q, access: item.access,
      found: idx >= 0,
      rank: idx >= 0 ? idx + 1 : 0,
      got: chunks.slice(0, 3).map(c => `${c.title}:${(c.section || '').split(' > ').slice(-1)[0]}`)
    });
  }
  const hits = results.filter(r => r.found).length;
  const mrr = results.reduce((s, r) => s + (r.rank ? 1 / r.rank : 0), 0) / results.length;
  return { results, recallAt5: hits / results.length, mrr, n: results.length };
}

// Mirrors the chat endpoint's flow (rewrite → embed → retrieve → rerank → LLM).
async function answer(message, history) {
  const rq = await rewriteQuery(message, history || []);
  let embedding = null;
  if (embeddingsOn()) { try { embedding = await embedOne(rq); } catch (_) {} }
  const candidates = await hybridSearch(rq, embedding, { access: 'public', finalK: CANDIDATE_K });
  const { chunks } = await rerank(rq, candidates, { topN: FINAL_K });
  const provider = llmOn('deepseek') ? 'deepseek' : 'kimi';
  const completion = await aiChat({
    provider,
    messages: [
      { role: 'system', content: SYSTEM_PROMPT.replace('{context}', buildContext(chunks)) },
      ...(history || []),
      { role: 'user', content: message }
    ],
    options: { temperature: 0, maxTokens: 500 }  // temp 0 for a deterministic gate (prod uses 0.2)
  });
  return completion.content;
}

async function llmEval() {
  if (!(llmOn('deepseek') || llmOn('kimi'))) return { skip: true, reason: 'no LLM key configured' };
  const cited = [];
  for (const q of ANSWERABLE_SET) {
    const a = await answer(q);
    cited.push({ q, pass: CITATION_RE.test(a), snippet: a.slice(0, 160).replace(/\n/g, ' ') });
  }
  const refused = [];
  for (const q of REFUSAL_SET) {
    const a = await answer(q);
    refused.push({ q, pass: REFUSAL_RE.test(a), snippet: a.slice(0, 160).replace(/\n/g, ' ') });
  }
  return {
    skip: false,
    citationRate: cited.filter(x => x.pass).length / cited.length,
    refusalRate: refused.filter(x => x.pass).length / refused.length,
    cited, refused
  };
}

async function main() {
  const strict = process.argv.includes('--strict');
  const counts = (await db.query(
    `select
       (select count(*)::int from assistant_documents where access='public') as public_docs,
       (select count(*)::int from assistant_chunks c join assistant_documents d on d.id=c.document_id where d.access='public') as public_chunks,
       (select count(*)::int from assistant_documents) as total_docs,
       (select count(*)::int from assistant_chunks) as total_chunks`
  )).rows[0];

  console.log('SniperTrader.ai Assistant — Eval Report');
  console.log('='.repeat(46));
  console.log(`corpus: ${counts.total_docs} docs / ${counts.total_chunks} chunks   (public: ${counts.public_docs} docs / ${counts.public_chunks} chunks)`);
  console.log(`embeddings: ${embeddingsOn() ? 'on' : 'OFF (full-text only)'}   rerank: ${isRerankerConfigured() ? 'cohere' : 'heuristic'}`);

  const r = await retrievalEval();
  console.log(`\n[1] Retrieval   recall@5=${r.recallAt5.toFixed(3)}   MRR=${r.mrr.toFixed(3)}   (${r.n} golden pairs)`);
  for (const x of r.results) {
    const mark = x.found ? '  hit ' : ' MISS ';
    console.log(`${mark} [${x.access.padEnd(8)}] ${x.q}${x.found ? `  (rank ${x.rank})` : '  -> got ' + JSON.stringify(x.got)}`);
  }

  const l = await llmEval();
  if (l.skip) {
    console.log('\n[2] Groundedness / [3] Refusal: SKIPPED (' + l.reason + ')');
  } else {
    console.log(`\n[2] Groundedness   citation_rate=${l.citationRate.toFixed(3)}`);
    for (const x of l.cited) console.log(`${x.pass ? '  cite' : ' MISS '}  ${x.q}  :: ${x.snippet}`);
    console.log(`\n[3] Refusal   refusal_rate=${l.refusalRate.toFixed(3)}`);
    for (const x of l.refused) console.log(`${x.pass ? '  refuse' : ' FAB?'}  ${x.q}  :: ${x.snippet}`);
  }

  const scores = {
    recallAt5: r.recallAt5,
    mrr: r.mrr,
    citationRate: l.skip ? null : l.citationRate,
    refusalRate: l.skip ? null : l.refusalRate
  };
  console.log('\nJSON_SUMMARY ' + JSON.stringify(scores));

  if (strict) {
    const checks = [['recall@5', r.recallAt5]];
    if (!l.skip) checks.push(['citation', l.citationRate], ['refusal', l.refusalRate]);
    const failed = checks.filter(([, v]) => v < THRESHOLD);
    if (failed.length) {
      console.error(`STRICT FAIL: ${failed.map(([k]) => k).join(', ')} below ${THRESHOLD}`);
      process.exit(1);
    }
    console.log(`STRICT PASS: all metrics >= ${THRESHOLD}`);
  }
  process.exit(0);
}

main().catch(e => { console.error('EVAL ERROR:', e.message); process.exit(2); });
