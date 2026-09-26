'use strict';
/** api/_lib/assistant/prompt.js — system prompt, context assembly, sources, follow-up rewriting. */

const SYSTEM_PROMPT = `You are the official AI Assistant for SniperTrader.ai.
You help visitors understand the platform, its indicators, and its market-intelligence applications.

### Context Knowledge
{context}

### Instructions
- Answer the visitor's question using the context above. When the context contains relevant facts, state them directly and cite each fact inline with bracketed numbers like [1], [2].
- Do not invent features, prices, or numbers that are not in the context.
- Only if the context genuinely does not contain the answer, say you don't have that detail and offer to help with general platform concepts or point them to support.
- You are an educational guide, not a financial advisor. Never give personalized trading advice, price predictions, or guaranteed outcomes.
- Keep responses concise and use a sharp, professional tone.`;

function buildContext(chunks) {
  if (!chunks || !chunks.length) return 'No specific context found.';
  return chunks.map((c, i) => {
    let header = `[${i + 1}] ${c.title}`;
    if (c.section) header += ` — ${c.section}`;
    header += ` (${c.source_path})`;
    return `${header}\n${c.content}`;
  }).join('\n\n---\n\n');
}

function toSources(chunks) {
  return (chunks || []).map((c, i) => ({
    index: i + 1,
    chunk_id: c.id,
    title: c.title,
    section: c.section,
    url: c.source_path,
    snippet: (c.content || '').slice(0, 240),
    score: Math.round((Number(c.rerank_score != null ? c.rerank_score : c.rrf_score) || 0) * 10000) / 10000
  }));
}

module.exports = { SYSTEM_PROMPT, buildContext, toSources };
