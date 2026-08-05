'use strict';
/*
 * ai_providers.js — zero-dependency clients for the AI features
 * ==================================================================
 * Both DeepSeek and Kimi expose an OpenAI-compatible
 * /chat/completions endpoint, so a single generic client covers both.
 *
 * Secrets are read from environment (never hardcoded, never sent to the
 * browser). The backend host is responsible for keeping these server-side.
 *
 * Usage:
 *   const { aiChat, PROVIDERS } = require('./ai_providers');
 *   const r = await aiChat({ provider: 'deepseek', messages: [...] });
 */
const https = require('https');

// Provider registry — baseUrl already includes the /v1 path where required.
const PROVIDERS = {
  deepseek: {
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
    // env var holding the key, and the default model
    keyEnv: 'DEEPSEEK_API_KEY',
    modelEnv: 'DEEPSEEK_MODEL',
    defaultModel: 'deepseek-chat'
  },
  kimi: {
    label: 'Kimi',
    baseUrl: 'https://api.moonshot.cn/v1',
    keyEnv: 'KIMI_API_KEY',
    modelEnv: 'KIMI_MODEL',
    defaultModel: 'moonshot-v1-8k'
  }
};

/**
 * Raw OpenAI-compatible chat completion request.
 * @param {object} o
 * @param {string} o.baseUrl   e.g. https://api.deepseek.com  (path /chat/completions appended)
 * @param {string} o.apiKey
 * @param {string} o.model
 * @param {Array}  o.messages  [{role:'system'|'user'|'assistant', content}]
 * @param {number} [o.temperature=0.7]
 * @param {number} [o.maxTokens=1024]
 * @param {number} [o.timeoutMs=20000]
 */
function chatCompletion({ baseUrl, apiKey, model, messages, temperature = 0.7, maxTokens = 1024, timeoutMs = 20000 }) {
  return new Promise((resolve, reject) => {
    if (!apiKey) return reject(new Error('missing API key for provider'));
    const url = new URL(baseUrl.replace(/\/+$/, '') + '/chat/completions');
    const payload = JSON.stringify({
      model,
      messages,
      temperature,
      max_tokens: maxTokens,
      stream: false
    });
    const req = https.request(
      {
        hostname: url.hostname,
        path: url.pathname + url.search,
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
            const content = json.choices && json.choices[0] && json.choices[0].message
              ? json.choices[0].message.content
              : null;
            if (content == null) return reject(new Error('no content in provider response'));
            resolve({ provider: model, content, raw: json });
          } catch (e) {
            reject(new Error('provider response parse error: ' + e.message));
          }
        });
      }
    );
    req.on('error', e => reject(new Error('provider request failed: ' + e.message)));
    req.setTimeout(timeoutMs, () => req.destroy(new Error('provider timeout')));
    req.write(payload);
    req.end();
  });
}

/**
 * High-level helper: pick a provider, resolve its key + model from env,
 * and run a chat completion.
 * @param {object} o
 * @param {('deepseek'|'kimi')} o.provider
 * @param {Array}  o.messages
 * @param {object} [o.options]  { temperature, maxTokens, model } overrides
 */
async function aiChat({ provider, messages, options = {} }) {
  const p = PROVIDERS[provider];
  if (!p) throw new Error('unknown provider: ' + provider);
  const apiKey = process.env[p.keyEnv];
  if (!apiKey) throw new Error(p.label + ' API key not configured — set ' + p.keyEnv);
  const model = options.model || process.env[p.modelEnv] || p.defaultModel;
  return chatCompletion({
    baseUrl: p.baseUrl,
    apiKey,
    model,
    messages,
    temperature: options.temperature != null ? options.temperature : 0.7,
    maxTokens: options.maxTokens != null ? options.maxTokens : 1024
  });
}

/** True if the given provider has a key configured in the environment. */
function isConfigured(provider) {
  const p = PROVIDERS[provider];
  return !!(p && process.env[p.keyEnv]);
}

module.exports = { PROVIDERS, chatCompletion, aiChat, isConfigured };
