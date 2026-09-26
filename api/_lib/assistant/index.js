'use strict';
/**
 * api/_lib/assistant/index.js — SniperTrader.ai site assistant facade + handlers.
 *
 *   POST /api/assistant/chat     — RAG chat (sources → answer), Postgres memory
 *   POST /api/assistant/feedback — rating/comment on an answer
 *   GET  /api/assistant/search   — raw retrieval (debug/admin; ?q=&access=)
 *   GET  /api/assistant/diag     — non-secret status
 */
const db = require('../traderedge/db');
const memory = require('./memory');
const promptMod = require('./prompt');
const { hybridSearch } = require('./retrieval');
const { embedOne, isConfigured: embeddingsOn, activeEmbedder } = require('./embeddings');
const { aiChat, isConfigured: llmOn } = require('../../_ai_providers');
const { rewriteQuery } = require('./query');
const { rerank, isRerankerConfigured } = require('./rerank');

const HISTORY_TURNS = Number(process.env.ASSISTANT_HISTORY_TURNS) || 8;
const FINAL_K = Number(process.env.ASSISTANT_FINAL_K) || 5;
const CANDIDATE_K = Number(process.env.ASSISTANT_CANDIDATE_K) || 20;

function respond(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
}

function readBody(req, maxBytes = 1e5) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', c => { body += c; if (body.length > maxBytes) reject(new Error('payload too large')); });
    req.on('end', () => { try { resolve(body ? JSON.parse(body) : {}); } catch (e) { reject(new Error('invalid JSON')); } });
    req.on('error', reject);
  });
}

async function chat(req, res) {
  let body;
  try { body = await readBody(req); } catch (e) { return respond(res, 400, { error: e.message }); }
  const message = String(body.message || '').trim();
  if (!message || message.length > 2000) return respond(res, 400, { error: 'message required (1..2000 chars)' });

  const provider = llmOn('deepseek') ? 'deepseek' : (llmOn('kimi') ? 'kimi' : null);
  if (!provider) return respond(res, 503, { error: 'no AI provider configured (DEEPSEEK_API_KEY / KIMI_API_KEY)' });

  const started = Date.now();
  try {
    const sid = await memory.ensureSession(body.session_id, req);
    const history = await memory.loadHistory(sid, HISTORY_TURNS);
    await memory.saveMessage(sid, 'user', message);

    const rq = await rewriteQuery(message, history);
    let embedding = null;
    if (embeddingsOn()) {
      try { embedding = await embedOne(rq); } catch (_) { embedding = null; } // degrade to full-text
    }
    const candidates = await hybridSearch(rq, embedding, { access: 'public', finalK: CANDIDATE_K });
    const { chunks, mode: rerankMode } = await rerank(rq, candidates, { topN: FINAL_K });
    const sources = promptMod.toSources(chunks);

    const messages = [
      { role: 'system', content: promptMod.SYSTEM_PROMPT.replace('{context}', promptMod.buildContext(chunks)) },
      ...history,
      { role: 'user', content: message }
    ];

    const completion = await aiChat({ provider, messages, options: { temperature: 0.2, maxTokens: 500 } });

    const latencyMs = Date.now() - started;
    const assistantMessageId = await memory.saveMessage(sid, 'assistant', completion.content, {
      sources, chunkIds: chunks.map(c => c.id), latencyMs
    });

    respond(res, 200, {
      content: completion.content,
      sources,
      session_id: sid,
      message_id: assistantMessageId,
      latency_ms: latencyMs,
      retrieval: {
        mode: embedding ? 'hybrid' : 'fulltext',
        embeddings: embeddingsOn(),
        query: rq,
        candidates: candidates.length,
        chunks: chunks.length,
        rerank: { mode: rerankMode }
      },
      llm: { provider, model: (completion.raw && completion.raw.model) || completion.provider }
    });
  } catch (e) {
    respond(res, 502, { error: String(e.message || e) });
  }
}

async function feedback(req, res) {
  let body;
  try { body = await readBody(req); } catch (e) { return respond(res, 400, { error: e.message }); }
  const id = Number(body.message_id);
  if (!Number.isInteger(id) || id <= 0) return respond(res, 400, { error: 'message_id required' });
  const rating = Number(body.rating);
  if (!Number.isInteger(rating) || rating < 1 || rating > 5) return respond(res, 400, { error: 'rating required (1..5)' });
  try {
    await memory.saveFeedback(id, rating, body.reason, body.comment);
    respond(res, 200, { ok: true });
  } catch (e) {
    respond(res, 500, { error: String(e.message || e) });
  }
}

async function search(req, res) {
  const url = new URL(req.url, 'http://localhost');
  const q = (url.searchParams.get('q') || '').trim();
  const access = url.searchParams.get('access') || 'public';
  if (!q) return respond(res, 400, { error: 'q required' });
  let embedding = null;
  if (embeddingsOn()) { try { embedding = await embedOne(q); } catch (_) { embedding = null; } }
  const chunks = await hybridSearch(q, embedding, { access, finalK: 10 });
  respond(res, 200, { query: q, mode: embedding ? 'hybrid' : 'fulltext', chunks: promptMod.toSources(chunks) });
}

async function diag(req, res) {
  let counts = null;
  try {
    const c = await db.query(
      `select (select count(*)::int from assistant_documents) as docs,
              (select count(*)::int from assistant_chunks) as chunks,
              (select count(*)::int from assistant_chunks where embedding is not null) as embedded_chunks`
    );
    counts = c.rows[0];
  } catch (e) { counts = { error: String(e.message || e) }; }
  respond(res, 200, {
    ok: true,
    embeddings: { configured: embeddingsOn(), provider: activeEmbedder() ? activeEmbedder().name : null },
    rerank: { cohere: isRerankerConfigured() },
    llm: { deepseek: llmOn('deepseek'), kimi: llmOn('kimi') },
    counts
  });
}

module.exports = { chat, feedback, search, diag, readBody, respond };
