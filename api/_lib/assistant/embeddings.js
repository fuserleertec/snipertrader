'use strict';
/**
 * api/_lib/assistant/embeddings.js — zero-dependency embeddings clients.
 *
 * Neither DeepSeek nor Kimi offers an embeddings endpoint, so vector search
 * needs a dedicated embeddings provider. OpenAI and Voyage both expose an
 * OpenAI-compatible POST /embeddings, so one generic client covers both.
 *
 * Honest degradation: if NO embeddings key is configured, isConfigured() is
 * false and retrieval falls back to full-text (tsvector) only. Vector search
 * lights up automatically the moment a key lands in env — no code change.
 */
const https = require('https');

const EMBEDDERS = {
  openai: {
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    keyEnv: 'OPENAI_API_KEY',
    modelEnv: 'EMBEDDING_MODEL',
    defaultModel: 'text-embedding-3-small',
    dims: 1536
  },
  voyage: {
    label: 'Voyage AI',
    baseUrl: 'https://api.voyageai.com/v1',
    keyEnv: 'VOYAGE_API_KEY',
    modelEnv: 'EMBEDDING_MODEL',
    defaultModel: 'voyage-3-lite',
    dims: 1024
  }
};

/** First provider with a key in env, or null. */
function activeEmbedder() {
  for (const name of Object.keys(EMBEDDERS)) {
    const p = EMBEDDERS[name];
    if (process.env[p.keyEnv]) return { name, ...p };
  }
  return null;
}

function isConfigured() { return activeEmbedder() !== null; }

/** Vector dimension for the schema column (must match the active provider). */
function dims() {
  const n = Number(process.env.EMBEDDING_DIMS);
  if (n > 0) return n;
  const a = activeEmbedder();
  return a ? a.dims : 1536;
}

function embedRequest({ baseUrl, apiKey, model, input }) {
  return new Promise((resolve, reject) => {
    if (!apiKey) return reject(new Error('missing embeddings API key'));
    const url = new URL(baseUrl.replace(/\/+$/, '') + '/embeddings');
    const payload = JSON.stringify({ model, input });
    const req = https.request(
      {
        hostname: url.hostname,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + apiKey,
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      },
      res => {
        let data = '';
        res.on('data', c => (data += c));
        res.on('end', () => {
          if (res.statusCode >= 400) {
            let msg = 'HTTP ' + res.statusCode;
            try {
              const e = JSON.parse(data);
              if (e && e.error && (e.error.message || e.error.type)) msg = e.error.message || e.error.type;
            } catch (_) {}
            return reject(new Error(msg));
          }
          try {
            const json = JSON.parse(data);
            const items = (json.data || []).slice().sort((a, b) => a.index - b.index);
            const vecs = items.map(d => d.embedding);
            const want = Array.isArray(input) ? input.length : 1;
            if (vecs.length !== want) return reject(new Error('embedding count mismatch'));
            resolve(vecs);
          } catch (e) {
            reject(new Error('embeddings parse error: ' + e.message));
          }
        });
      }
    );
    req.on('error', e => reject(new Error('embeddings request failed: ' + e.message)));
    req.setTimeout(30000, () => req.destroy(new Error('embeddings timeout')));
    req.write(payload);
    req.end();
  });
}

async function embedMany(texts) {
  const a = activeEmbedder();
  if (!a) throw new Error('no embeddings provider configured (set OPENAI_API_KEY or VOYAGE_API_KEY)');
  const model = process.env[a.modelEnv] || a.defaultModel;
  const arr = texts.map(String).filter(s => s.length > 0);
  if (!arr.length) return [];
  return embedRequest({ baseUrl: a.baseUrl, apiKey: process.env[a.keyEnv], model, input: arr });
}

async function embedOne(text) {
  const vecs = await embedMany([text]);
  return vecs[0];
}

module.exports = { EMBEDDERS, embedOne, embedMany, isConfigured, activeEmbedder, dims };
