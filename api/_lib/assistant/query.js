'use strict';
/**
 * api/_lib/assistant/query.js — LLM query rewriting.
 *
 * Follow-ups ("and how do I set it up?") resolve against prior turns. A small
 * LLM call rewrites them into a standalone retrieval query. Key-gated on the
 * already-configured DeepSeek/Kimi; falls back to a heuristic prepend when the
 * LLM is unavailable or the message is a standalone question.
 */
const { aiChat, isConfigured: llmOn } = require('../../_ai_providers');

const REWRITE_PROMPT = `You rewrite a chat follow-up into a standalone search query for a knowledge base.
Given the conversation history and the latest user message, produce a short, self-contained search query (a few keywords or a phrase).
Do not answer the question. Output only the query, with no preamble, no quotes, and no trailing punctuation.`;

function heuristic(message, lastUser) {
  return `${lastUser.content} ${message}`.trim();
}

/**
 * @param {string} message latest user message
 * @param {Array<{role:string,content:string}>} history prior turns (not incl. current)
 * @returns {Promise<string>} standalone retrieval query
 */
async function rewriteQuery(message, history) {
  const trimmed = String(message || '').trim();
  const words = trimmed.split(/\s+/).filter(Boolean).length;
  const prior = Array.isArray(history) ? history : [];
  const lastUser = [...prior].reverse().find(m => m.role === 'user');

  // Standalone first turns and long questions need no rewrite.
  if (!lastUser || words >= 6) return trimmed;

  const provider = llmOn('deepseek') ? 'deepseek' : (llmOn('kimi') ? 'kimi' : null);
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
    const q = String(r.content || '').trim().replace(/^["'\`]+|["'\`]+$/g, '').replace(/[.?!]+$/, '');
    return q || heuristic(trimmed, lastUser);
  } catch (_) {
    return heuristic(trimmed, lastUser);
  }
}

module.exports = { rewriteQuery };
