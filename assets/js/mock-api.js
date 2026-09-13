/* ============================================================
   snipertrader.ai — Command Portal · mock-api.js
   ------------------------------------------------------------
   Offline fallback data service. Used only when the real admin
   service (/api/admin/*) is unreachable (e.g. static-only host,
   local preview). Reads the clearly-labeled demo dataset from
   /assets/data/mock-data.json and simulates network latency so
   the skeleton-loading states are exercised honestly.

   Same interface as api.js (SniperAPI) so the portal is
   transport-agnostic:
     getAll() / get(resource) / patch(resource, body) / propAccount()

   propAccount() always rejects here: a live broker feed cannot be
   simulated, and the portal surfaces an honest "unavailable" state
   rather than fabricating account telemetry.
   ============================================================ */
(function (global) {
  'use strict';

  var MOCK_URL = '/assets/data/mock-data.json';
  var LATENCY_MIN = 280;
  var LATENCY_MAX = 620;

  var _db = null;

  function delay() {
    var ms = LATENCY_MIN + Math.random() * (LATENCY_MAX - LATENCY_MIN);
    return new Promise(function (res) { setTimeout(res, ms); });
  }

  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  function loadDB() {
    if (_db) return Promise.resolve(_db);
    return fetch(MOCK_URL, { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('mock data unavailable (HTTP ' + res.status + ')');
        return res.json();
      })
      .then(function (data) {
        data = data || {};
        data.meta = data.meta || {};
        data.meta.isDemo = true;
        data.meta.source = data.meta.source || MOCK_URL;
        _db = data;
        return _db;
      });
  }

  var MockAPI = {
    getAll: function () {
      return delay().then(loadDB).then(clone);
    },
    get: function (resource) {
      return delay().then(loadDB).then(function (db) {
        var key = resource;
        if (db[key] === undefined) {
          var err = new Error('unknown resource: ' + resource);
          err.status = 404;
          throw err;
        }
        return clone({ meta: db.meta, resource: key, data: db[key] });
      });
    },
    patch: function (resource, body) {
      // Mock store is read-only: apply in-memory only, mirroring the
      // real backend's read-only-filesystem behavior on Vercel.
      return delay().then(loadDB).then(function (db) {
        return clone({ meta: db.meta, persisted: false, warning: 'Offline mock store — changes are not persisted.' });
      });
    },
    propAccount: function () {
      return delay().then(function () {
        throw new Error('Live broker feed unavailable offline');
      });
    },
    /** Returns only the extra sections the live backend doesn't serve yet. */
    getExtended: function () {
      return loadDB().then(function (db) {
        var out = {};
        ['intelligence', 'chartAnalyses', 'auditLog', 'fingerprint', 'sentinel'].forEach(function (k) {
          if (db[k] !== undefined) out[k] = clone(db[k]);
        });
        return out;
      });
    }
  };

  global.MockAPI = MockAPI;
})(typeof window !== 'undefined' ? window : this);
