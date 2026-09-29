'use strict';
/**
 * api/_lib/assistant/query.js — LLM query rewriting + cross-lingual translation.
 *
 * Follow-ups ("and how do I set it up?") resolve against prior turns. A small
 * LLM call rewrites them into a standalone retrieval query. Key-gated on the
 * already-configured DeepSeek/Kimi; falls back to a heuristic prepend when the
 * LLM is unavailable or the message is a standalone question.
 *
 * Non-English input (Chinese, etc.) is translated to English first so the
 * English knowledge base stays searchable; the answer language is handled
 * separately by the system prompt (respond in the visitor's language).
 */
const { aiChat, isConfigured: llmOn } = require('../../_ai_providers');

const REWRITE_PROMPT = `You rewrite a chat follow-up into a standalone search query for a knowledge base.
Given the conversation history and the latest user message, produce a short, self-contained search query (a few keywords or a phrase).
Do not answer the question. Output only the query, with no preamble, no quotes, and no trailing punctuation.`;

const TRANSLATE_PROMPT = `Translate the following message into English for search. Output only the English translation — no preamble, no quotes, no extra text.`;

// Chinese + Japanese kana + Korean ranges (non-Latin scripts → cross-lingual path).
const CJK_RE = /[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/;

function hasCJK(s) { return CJK_RE.test(String(s || '')); }

function heuristic(message, lastUser) {
  return `${lastUser.content} ${message}`.trim();
}

async function translateToEnglish(text, provider) {
  const r = await aiChat({
    provider,
    messages: [
      { role: 'system', content: TRANSLATE_PROMPT },
      { role: 'user', content: text }
    ],
    options: { temperature: 0, maxTokens: 120 }
  });
  const q = String(r.content || '').trim().replace(/^["'`]+|["'`]+$/g, '').replace(/[.?!]+$/, '');
  return q || text;
}

/**
 * @param {string} message latest user message
 * @param {Array<{role:string,content:string}>} history prior turns (not incl. current)
 * @returns {Promise<string>} standalone retrieval query (English)
 */
async function rewriteQuery(message, history) {
  const trimmed = String(message || '').trim();
  const prior = Array.isArray(history) ? history : [];
  const lastUser = [...prior].reverse().find(m => m.role === 'user');
  const provider = llmOn('deepseek') ? 'deepseek' : (llmOn('kimi') ? 'kimi' : null);

  // Non-English input → translate to English so the English corpus is searchable.
  // Short follow-ups carry the prior user turn for context.
  if (hasCJK(trimmed) && provider) {
    const wc = trimmed.split(/\s+/).filter(Boolean).length;
    const target = (lastUser && wc < 6) ? `${lastUser.content} ${trimmed}` : trimmed;
    try { return await translateToEnglish(target, provider); }
    catch (_) { /* fall through to English heuristics */ }
  }

  const words = trimmed.split(/\s+/).filter(Boolean).length;

  // Standalone first turns and long questions need no rewrite.
  if (!lastUser || words >= 6) return trimmed;
  if (!provider) return heuristic(trimmed, lastUser);

  try {
    const hist = prior.slice(-6).map(m => `${m.role}: ${m.content}`).join('\n');
    const r = await aiChat({
      provider,
      messages: [
        { role: 'system', content: REWRITE_PROMPT },
        { role: 'user', content: `History:\n${hist}\n\nLatest message: ${trimmed}\n\nStandalone query:` }
      ],
      options: { temperature: 0, maxTokens: 60 }
    });
    const q = String(r.content || '').trim().replace(/^["'`]+|["'`]+$/g, '').replace(/[.?!]+$/, '');
    return q || heuristic(trimmed, lastUser);
  } catch (_) {
    return heuristic(trimmed, lastUser);
  }
}

module.exports = { rewriteQuery };
