/* ============================================================
   snipertrader.ai — Command Portal · api.js
   ------------------------------------------------------------
   Real API client for the admin Command Portal. Talks to the
   Vercel serverless admin service (/api/admin/*) and the live
   prop-account telemetry (/api/prop/account).

   Contract (mirrors mock-api.js so the portal is transport-agnostic):
     getAll()            → full dashboard payload (meta + sections)
     get(resource)       → single section (e.g. 'sessions')
     patch(resource, b)  → PATCH a whitelisted field set
     propAccount()       → live Alpaca paper account (graceful)

   Every request has a timeout and throws a descriptive Error on
   failure so the UI can render an honest error state with Retry.
   ============================================================ */
(function (global) {
  'use strict';

  var TOKEN = 'demo-admin-token';               // demo gate — replace with real session/JWT
  var TIMEOUT_MS = 8000;

  var HEADERS = {
    'Authorization': 'Bearer ' + TOKEN,
    'Content-Type': 'application/json'
  };

  function esc(s) {
    return String(s == null ? '' : s);
  }

  /** Fetch with an AbortController timeout; throws on non-2xx. */
  function request(path, opts) {
    opts = opts || {};
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = null;
    if (ctrl) {
      timer = setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);
    }
    var headers = opts.noAuth ? { 'Accept': 'application/json' } : HEADERS;
    if (opts.headers) { for (var k in opts.headers) headers[k] = opts.headers[k]; }

    return fetch(path, {
      method: opts.method || 'GET',
      headers: headers,
      body: opts.body,
      signal: ctrl ? ctrl.signal : undefined
    })
      .then(function (res) {
        if (!res.ok) {
          return res.text().then(function (t) {
            var msg = 'HTTP ' + res.status;
            try { var j = JSON.parse(t); if (j && j.error) msg = j.error; } catch (e) {}
            throw new Error(msg);
          });
        }
        return res.json();
      })
      .catch(function (e) {
        if (e && e.name === 'AbortError') throw new Error('Request timed out');
        throw e;
      })
      .finally(function () {
        if (timer) clearTimeout(timer);
      });
  }

  var SniperAPI = {
    getAll: function () { return request('/api/admin/all'); },
    get: function (resource) { return request('/api/admin/' + esc(resource)); },
    patch: function (resource, body) {
      return request('/api/admin/' + esc(resource), { method: 'PATCH', body: JSON.stringify(body || {}) });
    },
    propAccount: function () { return request('/api/prop/account', { noAuth: true }); },
    isAvailable: function () {
      return request('/api/admin/all').then(function () { return true; }).catch(function () { return false; });
    }
  };

  global.SniperAPI = SniperAPI;
})(typeof window !== 'undefined' ? window : this);
