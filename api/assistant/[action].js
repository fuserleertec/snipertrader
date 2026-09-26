'use strict';
// SniperTrader.ai site assistant — Vercel dynamic route (counts as ONE function).
//   POST /api/assistant/chat     → RAG chat
//   POST /api/assistant/feedback → rating/comment on an answer
//   GET  /api/assistant/search   → raw retrieval (debug/admin; ?q=&access=)
//   GET  /api/assistant/diag     → status
const engine = require('../_lib/assistant');

function setCors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

module.exports = async (req, res) => {
  setCors(res);
  if (req.method === 'OPTIONS') { res.status(204); return res.end(); }
  const url = new URL(req.url, 'http://localhost');
  const action = (url.pathname.split('/').pop() || '').toLowerCase();
  try {
    switch (action) {
      case 'chat':
        if (req.method !== 'POST') { res.status(404).json({ error: 'not found — POST /api/assistant/chat' }); return; }
        return engine.chat(req, res);
      case 'feedback':
        if (req.method !== 'POST') { res.status(404).json({ error: 'not found — POST /api/assistant/feedback' }); return; }
        return engine.feedback(req, res);
      case 'search':
        if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/assistant/search?q=...' }); return; }
        return engine.search(req, res);
      case 'diag':
        if (req.method !== 'GET') { res.status(404).json({ error: 'not found — GET /api/assistant/diag' }); return; }
        return engine.diag(req, res);
      default:
        res.status(404).json({ error: 'unknown assistant action: ' + action });
    }
  } catch (e) {
    res.status(500).json({ error: String(e.message || e) });
  }
};
