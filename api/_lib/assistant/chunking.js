'use strict';
/**
 * api/_lib/assistant/chunking.js — markdown-aware chunking.
 * Split by headings (respecting code fences), then slide a word window within
 * each section with overlap. Word-based (no tiktoken — zero-dep).
 */
function chunkMarkdown(text, targetWords = 450, overlapWords = 60) {
  const lines = String(text || '').split(/\r?\n/);
  const sections = [];
  let stack = [];
  let buf = [];
  let inCode = false;

  const flush = () => {
    if (buf.length) {
      sections.push({ heading: stack.join(' > ') || 'Intro', body: buf.join('\n').trim() });
      buf = [];
    }
  };

  for (const line of lines) {
    if (line.startsWith('```')) { inCode = !inCode; buf.push(line); continue; }
    if (!inCode) {
      const m = line.match(/^(#{1,6})\s+(.*)$/);
      if (m) {
        flush();
        const level = m[1].length;
        stack = stack.slice(0, level - 1);
        stack.push(m[2].trim());
        continue;
      }
    }
    buf.push(line);
  }
  flush();

  const chunks = [];
  const step = Math.max(1, targetWords - overlapWords);
  for (const { heading, body } of sections) {
    if (!body) continue;
    const words = body.split(/\s+/).filter(Boolean);
    for (let i = 0; i < words.length; i += step) {
      const piece = words.slice(i, i + targetWords).join(' ').trim();
      if (piece) chunks.push({ section: heading, content: piece });
    }
  }
  return chunks;
}

module.exports = { chunkMarkdown };
