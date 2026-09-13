/* ============================================================
   snipertrader.ai — Command Portal · admin.js
   ------------------------------------------------------------
   Application logic for /admin.html. Mirrors the marketing site's
   shell (scope cursor, nav dropdowns, ticker, theme toggle) and
   drives the 10 Command Portal sections with honest three-state
   data handling (skeleton → data / empty / error).

   Data service: SniperAPI (real /api/admin/*) with MockAPI fallback
   (/assets/data/mock-data.json). Sections the backend doesn't serve
   yet (intelligence, chart analyses, audit log, device fingerprint)
   are merged from the mock store and clearly badged SIMULATION.
   ============================================================ */
(function () {
  'use strict';

  /* ──────────────────────────────────────────────────────────
     Inline SVG icon set (decorative — aria-hidden + adjacent text)
     ────────────────────────────────────────────────────────── */
  var ICONS = {
    grid: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
    pulse: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 12h4l2.5-6 4 12 2.5-6H21"/></svg>',
    list: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 6h12M9 12h12M9 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/></svg>',
    checkSquare: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="m8.5 12.5 2.5 2.5 5-5.5"/></svg>',
    chart: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 20h18"/><path d="M5 16l4-4 3 2 5-6 3 2"/></svg>',
    shield: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3l7 3v5.5c0 4.6-3 8.2-7 9.5-4-1.3-7-4.9-7-9.5V6z"/><path d="m9 12 2 2 4-4"/></svg>',
    heart: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 21C7.5 16.7 3 13 3 8.6A4.6 4.6 0 0 1 12 5.5 4.6 4.6 0 0 1 21 8.6C21 13 16.5 16.7 12 21z"/></svg>',
    bank: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 9.5 12 4l9 5.5"/><path d="M4 10v9M9 10v9M15 10v9M20 10v9"/><path d="M2 21h20"/></svg>',
    key: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="8" cy="15" r="4.5"/><path d="m11.5 11.5 8-8M15.5 7.5l2 2M18.5 4.5l1 1"/></svg>',
    user: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c.8-3.6 3.8-5.5 7.5-5.5s6.7 1.9 7.5 5.5"/></svg>',
    lock: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/></svg>',
    bell: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 9a6 6 0 0 1 12 0c0 5 1.7 6 1.7 6H4.3S6 14 6 9"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>',
    sun: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    moon: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
    logout: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg>',
    download: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3v12M6 11l6 6 6-6"/><path d="M4 21h16"/></svg>',
    export: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M7 17 17 7M9 7h8v8"/></svg>',
    chevronDown: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m6 9 6 6 6-6"/></svg>',
    external: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m5 13 4 4L19 7"/></svg>',
    x: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    alert: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3 2 20h20z"/><path d="M12 9v5M12 17h.01"/></svg>',
    eye: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    eyeOff: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2 12s3.5-7 10-7c2 0 3.8.7 5.3 1.8"/><path d="M6.2 6.2C3.6 7.8 2 12 2 12s3.5 7 10 7c1.9 0 3.6-.6 5-1.5"/><path d="m3 3 18 18"/><path d="M9.9 9.9A3 3 0 0 0 14 14"/></svg>',
    fingerprint: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 11a4 4 0 0 0-4 4c0 2 .8 3.6 1.5 5.2"/><path d="M12 7a8 8 0 0 0-8 8c0 1.5.3 2.8.7 4"/><path d="M12 3a12 12 0 0 0-12 12"/><path d="M15.5 14.5A4 4 0 0 0 16 15c0 2 .8 3.6 1.5 5.2"/><path d="M16 7a8 8 0 0 1 6.9 4"/></svg>',
    card: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>',
    phone: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18h2"/></svg>',
    file: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>',
    link: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2"/></svg>',
    users: '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
  };

  function icon(name) { return ICONS[name] || ''; }

  /* ──────────────────────────────────────────────────────────
     Sidebar config — sections mapped to product pillars
     ────────────────────────────────────────────────────────── */
  var SECTIONS = [
    { id: 'overview', label: 'Overview', icon: 'grid', solo: true },
    { group: 'Market Intelligence Engine', items: [
      { id: 'intelligence', label: 'Intelligence Feed', icon: 'pulse' },
      { id: 'signals', label: 'Signal Log', icon: 'list' },
      { id: 'preflight', label: 'Pre-Flight Status', icon: 'checkSquare' },
      { id: 'analyses', label: 'Chart Analysis History', icon: 'chart' }
    ]},
    { group: 'Psychology Gate', items: [
      { id: 'discipline', label: 'Discipline Dashboard', icon: 'heart' }
    ]},
    { group: 'Capital & Access', items: [
      { id: 'propfirms', label: 'Prop Firm Command Center', icon: 'bank' },
      { id: 'license', label: 'License & Billing', icon: 'key' },
      { id: 'sentinel', label: 'Sentinel Affiliate Program', icon: 'users' }
    ]},
    { group: 'Account', items: [
      { id: 'profile', label: 'Trader Profile', icon: 'user' },
      { id: 'security', label: 'Security', icon: 'lock' }
    ]}
  ];

  /* ──────────────────────────────────────────────────────────
     Utilities
     ────────────────────────────────────────────────────────── */
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };
  var fmtMoney = function (n) {
    n = Number(n) || 0;
    return (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  var pnlClass = function (n) { n = Number(n) || 0; return n > 0 ? 'var(--emerald)' : (n < 0 ? 'var(--red)' : 'var(--text2)'); };
  var pnlText = function (n) { n = Number(n) || 0; return (n > 0 ? '+' : '') + fmtMoney(n); };

  function skeletonHTML(rows) {
    var out = '';
    for (var i = 0; i < rows; i++) out += '<div class="sk-row skeleton"></div>';
    return out;
  }
  function showEmpty(id, msg, ctaHTML) {
    var el = $(id); if (!el) return;
    el.innerHTML = '<div class="dash-empty"><b>' + esc(msg) + '</b>' + (ctaHTML ? '<div class="cta">' + ctaHTML + '</div>' : '') + '</div>';
  }
  function showError(id, msg) {
    var el = $(id); if (!el) return;
    console.error('[CommandPortal] error:', msg);
    el.innerHTML = '<div class="dash-error">Connection interrupted. ' + esc(msg) +
      '<div class="err-detail">Retry or contact support.</div>' +
      '<div class="cta"><button class="action-btn primary" data-action="retry">Retry</button></div></div>';
  }
  function badge(text, cls) {
    return '<span class="badge ' + esc(cls || '') + '">' + esc(text) + '</span>';
  }

  /* ──────────────────────────────────────────────────────────
     State
     ────────────────────────────────────────────────────────── */
  var State = {
    data: null,
    current: 'overview',
    simulated: {},           // sections served from the mock store (badged SIMULATION)
    sigPage: 0,
    sigFilter: 'all',
    PAGE_SIZE: 6,
    piiRevealed: false,
    audit: []               // in-memory audit log (also mirrored to localStorage)
  };

  var AUDIT_KEY = 'st_admin_audit';
  function loadAudit() {
    try { State.audit = JSON.parse(localStorage.getItem(AUDIT_KEY) || '[]'); } catch (e) { State.audit = []; }
  }
  function persistAudit() {
    try { localStorage.setItem(AUDIT_KEY, JSON.stringify(State.audit.slice(0, 40))); } catch (e) {}
  }
  function logAudit(action, detail) {
    var entry = { id: 'au' + Date.now(), actor: 'Jaylu', action: action, detail: detail || '', when: new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) + ' ET' };
    State.audit.unshift(entry);
    persistAudit();
    console.info('[audit]', action, detail);
    renderAudit();
  }

  /* ──────────────────────────────────────────────────────────
     Data service (real API → mock fallback → merge extras)
     ────────────────────────────────────────────────────────── */
  function loadAll() {
    return (window.SniperAPI ? SniperAPI.getAll() : Promise.reject(new Error('no api client')))
      .then(function (data) {
        // Real backend is up. Fill the sections it doesn't serve yet from the mock store.
        data = data || {};
        return (window.MockAPI ? MockAPI.getExtended() : Promise.resolve({}))
          .then(function (extras) {
            Object.keys(extras || {}).forEach(function (k) {
              if (data[k] === undefined) { data[k] = extras[k]; State.simulated[k] = true; }
            });
            data.meta = data.meta || {};
            data.meta.isDemo = !!data.meta.isDemo;
            return data;
          })
          .catch(function () { return data; });
      })
      .catch(function (e) {
        // Backend unreachable — fall back to the mock store entirely.
        console.warn('[CommandPortal] admin service unreachable, using mock data:', e.message);
        return (window.MockAPI ? MockAPI.getAll() : Promise.reject(e)).then(function (mock) {
          ['intelligence', 'chartAnalyses', 'auditLog', 'fingerprint', 'preflights', 'sentinel'].forEach(function (k) {
            if (mock[k] !== undefined) State.simulated[k] = true;
          });
          mock.meta = mock.meta || {};
          mock.meta.isDemo = true;
          return mock;
        });
      });
  }

  function isSimulated(key) { return !!State.simulated[key]; }
  function simFlag() {
    return '<span class="demo-flag">' + icon('pulse') + ' SIMULATION</span>';
  }

  /* ──────────────────────────────────────────────────────────
     Shell: scope cursor, theme, nav, ticker, sidebar
     ────────────────────────────────────────────────────────── */
  function initScopeCursor() {
    var scope = $('scope'), ring = $('scope-ring'), dot = $('scope-dot');
    if (!scope || !ring) return;
    var mx = innerWidth / 2, my = innerHeight / 2, rx = mx, ry = my;
    document.addEventListener('mousemove', function (e) {
      mx = e.clientX; my = e.clientY;
      if (dot) { dot.style.left = mx + 'px'; dot.style.top = my + 'px'; }
      if (scope) { scope.style.left = mx + 'px'; scope.style.top = my + 'px'; }
    });
    (function loop() {
      rx += (mx - rx) * 0.16; ry += (my - ry) * 0.16;
      if (ring) { ring.style.left = rx + 'px'; ring.style.top = ry + 'px'; }
      requestAnimationFrame(loop);
    })();
  }

  function initTheme() {
    var light = false;
    var btns = [];
    ['themeBtn', 'themeBtnLogin'].forEach(function (id) { var b = $(id); if (b) btns.push(b); });
    function apply(l) {
      light = l;
      document.body.classList.toggle('light', l);
      btns.forEach(function (btn) {
        btn.innerHTML = (l ? icon('sun') : icon('moon')) + '<span>' + (l ? 'Dark' : 'Light') + '</span>';
      });
    }
    btns.forEach(function (btn) { btn.addEventListener('click', function () { apply(!light); }); });
    apply(false);
  }

  function initNavDropdowns() {
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest('[data-drop]');
      var inside = e.target.closest('.nav-item');
      document.querySelectorAll('.nav-item.open').forEach(function (item) {
        if (!trigger || item !== trigger.closest('.nav-item')) item.classList.remove('open');
      });
      if (trigger) {
        var item = trigger.closest('.nav-item');
        if (item) item.classList.toggle('open');
      }
    });
    var burger = $('burger'), menu = $('mobileMenu');
    if (burger && menu) burger.addEventListener('click', function () { menu.classList.toggle('open'); });
  }

  function initTicker() {
    var TSTATE = {
      'BTC/USD': { p: 67224, c: 2.14 }, 'ETH/USD': { p: 3811, c: 1.52 }, 'SOL/USD': { p: 168.4, c: 2.01 },
      'XRP/USD': { p: 0.5124, c: 1.38 }, 'XAU/USD': { p: 2341.8, c: -0.12 }, 'EUR/USD': { p: 1.0834, c: -0.08 },
      'GBP/USD': { p: 1.2718, c: 0.11 }, 'USD/JPY': { p: 157.42, c: 0.14 }, 'SPX': { p: 5847.2, c: 0.31 },
      'NDX': { p: 21247, c: 0.68 }, 'VIX': { p: 13.42, c: -5.35 }, 'DXY': { p: 104.18, c: 0.18 }
    };
    var ORDER = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'XRP/USD', 'XAU/USD', 'EUR/USD', 'GBP/USD', 'USD/JPY', 'SPX', 'NDX', 'VIX', 'DXY'];
    function fmt(p, sym) {
      if (sym === 'BTC/USD') return '$' + Math.round(p).toLocaleString();
      if (sym === 'ETH/USD' || sym === 'SOL/USD') return '$' + p.toFixed(2);
      if (sym === 'XRP/USD' || sym === 'EUR/USD' || sym === 'GBP/USD') return p.toFixed(4);
      return p.toFixed(2);
    }
    function render() {
      var el = $('tickerInner'); if (!el) return;
      var keys = ORDER.filter(function (k) { return TSTATE[k] && TSTATE[k].p > 0; });
      var d = keys.concat(keys);
      el.innerHTML = d.map(function (s) {
        var o = TSTATE[s], up = o.c >= 0;
        return '<div class="tick-item"><span class="t-sym">' + s + '</span><span class="t-price">' + fmt(o.p, s) + '</span><span class="' + (up ? 't-up' : 't-dn') + '">' + (up ? '+' : '') + o.c.toFixed(2) + '%</span></div>';
      }).join('');
      el.style.animation = 'none'; void el.offsetWidth; el.style.animation = '';
    }
    render();
    try {
      var ws = new WebSocket('wss://stream.binance.com:9443/stream?streams=btcusdt@miniTicker/ethusdt@miniTicker/solusdt@miniTicker/xrpusdt@miniTicker');
      var MAP = { BTCUSDT: 'BTC/USD', ETHUSDT: 'ETH/USD', SOLUSDT: 'SOL/USD', XRPUSDT: 'XRP/USD' };
      ws.onmessage = function (e) {
        try { var d = JSON.parse(e.data).data; var l = MAP[d.s]; if (l && TSTATE[l]) { var p = parseFloat(d.c), o = parseFloat(d.o); if (p > 0 && o > 0) { TSTATE[l].p = p; TSTATE[l].c = (p - o) / o * 100; render(); } } } catch (err) {}
      };
    } catch (e) {}
    function stooq() {
      var syms = { spx: 'SPX', ndx: 'NDX', vix: 'VIX', dxy: 'DXY', xauusd: 'XAU/USD' };
      Object.keys(syms).forEach(function (s) {
        fetch('https://stooq.com/q/l/?s=' + s + '&f=sd2t2ohlcv&h&e=csv', { cache: 'no-store' })
          .then(function (r) { return r.text(); })
          .then(function (t) { var l = t.trim().split('\n'); if (l.length < 2) return; var c = l[1].split(','); var o = parseFloat(c[3]), cl = parseFloat(c[6]); if (cl > 0 && o > 0 && TSTATE[syms[s]]) { TSTATE[syms[s]].p = cl; TSTATE[syms[s]].c = (cl - o) / o * 100; } })
          .catch(function () {});
      });
    }
    stooq(); setInterval(stooq, 30000);
  }

  function buildSidebar() {
    var el = $('sidebar'); if (!el) return;
    var html = '';
    SECTIONS.forEach(function (sec) {
      if (sec.solo) {
        html += '<a class="sidebar-link" data-section="' + sec.id + '" href="#panel-' + sec.id + '">' + icon(sec.icon) + '<span>' + esc(sec.label) + '</span></a>';
      } else {
        html += '<div class="sidebar-group">' +
          '<button class="sidebar-group-label" data-group-toggle aria-expanded="true">' + esc(sec.group) + '<span class="sg-caret">' + icon('chevronDown') + '</span></button>' +
          '<div class="sidebar-group-body">';
        sec.items.forEach(function (it) {
          html += '<a class="sidebar-link" data-section="' + it.id + '" href="#panel-' + it.id + '">' + icon(it.icon) + '<span>' + esc(it.label) + '</span></a>';
        });
        html += '</div></div>';
      }
    });
    el.innerHTML = html;

    // group collapse toggles
    el.querySelectorAll('[data-group-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var group = btn.closest('.sidebar-group');
        var collapsed = group.classList.toggle('collapsed');
        btn.setAttribute('aria-expanded', String(!collapsed));
      });
    });
  }

  /* ──────────────────────────────────────────────────────────
     Section navigation
     ────────────────────────────────────────────────────────── */
  var TITLES = {
    overview: 'Command Portal',
    intelligence: 'Intelligence Feed',
    signals: 'Signal Log',
    preflight: 'Pre-Flight Status',
    analyses: 'Chart Analysis History',
    discipline: 'Discipline Dashboard',
    propfirms: 'Prop Firm Command Center',
    license: 'License & Billing',
    sentinel: 'Sentinel Affiliate Program',
    profile: 'Trader Profile',
    security: 'Security'
  };

  function showSection(id) {
    if (id === State.current && $('panel-' + id) && $('panel-' + id).classList.contains('active')) return;
    State.current = id;
    document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('active'); });
    var panel = $('panel-' + id);
    if (panel) panel.classList.add('active');
    document.querySelectorAll('.sidebar-link').forEach(function (l) {
      l.classList.toggle('active', l.getAttribute('data-section') === id);
    });
    var crumb = $('crumbCurrent'); if (crumb) crumb.textContent = TITLES[id] || id;
    var ann = $('srAnnounce'); if (ann) ann.textContent = 'Navigated to ' + (TITLES[id] || id);
    if (window.innerWidth < 1080) {
      var m = $('mobileMenu'); if (m) m.classList.remove('open');
    }
  }

  /* ──────────────────────────────────────────────────────────
     Live prop-account telemetry (graceful — never fabricated)
     ────────────────────────────────────────────────────────── */
  function refreshLiveAccount() {
    var banner = $('liveBanner'), msg = $('liveMsg');
    if (!banner || !msg) return;
    banner.style.display = 'flex'; banner.classList.add('refreshing');
    msg.textContent = 'Connecting to live broker feed…';
    var done = function (html, err) {
      banner.classList.remove('refreshing');
      if (err) banner.classList.add('lb-err'); else banner.classList.remove('lb-err');
      msg.innerHTML = html;
    };
    if (!window.SniperAPI) { done('<span class="lb-err">Live broker feed unavailable.</span>', true); return; }
    SniperAPI.propAccount()
      .then(function (d) {
        if (d && d.error) throw new Error(d.error);
        var a = d.account || {};
        var eq = Number(a.equity || 0), bp = Number(a.buying_power || 0), dpl = Number(a.day_pnl || 0);
        var pos = (d.positions || []).length, ord = (d.orders || []).length;
        done('<b>LIVE · Alpaca ' + esc(a.status || 'paper') + '</b> — Equity ' + fmtMoney(eq) +
          ' · Day P&amp;L <span style="color:' + pnlClass(dpl) + '">' + pnlText(dpl) + '</span> · Buying power ' + fmtMoney(bp) +
          ' · ' + pos + ' positions · ' + ord + ' orders', false);
      })
      .catch(function (e) {
        done('<span class="lb-err">Live broker feed unavailable — ' + esc(e.message) + '.</span> The figures below are labeled demo data.', true);
      });
  }

  function refreshPropLiveTile() {
    var body = $('pfLiveBody'), meta = $('pfLiveMeta');
    if (!body) return;
    body.classList.add('refreshing'); if (meta) meta.textContent = '';
    if (!window.SniperAPI) {
      body.classList.remove('refreshing'); body.classList.add('lb-err');
      body.innerHTML = '<div class="pf-live-foot" style="color:var(--red)">Live broker feed unavailable — accounts below are demo data.</div>';
      if (meta) meta.textContent = 'OFFLINE';
      return;
    }
    SniperAPI.propAccount()
      .then(function (d) {
        if (d && d.error) throw new Error(d.error);
        var a = d.account || {};
        var eq = Number(a.equity || 0), bp = Number(a.buying_power || 0), dpl = Number(a.day_pnl || 0);
        var pos = (d.positions || []).length, ord = (d.orders || []).length;
        body.classList.remove('refreshing', 'lb-err');
        body.innerHTML = '<div class="pf-live-grid">' +
          '<div class="pf-metric"><div class="l">Equity</div><div class="v">' + fmtMoney(eq) + '</div></div>' +
          '<div class="pf-metric"><div class="l">Day P&amp;L</div><div class="v" style="color:' + pnlClass(dpl) + '">' + pnlText(dpl) + '</div></div>' +
          '<div class="pf-metric"><div class="l">Buying Power</div><div class="v">' + fmtMoney(bp) + '</div></div>' +
          '<div class="pf-metric"><div class="l">Positions</div><div class="v">' + pos + ' <span style="font-size:.7rem;color:var(--text4)">· ' + ord + ' orders</span></div></div>' +
          '</div>' +
          '<div class="pf-live-foot">Broker: ' + esc(a.status || 'paper') + ' · Acct …' + esc(String(a.number || '').slice(-4) || '—') + '</div>';
        if (meta) meta.textContent = 'LIVE';
      })
      .catch(function (e) {
        body.classList.remove('refreshing'); body.classList.add('lb-err');
        body.innerHTML = '<div class="pf-live-foot" style="color:var(--red)">Live broker feed unavailable — ' + esc(e.message) + '.</div>';
        if (meta) meta.textContent = 'OFFLINE';
      });
  }

  /* ──────────────────────────────────────────────────────────
     Renderers
     ────────────────────────────────────────────────────────── */
  function renderAll() {
    var d = State.data;
    renderProfile(d.profile);
    renderOverview(d.overview, d.alerts, d.profile);
    renderIntelligence(d.intelligence);
    renderSignals(d.sessions);
    renderPreflight(d.preflights);
    renderAnalyses(d.chartAnalyses);
    renderDiscipline(d.overview, d.modules, d.alerts);
    renderPropFirms(d.propFirms);
    renderLicense(d.licenses, d.billing, d.downloads, d.specialLicenses, d.memberAccess);
    renderSentinel(d.sentinel);
    renderProfileForm(d.profile, d.notifications);
    renderSecurity(d.security, d.fingerprint);
    refreshLiveAccount();
    refreshPropLiveTile();
    renderBell(d.notifications);
    var df = $('demoFlag'); if (df) df.style.display = (d.meta && d.meta.isDemo) ? 'inline-flex' : 'none';
  }

  function renderProfile(p) {
    if (!p) return;
    var name = p.displayName || 'Trader';
    var wn = $('navName'); if (wn) wn.textContent = name;
    var av = $('navAvatar'); if (av) av.textContent = name.split(/\s+/).map(function (s) { return s[0]; }).join('').slice(0, 2).toUpperCase();
    var welcome = $('welcomeName'); if (welcome) welcome.textContent = name + '.';
    var sub = $('welcomeSub');
    if (sub) sub.textContent = 'Precision Suite · Elite license · Last check 06:42 EST';
  }

  function renderOverview(o, alerts, profile) {
    if (!o) { showError('statRow', 'Overview data unavailable.'); return; }
    var stats = [
      { v: o.sessionsCompleted, l: 'Sessions Completed', c: 'var(--cyan)', s: 'live', sCls: 'up' },
      { v: o.avgDisciplineScore + '%', l: 'Avg Discipline Score', c: 'var(--emerald)', s: 'live', sCls: 'up' },
      { v: o.dayStreak, l: 'Day Streak', c: 'var(--gold)', s: 'consecutive', sCls: 'nt' },
      { v: o.breachEvents, l: 'Breach Events', c: 'var(--red)', s: 'reviewed', sCls: 'dn' }
    ];
    $('statRow').innerHTML = stats.map(function (s) {
      return '<div class="stat-card"><span class="sc-val" style="color:' + s.c + '">' + esc(s.v) + '</span>' +
        '<span class="sc-label">' + esc(s.l) + '</span><span class="sc-change ' + s.sCls + '">' + esc(s.s) + '</span></div>';
    }).join('');

    // weekly activity
    var chart = $('activityChart');
    var arr = Array.isArray(o.weeklyActivity) ? o.weeklyActivity : [0, 0, 0, 0, 0, 0, 0];
    var max = Math.max(1, arr.reduce(function (a, b) { return Math.max(a, b); }, 0));
    var labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    chart.innerHTML = arr.map(function (h, i) {
      return '<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;">' +
        '<div style="width:100%;height:' + Math.round(h / max * 120) + 'px;background:' + (i === 3 ? 'var(--gold)' : 'var(--emerald-dim)') + ';border-radius:6px 6px 0 0;"></div>' +
        '<span style="font-family:var(--ff-m);font-size:.62rem;color:var(--text4)">' + labels[i] + '</span></div>';
    }).join('');
    chart.setAttribute('role', 'img');
    chart.setAttribute('aria-label', 'Weekly session activity, ' + arr.join(', '));

    // neural readiness
    var nr = $('neuralReadiness');
    if (o.neuralReadiness) {
      var wks = o.neuralReadiness.weeks || [], cur = o.neuralReadiness.current || 0;
      var m = Math.max(1, cur, wks.reduce(function (a, b) { return Math.max(a, b); }, 0));
      nr.innerHTML = '<div style="display:flex;align-items:flex-end;gap:6px;height:64px;">' +
        wks.map(function (v, i) {
          return '<div style="flex:1;height:' + Math.round(v / m * 100) + '%;background:' + (i === wks.length - 1 ? 'var(--emerald)' : 'var(--emerald-dim)') + ';border-radius:4px 4px 0 0;"></div>';
        }).join('') +
        '</div>' +
        '<div style="display:flex;justify-content:space-between;font-family:var(--ff-m);font-size:.62rem;color:var(--text4);margin-top:6px;">' +
        '<span>Wk1</span><span>Wk2</span><span>Wk3</span><span>Wk4</span></div>' +
        '<div style="font-family:var(--ff-d);font-size:1.8rem;font-weight:600;color:var(--emerald);margin-top:8px;">' + esc(cur) + ' <span style="font-size:.9rem;color:var(--text3)">/ 100</span></div>';
    } else {
      nr.innerHTML = '';
    }

    // recent alerts
    renderAlerts('alertsList', alerts);
  }

  function renderAlerts(id, list) {
    var el = $(id); if (!el) return;
    if (!Array.isArray(list) || !list.length) {
      showEmpty(id, 'No alerts in the last 7 days.', '<a class="action-btn primary" href="/prerun_detection.html">Run Pre-Market Scan</a>');
      return;
    }
    el.innerHTML = list.map(function (a) {
      var color = { red: 'var(--red)', gold: 'var(--gold)', green: 'var(--emerald)', cyan: 'var(--cyan)' }[a.level] || 'var(--cyan)';
      return '<div class="alert-item" style="display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;">' +
        '<span class="ai-dot" style="width:8px;height:8px;border-radius:50%;background:' + color + ';flex-shrink:0;"></span>' +
        '<span class="ai-text" style="flex:1;font-size:.86rem;color:var(--text2)">' + esc(a.text) + '</span>' +
        '<span class="ai-time" style="font-family:var(--ff-m);font-size:.68rem;color:var(--text4);flex-shrink:0">' + esc(a.time || '') + '</span></div>';
    }).join('');
  }

  function renderIntelligence(intel) {
    var el = $('intelBody'); if (!el) return;
    if (!intel || !Array.isArray(intel.bias) || !intel.bias.length) {
      showEmpty('intelBody', 'No live bias scores yet.', '<a class="action-btn primary" href="/market_terminal.html">Open Market Terminal</a>');
      return;
    }
    var flag = isSimulated('intelligence') ? '<div style="margin-bottom:14px">' + simFlag() + ' <span style="font-family:var(--ff-m);font-size:.72rem;color:var(--text4);margin-left:8px">Updated ' + esc(intel.updated || '') + '</span></div>' : '';
    var bias = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('pulse') + '</div><div><div class="gph-title">Live Bias Scores</div><div class="gph-sub">Directional conviction per market</div></div></div></div><div class="bias-grid">' +
      intel.bias.map(function (b) {
        var cls = b.score > 25 ? 'pos' : (b.score < -25 ? 'neg' : 'nt');
        var biasCls = b.bias === 'Bullish' ? 'sage' : (b.bias === 'Bearish' ? 'red' : 'gold');
        return '<div class="bias-card"><div class="bc-top"><span class="bc-sym">' + esc(b.market) + '</span><span class="tag ' + biasCls + '">' + esc(b.bias) + '</span></div>' +
          '<div class="bc-score ' + cls + '">' + (b.score > 0 ? '+' : '') + esc(b.score) + '</div>' +
          '<div class="bc-note">' + esc(b.note) + '</div></div>';
      }).join('') + '</div></div>';

    var levels = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('chart') + '</div><div><div class="gph-title">Key Levels</div><div class="gph-sub">Mapped liquidity &amp; structure</div></div></div></div><div class="level-list">' +
      (intel.keyLevels || []).map(function (k) {
        return '<div class="level-item"><span class="lv-sym">' + esc(k.sym) + '</span><span class="lv-level">' + esc(k.level) + '</span><span class="lv-type">' + esc(k.type) + '</span><span class="lv-dir ' + esc(k.dir) + '">' + esc(k.dir) + '</span></div>';
      }).join('') + '</div></div>';

    var cats = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon r">' + icon('alert') + '</div><div><div class="gph-title">Catalyst Calendar</div><div class="gph-sub">High-impact events on the horizon</div></div></div></div><div class="catalyst-list">' +
      (intel.catalysts || []).map(function (c) {
        return '<div class="catalyst-item"><span class="cat-date">' + esc(c.date) + '</span><span class="cat-event">' + esc(c.event) + '</span><span class="cat-time">' + esc(c.time) + ' · ' + esc(c.impact) + '</span></div>';
      }).join('') + '</div></div>';

    el.innerHTML = flag + bias + levels + cats;
  }

  function renderSignals(sessions) {
    var body = $('signalsBody'), pager = $('signalsPager'), count = $('signalsCount');
    if (!body) return;
    var list = Array.isArray(sessions) ? sessions : [];
    if (!list.length) {
      showEmpty('signalsWrap', 'No signals logged yet.', '<a class="action-btn primary" href="/market_terminal.html">Open Market Terminal</a>');
      return;
    }
    var filtered = list;
    if (State.sigFilter !== 'all') filtered = list.filter(function (s) { return String(s.module).toUpperCase() === State.sigFilter; });
    var pages = Math.max(1, Math.ceil(filtered.length / State.PAGE_SIZE));
    if (State.sigPage >= pages) State.sigPage = 0;
    var start = State.sigPage * State.PAGE_SIZE;
    var pageItems = filtered.slice(start, start + State.PAGE_SIZE);

    body.innerHTML = pageItems.map(function (s) {
      var pnl = Number(s.pnl || 0);
      var statusCls = String(s.status || '').toUpperCase() === 'BREACH' ? 'inactive' : 'active';
      return '<tr>' +
        '<td style="font-family:var(--ff-m);font-size:.78rem;color:var(--text3)">' + esc(s.date) + '</td>' +
        '<td>' + badge(s.module, 'pro') + '</td>' +
        '<td style="font-family:var(--ff-m);font-size:.82rem">' + esc(s.market) + '</td>' +
        '<td style="font-family:var(--ff-m);font-size:.85rem;font-weight:700;color:' + pnlClass(pnl) + '">' + pnlText(pnl) + '</td>' +
        '<td><span style="display:inline-flex;width:28px;height:28px;border-radius:50%;align-items:center;justify-content:center;font-family:var(--ff-m);font-size:.74rem;font-weight:700;color:' + pnlClass(pnl) + ';background:var(--card2);border:1px solid var(--border)">' + esc(s.score) + '</span></td>' +
        '<td style="font-size:.82rem;color:var(--text2)">' + esc(s.trigger) + '</td>' +
        '<td>' + badge(s.status, statusCls) + '</td>' +
        '<td><button class="action-btn cyan" data-action="review-signal" data-id="' + esc(s.id) + '">' + icon('eye') + ' Review</button></td></tr>';
    }).join('');

    if (count) count.textContent = filtered.length + ' signals';
    if (pager) {
      pager.innerHTML = '<button class="action-btn gold" data-action="sig-prev" ' + (State.sigPage === 0 ? 'disabled aria-disabled="true"' : '') + '>← Prev</button>' +
        '<span style="font-family:var(--ff-m);font-size:.72rem;color:var(--text3);padding:0 10px">Page ' + (State.sigPage + 1) + ' of ' + pages + '</span>' +
        '<button class="action-btn gold" data-action="sig-next" ' + (State.sigPage >= pages - 1 ? 'disabled aria-disabled="true"' : '') + '>Next →</button>';
    }
  }

  function renderPreflight(preflights) {
    var el = $('preflightBody'); if (!el) return;
    var list = Array.isArray(preflights) ? preflights : [];
    var pf = list[list.length - 1];
    if (!pf) {
      showEmpty('preflightBody', 'No pre-flight scan logged for today.',
        '<a class="action-btn primary" href="/prerun_detection.html">Run Pre-Market Scan</a>');
      return;
    }
    var nb = pf.neuralBaseline || {};
    var gates = pf.gates || [];
    var passed = gates.filter(function (g) { return g.passed; }).length;
    var sim = isSimulated('preflights') || isSimulated('preflight');
    var flag = sim ? '<div style="margin-bottom:14px">' + simFlag() + '</div>' : '';

    var baseline = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('heart') + '</div><div><div class="gph-title">Neural Baseline</div><div class="gph-sub">Readiness logged ' + esc(pf.updated || '') + '</div></div></div></div>' +
      '<div class="stats-row" style="margin-bottom:0">' +
      statBox('Score', nb.score + '/100', 'var(--emerald)') +
      statBox('Stress', nb.stress, 'var(--cyan)') +
      statBox('Sleep', nb.sleep, 'var(--gold)') +
      statBox('Focus', nb.focus, 'var(--emerald)') +
      '</div></div>';

    var gateList = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('checkSquare') + '</div><div><div class="gph-title">Discipline Gates</div><div class="gph-sub">' + passed + ' of ' + gates.length + ' cleared</div></div></div></div><div class="gate-list">' +
      gates.map(function (g) {
        return '<div class="gate-item ' + (g.passed ? 'passed' : 'failed') + '"><span class="gate-dot"></span><span class="gate-name">' + esc(g.name) + '</span><span class="gate-state">' + (g.passed ? 'Cleared' : 'Blocked') + '</span></div>';
      }).join('') + '</div></div>';

    var auth = '<div class="authorize-strip">' +
      '<span style="font-family:var(--ff-d);font-size:1.2rem;font-weight:600;color:' + (pf.authorized ? 'var(--emerald)' : 'var(--red)') + '">' + (pf.authorized ? icon('check') + ' Authorized' : icon('alert') + ' Not Authorized') + '</span>' +
      '<span style="flex:1;font-size:.9rem;color:var(--text2);min-width:200px">' + esc(pf.authorizedBy || '') + '</span>' +
      '<a class="action-btn primary" href="/traderedge_preflight.html">' + icon('external') + ' Launch Protocol</a></div>';

    el.innerHTML = flag + baseline + gateList + auth;
  }

  function statBox(l, v, c) {
    return '<div class="stat-card" style="margin-bottom:0"><span class="sc-val" style="font-size:1.5rem;color:' + c + '">' + esc(v) + '</span><span class="sc-label">' + esc(l) + '</span></div>';
  }

  function renderAnalyses(list) {
    var el = $('analysesBody'); if (!el) return;
    if (!Array.isArray(list) || !list.length) {
      showEmpty('analysesBody', 'No saved analyses yet. Open a chart to generate one.',
        '<a class="action-btn primary" href="https://chart-ai.snipertrader.ai" target="_blank" rel="noopener">' + icon('external') + ' Open Chart AI</a>');
      return;
    }
    var flag = isSimulated('chartAnalyses') ? '<div style="margin-bottom:14px">' + simFlag() + '</div>' : '';
    el.innerHTML = flag + '<div class="analysis-grid">' + list.map(function (a) {
      var biasCls = a.bias === 'Bullish' ? 'sage' : (a.bias === 'Bearish' ? 'red' : 'gold');
      return '<div class="analysis-card"><div class="an-top"><span class="an-sym">' + esc(a.sym) + '</span><span class="tag ' + biasCls + '">' + esc(a.bias) + '</span></div>' +
        '<div class="an-tf">' + esc(a.timeframe) + ' timeframe</div>' +
        '<div class="an-flags">' + (a.flags || []).map(function (f) { return '<span class="tag">' + esc(f) + '</span>'; }).join('') + '</div>' +
        '<div class="an-meta">Saved ' + esc(a.savedAt) + '</div>' +
        '<a class="action-btn cyan" href="' + esc(a.openHref || 'https://chart-ai.snipertrader.ai') + '" target="_blank" rel="noopener">' + icon('external') + ' Re-open analysis</a></div>';
    }).join('') + '</div>';
  }

  function renderDiscipline(overview, modules, alerts) {
    var el = $('disciplineBody'); if (!el) return;
    if (!overview) { showError('disciplineBody', 'Discipline data unavailable.'); return; }
    var streak = Number(overview.dayStreak || 0);
    var psych = Number(overview.avgDisciplineScore || 0);
    var breach = Number(overview.breachEvents || 0);
    var milestones = [7, 14, 30, 60];

    var circ = 2 * Math.PI * 52;
    var pct = Math.min(100, psych);

    var streakHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('heart') + '</div><div><div class="gph-title">Discipline Streak</div><div class="gph-sub">Consecutive sessions without a breach</div></div></div></div>' +
      '<div class="streak-wrap"><div class="streak-ring">' +
      '<svg width="120" height="120" viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" fill="none" stroke="var(--card2)" stroke-width="8"/><circle cx="60" cy="60" r="52" fill="none" stroke="var(--gold)" stroke-width="8" stroke-linecap="round" stroke-dasharray="' + circ + '" stroke-dashoffset="' + (circ * (1 - streak / 60)) + '"/></svg>' +
      '<div class="sr-num"><b>' + streak + '</b><span>day streak</span></div></div>' +
      '<div style="flex:1;min-width:220px"><div class="eyebrow" style="margin-bottom:12px">Milestones</div><div class="milestones">' +
      milestones.map(function (m) { return '<span class="milestone ' + (streak >= m ? 'hit' : '') + '">' + (streak >= m ? '✓ ' : '') + m + 'd</span>'; }).join('') +
      '</div><p style="font-size:.86rem;color:var(--text3);margin-top:14px;line-height:1.6">' + (breach > 0 ? 'Breach events this cycle: ' + breach + '. Review flagged sessions to protect the streak.' : 'No breach events this cycle. Discipline is holding.') + '</p></div></div></div>';

    var psychHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('pulse') + '</div><div><div class="gph-title">Psychology Score</div><div class="gph-sub">4-week rolling average</div></div></div></div>' +
      '<div style="display:flex;align-items:center;gap:20px"><span style="font-family:var(--ff-d);font-size:3rem;font-weight:600;color:var(--emerald)">' + psych + '</span>' +
      '<div style="flex:1;height:10px;border-radius:6px;background:var(--bg3);overflow:hidden"><div style="width:' + pct + '%;height:100%;background:linear-gradient(90deg,var(--emerald),var(--gold));border-radius:6px"></div></div></div>' +
      '<p style="font-size:.82rem;color:var(--text3);margin-top:12px">' + (psych >= 80 ? 'Neural baseline is holding steady. Authorized for full size.' : psych >= 60 ? 'Baseline within range. Consider a reduced-risk session.' : 'Baseline degraded — run the Pre-Flight Protocol before trading.') + '</p></div>';

    var mods = (Array.isArray(modules) && modules.length) ? '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('grid') + '</div><div><div class="gph-title">Module Discipline</div><div class="gph-sub">Usage &amp; completion across the suite</div></div></div></div><div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px">' +
      modules.map(function (m) {
        return '<div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px">' +
          '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><span style="font-size:.88rem;font-weight:600">' + esc(m.name) + '</span><span style="font-family:var(--ff-m);font-size:.72rem;color:var(--text4)">' + esc(m.sessions) + ' sessions</span></div>' +
          '<div style="height:5px;background:var(--bg3);border-radius:3px;overflow:hidden"><div style="width:' + esc(m.pct || 0) + '%;height:100%;background:' + esc(m.color) + '"></div></div>' +
          '<div style="font-family:var(--ff-m);font-size:.66rem;color:var(--text4);margin-top:6px">' + esc(m.detail) + '</div></div>';
      }).join('') + '</div></div>' : '';

    // breach warnings from alerts
    var warnings = (Array.isArray(alerts) ? alerts : []).filter(function (a) { return a.level === 'red' || a.level === 'gold'; });
    var warnHTML = warnings.length ? '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon r">' + icon('alert') + '</div><div><div class="gph-title">Breach Warnings</div><div class="gph-sub">Risk flags requiring review</div></div></div></div><div>' +
      warnings.map(function (a) {
        var c = a.level === 'red' ? 'var(--red)' : 'var(--gold)';
        return '<div class="alert-item" style="display:flex;align-items:center;gap:12px;padding:11px 14px;background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:8px"><span style="width:8px;height:8px;border-radius:50%;background:' + c + ';flex-shrink:0"></span><span style="flex:1;font-size:.86rem;color:var(--text2)">' + esc(a.text) + '</span><span style="font-family:var(--ff-m);font-size:.66rem;color:var(--text4)">' + esc(a.time) + '</span></div>';
      }).join('') + '</div></div>' : '';

    el.innerHTML = streakHTML + psychHTML + mods + warnHTML;
  }

  function renderPropFirms(list) {
    var el = $('propFirmsGrid'); if (!el) return;
    if (!Array.isArray(list) || !list.length) {
      showEmpty('propFirmsGrid', 'No prop firm accounts linked yet.', '<a class="action-btn primary" href="/traderedge_prop_firms_command_center.html">Open Command Center</a>');
      return;
    }
    el.innerHTML = list.map(function (p) {
      var status = String(p.status || 'ACTIVE').toLowerCase();
      var dpl = Number(p.dayPnl || 0), eq = Number(p.equity || 0);
      var dd = Number(p.drawdownUsed || 0), ddMax = Number(p.drawdownMax || 0);
      var ddPct = ddMax ? Math.round(dd / ddMax * 100) : 0;
      return '<div class="pf-card' + (status === 'breach' ? ' is-breach' : '') + (status === 'funding' ? ' is-funding' : '') + '">' +
        '<div class="pf-card-top"><div><div class="pf-name">' + esc(p.firm) + '</div><div class="pf-prog">' + esc(p.program || '') + ' · ' + esc(p.phase || '') + '</div></div>' +
        '<span class="pf-status ' + status + '">' + esc(p.status) + '</span></div>' +
        '<div class="pf-alloc">' + esc(p.allocation || '—') + '</div>' +
        '<div class="pf-equity-line"><span>Equity</span><span style="font-family:var(--ff-m);font-weight:700">' + fmtMoney(eq) + '</span></div>' +
        '<div class="pf-metrics"><div class="pf-metric"><div class="l">Day P&amp;L</div><div class="v" style="color:' + pnlClass(dpl) + '">' + pnlText(dpl) + '</div></div>' +
        '<div class="pf-metric"><div class="l">Consistency</div><div class="v" style="color:' + (p.consistency >= 90 ? 'var(--emerald)' : 'var(--gold)') + '">' + esc(p.consistency) + '%</div></div></div>' +
        '<div class="pf-bar-wrap"><div class="pf-bar-label"><span>Phase progress</span><span>' + esc(p.progress || 0) + '%</span></div><div class="pf-bar-track"><div class="pf-bar-fill" style="width:' + esc(p.progress || 0) + '%"></div></div></div>' +
        '<div class="pf-bar-wrap"><div class="pf-bar-label"><span>Drawdown used</span><span>' + ddPct + '%</span></div><div class="pf-bar-track"><div class="pf-bar-fill" style="width:' + ddPct + '%;background:' + (ddPct >= 80 ? 'var(--red)' : 'linear-gradient(90deg,var(--gold),var(--red))') + '"></div></div></div>' +
        '<div class="pf-card-foot"><span>Updated ' + esc(p.lastUpdate || '—') + '</span>' +
        '<button class="action-btn cyan" data-action="cycle-prop" data-id="' + esc(p.id) + '">' + icon('refresh') + ' Cycle</button></div></div>';
    }).join('');
  }

  function renderLicense(licenses, billing, downloads, special, member) {
    var el = $('licenseBody'); if (!el) return;
    var plan = (billing && billing.plan) || 'ELITE LICENSE';
    var price = (billing && billing.price) || '$49/month';
    var feats = (billing && billing.features) || [];

    var planHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('card') + '</div><div><div class="gph-title">Current License</div><div class="gph-sub">Manage your Precision Suite access</div></div></div>' + badge(plan, 'elite') + '</div>' +
      '<div style="background:linear-gradient(135deg,rgba(240,192,64,.08),rgba(0,212,255,.05));border:1px solid rgba(240,192,64,.2);border-radius:12px;padding:20px;margin-bottom:16px">' +
      '<div style="font-family:var(--ff-d);font-size:1.5rem;font-weight:600;color:var(--gold);margin-bottom:6px">' + esc(plan) + '</div>' +
      '<div style="font-family:var(--ff-m);font-size:1.1rem;color:var(--text);margin-bottom:14px">' + esc(price) + '</div>' +
      '<div style="font-size:.84rem;color:var(--text2);line-height:2">' + feats.map(function (f) { return '<div>' + icon('check') + ' ' + esc(f) + '</div>'; }).join('') + '</div></div>' +
      '<div style="display:flex;gap:10px;flex-wrap:wrap"><button class="action-btn gold" data-action="manage-billing">' + icon('card') + ' Manage Billing</button><button class="action-btn primary" data-action="upgrade">' + icon('external') + ' Upgrade License</button></div></div>';

    var invoices = (billing && Array.isArray(billing.invoices)) ? billing.invoices : [];
    var invHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('file') + '</div><div><div class="gph-title">Invoices</div><div class="gph-sub">Billing history</div></div></div></div>' +
      (invoices.length ? '<div class="table-wrap"><table class="admin-table"><thead><tr><th scope="col">Date</th><th scope="col">Description</th><th scope="col">Amount</th><th scope="col">Status</th></tr></thead><tbody>' +
        invoices.map(function (i) { return '<tr><td style="font-family:var(--ff-m);font-size:.78rem;color:var(--text3)">' + esc(i.date) + '</td><td>' + esc(i.description) + '</td><td style="font-family:var(--ff-m);color:var(--emerald)">' + fmtMoney(i.amount) + '</td><td>' + badge(i.status, 'active') + '</td></tr>'; }).join('') +
        '</tbody></table></div>' : '<div class="dash-empty"><b>No invoices yet.</b></div>') + '</div>';

    var keys = Array.isArray(licenses) ? licenses : [];
    var keyHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('key') + '</div><div><div class="gph-title">License Keys</div><div class="gph-sub">Active product keys</div></div></div></div>' +
      (keys.length ? keys.map(function (l) {
        return '<div style="margin-bottom:22px"><div style="font-family:var(--ff-m);font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:8px">' + esc(l.product) + '</div>' +
          '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--bg3);border:1px solid var(--border2);border-radius:10px;padding:14px 18px;font-family:var(--ff-m);font-size:.9rem;font-weight:700;color:var(--gold);letter-spacing:.04em">' +
          '<span class="masked' + (State.piiRevealed ? ' revealed' : '') + '" data-key="' + esc(l.key) + '">' + esc(l.key) + '</span>' +
          '<button class="action-btn gold" data-action="copy-key" data-key="' + esc(l.key) + '">' + icon('link') + ' Copy</button></div>' +
          '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:10px">' +
          (l.status ? '<div><span style="font-size:.64rem;color:var(--text4);font-family:var(--ff-m)">STATUS</span><div>' + badge(l.status, 'active') + '</div></div>' : '') +
          (l.plan ? '<div><span style="font-size:.64rem;color:var(--text4);font-family:var(--ff-m)">PLAN</span><div>' + badge(l.plan, 'elite') + '</div></div>' : '') +
          (l.devices ? '<div><span style="font-size:.64rem;color:var(--text4);font-family:var(--ff-m)">DEVICES</span><div style="font-family:var(--ff-m);font-size:.82rem;color:var(--cyan)">' + esc(l.devices) + '</div></div>' : '') +
          (l.renews ? '<div><span style="font-size:.64rem;color:var(--text4);font-family:var(--ff-m)">RENEWS</span><div style="font-family:var(--ff-m);font-size:.82rem;color:var(--gold)">' + esc(l.renews) + '</div></div>' : '') +
          (l.version ? '<div><span style="font-size:.64rem;color:var(--text4);font-family:var(--ff-m)">VERSION</span><div style="font-family:var(--ff-m);font-size:.82rem;color:var(--cyan)">' + esc(l.version) + '</div></div>' : '') +
          (l.platform ? '<div><span style="font-size:.64rem;color:var(--text4);font-family:var(--ff-m)">PLATFORM</span><div style="font-family:var(--ff-m);font-size:.82rem;color:var(--gold)">' + esc(l.platform) + '</div></div>' : '') +
          (l.term ? '<div><span style="font-size:.64rem;color:var(--text4);font-family:var(--ff-m)">TERM</span><div style="font-family:var(--ff-m);font-size:.82rem;color:var(--cyan)">' + esc(l.term) + '</div></div>' : '') +
          '</div></div>';
      }).join('') : '<div class="dash-empty"><b>No active licenses.</b></div>') + '</div>';

    function dlCards(list, emptyMsg) {
      list = Array.isArray(list) ? list : [];
      if (!list.length) return '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('download') + '</div><div><div class="gph-title">Downloads</div></div></div></div><div class="dash-empty"><b>' + esc(emptyMsg) + '</b></div></div>';
      return '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('download') + '</div><div><div class="gph-title">Downloads &amp; Access</div><div class="gph-sub">Licensed materials</div></div></div></div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px">' +
        list.map(function (d) {
          var btn = d.type === 'appstore' ? '<a class="action-btn cyan" href="#">' + icon('phone') + ' App Store</a>' :
            d.type === 'googleplay' ? '<a class="action-btn cyan" href="#">' + icon('phone') + ' Google Play</a>' :
            d.type === 'access' ? '<span class="badge elite">GRANTED</span>' :
            '<button class="action-btn gold" data-action="download" data-file="' + esc(d.file || 'package.zip') + '">' + icon('download') + ' Download</button>';
          return '<div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px"><div style="color:var(--gold);margin-bottom:10px">' + icon('file') + '</div>' +
            '<div style="font-weight:600;margin-bottom:6px">' + esc(d.name) + '</div>' +
            '<div style="font-size:.78rem;color:var(--text3);line-height:1.6;margin-bottom:12px">' + esc(d.meta || '').replace(/<br\s*\/?>/g, ' ') + '</div>' + btn + '</div>';
        }).join('') + '</div></div>';
    }

    el.innerHTML = planHTML + invHTML + keyHTML + dlCards(downloads, 'No downloads available.') + dlCards(special, 'No special licenses.') + dlCards(member, 'No member access.');
  }

  function renderSentinel(s) {
    var el = $('sentinelBody'); if (!el) return;
    if (!s || !s.tier) {
      showEmpty('sentinelBody', 'No Sentinel clearance on file.',
        '<a class="action-btn primary" href="/sentinel_program.html">View the Sentinel Program</a>');
      return;
    }
    var flag = isSimulated('sentinel')
      ? '<div style="margin-bottom:14px">' + simFlag() + ' <span style="font-family:var(--ff-m);font-size:.72rem;color:var(--text4);margin-left:8px">Affiliate telemetry is simulated</span></div>'
      : '';
    var c = s.commission || {}, stats = s.stats || {}, po = s.payout || {};
    var next = s.nextTier || {};

    var statsHTML = '<div class="stats-row">' +
      statBox('Active Referrals', stats.activeReferrals, 'var(--cyan)') +
      statBox('Total Earned', fmtMoney(stats.totalEarned), 'var(--emerald)') +
      statBox('Recurring / Mo', fmtMoney(stats.recurringMonthly), 'var(--gold)') +
      statBox('Attribution', s.attribution || '—', 'var(--text2)') + '</div>';

    var cm = [
      { l: 'Base commission', v: (c.base || 0) + '%', col: 'var(--emerald)' },
      { l: 'Recurring', v: (c.recurring || 0) + '%', col: 'var(--gold)' },
      { l: 'Sub-affiliate', v: (c.subAffiliate || 0) + '%', col: 'var(--cyan)' },
      { l: 'Cross-product', v: '+' + (c.crossProduct || 0) + '%', col: 'var(--text2)' }
    ];
    var cmHTML = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px">' +
      cm.map(function (m) {
        return '<div style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px"><div style="font-family:var(--ff-m);font-size:.62rem;color:var(--text4);text-transform:uppercase;letter-spacing:.06em">' + esc(m.l) + '</div><div style="font-family:var(--ff-m);font-size:1.05rem;font-weight:700;color:' + m.col + '">' + esc(m.v) + '</div></div>';
      }).join('') + '</div>';

    var progPct = next.target ? Math.min(100, Math.round((next.current || 0) / next.target * 100)) : 100;
    var tierHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('users') + '</div><div><div class="gph-title">' + esc(s.tier) + ' Tier</div><div class="gph-sub">' + esc(s.tierSub || '') + '</div></div></div>' + badge('ACTIVE', 'active') + '</div>' +
      cmHTML +
      (next.name ? '<div class="pf-bar-wrap"><div class="pf-bar-label"><span>Progress to ' + esc(next.name) + ' · ' + esc(next.requires || '') + '</span><span>' + (next.current || 0) + ' / ' + (next.target || '—') + '</span></div><div class="pf-bar-track"><div class="pf-bar-fill" style="width:' + progPct + '%"></div></div></div>' : '') +
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:16px;background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:12px 16px;font-family:var(--ff-m);font-size:.78rem;color:var(--text3)">' +
      '<span class="masked' + (State.piiRevealed ? ' revealed' : '') + '" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(s.referralLink || '—') + '</span>' +
      '<button class="action-btn gold" data-action="copy-link" data-link="' + esc(s.referralLink || '') + '" style="flex-shrink:0">' + icon('link') + ' Copy link</button></div></div>';

    var tiers = s.tiers || [];
    var ladderHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('chart') + '</div><div><div class="gph-title">Tier Ladder</div><div class="gph-sub">Commission architecture — unlocks on authority or proven referrals</div></div></div></div><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px">' +
      tiers.map(function (t) {
        var cur = (t.rank || 0) === (s.tierRank || 0);
        return '<div style="background:' + (cur ? 'var(--card2)' : 'var(--card)') + ';border:1px solid ' + (cur ? 'var(--border2)' : 'var(--border)') + ';border-radius:12px;padding:14px">' +
          '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px"><span style="font-family:var(--ff-m);font-size:.62rem;color:var(--text4)">TIER 0' + esc(t.rank) + '</span>' + (cur ? badge('CURRENT', 'active') : '') + '</div>' +
          '<div style="font-weight:600;font-size:.95rem;color:var(--text)">' + esc(t.name) + '</div>' +
          '<div style="font-size:.72rem;color:var(--text3);margin-bottom:8px">' + esc(t.sub || '') + '</div>' +
          '<div style="font-family:var(--ff-m);font-size:.78rem;color:var(--gold);font-weight:700">' + esc(t.base) + '%' + (t.recurring ? ' + ' + esc(t.recurring) + '% rec' : '') + '</div></div>';
      }).join('') + '</div></div>';

    var refs = s.recentReferrals || [];
    var refsHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('list') + '</div><div><div class="gph-title">Recent Referrals</div><div class="gph-sub">Last-touch attribution</div></div></div></div>' +
      (refs.length ? '<div class="table-wrap"><table class="admin-table"><caption>Recent referrals — Customer, Product, Commission, Status, Date</caption><thead><tr><th scope="col">Customer</th><th scope="col">Product</th><th scope="col">Commission</th><th scope="col">Status</th><th scope="col">Date</th></tr></thead><tbody>' +
        refs.map(function (r) {
          var st = String(r.status || '').toUpperCase();
          return '<tr><td style="font-family:var(--ff-m);font-size:.78rem;color:var(--text2)">' + esc(r.customer) + '</td>' +
            '<td style="font-size:.82rem;color:var(--text2)">' + esc(r.product) + '</td>' +
            '<td style="font-family:var(--ff-m);font-size:.82rem;font-weight:700;color:var(--emerald)">' + fmtMoney(r.amount) + '</td>' +
            '<td>' + badge(r.status, st === 'PAID' ? 'active' : 'trial') + '</td>' +
            '<td style="font-family:var(--ff-m);font-size:.74rem;color:var(--text4)">' + esc(r.date) + '</td></tr>';
        }).join('') + '</tbody></table></div>' : '<div class="dash-empty"><b>No referrals yet. Share your link to begin earning.</b></div>') + '</div>';

    var payoutHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('card') + '</div><div><div class="gph-title">Payouts</div><div class="gph-sub">' + esc(po.schedule || 'Monthly · net-15') + ' · ' + esc(po.minimum || '$50') + ' minimum</div></div></div><span style="font-family:var(--ff-d);font-size:1.6rem;font-weight:600;color:var(--gold)">' + fmtMoney(po.balance) + '</span></div>' +
      '<div style="font-family:var(--ff-m);font-size:.72rem;color:var(--text4);margin:-10px 0 0 4px">Next payout ' + esc(po.nextDate || '—') + '</div>' +
      '<div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap"><a class="action-btn primary" href="/sentinel_application.html">' + icon('external') + ' Request Clearance</a><a class="action-btn cyan" href="/sentinel_program.html">' + icon('external') + ' View Commission Structure</a></div></div>';

    el.innerHTML = flag + statsHTML + tierHTML + ladderHTML + refsHTML + payoutHTML;
  }

  function renderProfileForm(profile, notifications) {
    var el = $('profileBody'); if (!el) return;
    var p = profile || {};
    var notifCount = (Array.isArray(notifications) ? notifications : []).length;
    var prefToggles = [
      { id: 'pref-baseline', name: 'Neural baseline reminders', desc: 'Daily check at your session start time', on: true },
      { id: 'pref-breach', name: 'Breach warning alerts', desc: 'Signal alert when daily loss limit approaches', on: true },
      { id: 'pref-sentiment', name: 'Auto-refresh sentiment on open', desc: 'Sentiment scan runs automatically at 08:30 ET', on: true },
      { id: 'pref-review', name: 'Post-session review prompts', desc: 'Reminder to complete review after session close', on: true },
      { id: 'pref-streak', name: 'Streak milestone alerts', desc: 'Signal alerts at 7, 14, 30-day milestones', on: false },
      { id: 'pref-report', name: 'Weekly performance report', desc: 'Email summary every Sunday at 20:00 ET', on: true }
    ];
    el.innerHTML = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">' +
      '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('user') + '</div><div><div class="gph-title">Trader Profile</div><div class="gph-sub">Neural baseline &amp; session preferences</div></div></div><button class="action-btn primary" data-action="save-profile">' + icon('check') + ' Save Changes</button></div>' +
      '<div class="form-field"><label class="form-label" for="settingName">Display Name</label><input class="form-input" id="settingName" value="' + esc(p.displayName || '') + '"></div>' +
      '<div class="form-field"><label class="form-label" for="settingEmail">Email Address</label><input class="form-input" id="settingEmail" value="' + esc(p.email || '') + '"></div>' +
      '<div class="form-field"><label class="form-label" for="settingPhone">Phone (masked)</label><input class="form-input" id="settingPhone" value="' + esc(p.phoneMasked || '+1 (***) ***-7834') + '" readonly aria-describedby="phoneHint"><div id="phoneHint" style="font-size:.72rem;color:var(--text4);margin-top:4px">Shown masked unless authorized.</div></div>' +
      '<div class="two-col">' +
      '<div class="form-field"><label class="form-label" for="settingTz">Timezone</label><select class="form-select" id="settingTz"><option' + (p.timezone && p.timezone.indexOf('New_York') >= 0 ? ' selected' : '') + '>America/New_York (EST)</option><option' + (p.timezone && p.timezone.indexOf('Chicago') >= 0 ? ' selected' : '') + '>America/Chicago (CST)</option><option' + (p.timezone && p.timezone.indexOf('Los_Angeles') >= 0 ? ' selected' : '') + '>America/Los_Angeles (PST)</option><option' + (p.timezone && p.timezone.indexOf('London') >= 0 ? ' selected' : '') + '>Europe/London (GMT)</option></select></div>' +
      '<div class="form-field"><label class="form-label" for="settingMarket">Primary Market</label><select class="form-select" id="settingMarket"><option' + (p.primaryMarket && p.primaryMarket.indexOf('NQ') >= 0 ? ' selected' : '') + '>NQ / NASDAQ 100</option><option' + (p.primaryMarket && p.primaryMarket.indexOf('ES') >= 0 ? ' selected' : '') + '>ES / S&amp;P 500</option><option' + (p.primaryMarket && p.primaryMarket.indexOf('GC') >= 0 ? ' selected' : '') + '>GC / Gold</option><option' + (p.primaryMarket && p.primaryMarket.indexOf('CL') >= 0 ? ' selected' : '') + '>CL / Crude Oil</option><option' + (p.primaryMarket && p.primaryMarket.indexOf('BTC') >= 0 ? ' selected' : '') + '>BTC / Bitcoin</option></select></div>' +
      '</div>' +
      '<div class="form-field"><label class="form-label" for="settingStyle">Trading Style</label><select class="form-select" id="settingStyle"><option' + (p.tradingStyle && p.tradingStyle.indexOf('ICT') >= 0 ? ' selected' : '') + '>ICT / Smart Money Concepts</option><option' + (p.tradingStyle && p.tradingStyle.indexOf('Price') >= 0 ? ' selected' : '') + '>Price Action</option><option' + (p.tradingStyle && p.tradingStyle.indexOf('Flow') >= 0 ? ' selected' : '') + '>Institutional Flow</option><option' + (p.tradingStyle && p.tradingStyle.indexOf('Hybrid') >= 0 ? ' selected' : '') + '>Hybrid</option></select></div>' +
      '</div>' +
      '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('bell') + '</div><div><div class="gph-title">Signal Alerts</div><div class="gph-sub">Non-repainting engine triggers &amp; risk flags · ' + notifCount + ' pending</div></div></div></div>' +
      prefToggles.map(function (t) {
        return '<div class="toggle-row"><div><div class="toggle-name">' + esc(t.name) + '</div><div class="toggle-desc">' + esc(t.desc) + '</div></div>' +
          '<label class="toggle-switch"><input type="checkbox" data-pref="' + t.id + '"' + (t.on ? ' checked' : '') + '><span class="toggle-slider" aria-hidden="true"></span><span class="sr-only">' + esc(t.name) + '</span></label></div>';
      }).join('') + '</div></div>';
  }

  function renderSecurity(sec, fingerprint) {
    var el = $('securityBody'); if (!el) return;
    sec = sec || {};
    var fp = fingerprint || {};
    var twoFA = String(sec.twoFactor || 'DISABLED').toUpperCase() === 'ENABLED';

    var fpHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('fingerprint') + '</div><div><div class="gph-title">Session Integrity</div><div class="gph-sub">Device fingerprint &amp; origin</div></div></div>' + (twoFA ? '<span class="badge active">' + icon('check') + ' 2FA</span>' : '<span class="badge inactive">2FA OFF</span>') + '</div>' +
      '<div class="fingerprint-card"><div class="fp-row"><span class="fp-k">Device</span><span class="fp-v">' + esc(fp.device || 'Unknown device') + '</span></div>' +
      '<div class="fp-row"><span class="fp-k">Fingerprint</span><span class="fp-v masked' + (State.piiRevealed ? ' revealed' : '') + '">' + esc(fp.id || 'fp_unknown') + '</span></div>' +
      '<div class="fp-row"><span class="fp-k">IP Location</span><span class="fp-v masked' + (State.piiRevealed ? ' revealed' : '') + '">' + esc(fp.ip || '—') + ' · ' + esc(fp.location || '—') + '</span></div>' +
      '<div class="fp-row"><span class="fp-k">Last active</span><span class="fp-v">' + esc(fp.lastActive || 'Now') + '</span></div>' +
      '<div class="fp-row"><span class="fp-k">Trust</span><span class="fp-v" style="color:' + (fp.trusted ? 'var(--emerald)' : 'var(--red)') + '">' + (fp.trusted ? 'Recognized device' : 'Unrecognized device') + '</span></div></div></div>';

    var methods = (sec.methods || []);
    var methodsHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon g">' + icon('lock') + '</div><div><div class="gph-title">Two-Factor Auth</div><div class="gph-sub">' + (twoFA ? 'Enabled' : 'Disabled') + '</div></div></div></div>' +
      methods.map(function (m) {
        return '<div class="toggle-row"><div><div class="toggle-name">' + esc(m.name) + '</div><div class="toggle-desc">' + esc(m.desc) + '</div></div>' +
          '<label class="toggle-switch"><input type="checkbox"' + (m.enabled ? ' checked' : '') + '><span class="toggle-slider" aria-hidden="true"></span><span class="sr-only">' + esc(m.name) + '</span></label></div>';
      }).join('') + '</div>';

    var sessions = sec.sessions || [];
    var sessHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon r">' + icon('phone') + '</div><div><div class="gph-title">Active Sessions</div><div class="gph-sub">' + sessions.length + ' devices</div></div></div><button class="action-btn red" data-action="signout-all">' + icon('logout') + ' Sign out all others</button></div>' +
      (sessions.length ? sessions.map(function (s) {
        var c = s.level === 'green' ? 'var(--emerald)' : 'var(--cyan)';
        return '<div class="session-item"><span class="ai-dot" style="background:' + c + '"></span>' +
          '<div class="ai-text">' + esc(s.device) + '<div class="ai-sub">' + esc(s.state || '') + '</div></div>' +
          (s.current ? '<span class="badge active">This device</span>' : '<button class="action-btn red" data-action="revoke-session" data-id="' + esc(s.id) + '">' + icon('x') + ' Revoke</button>') +
          '</div>';
      }).join('') : '<div class="dash-empty"><b>No active sessions reported.</b></div>') + '</div>';

    var audit = State.audit.length ? State.audit : (window.__initialAudit || []);
    var auditHTML = '<div class="g-panel"><div class="g-panel-hdr"><div class="gph-left"><div class="gph-icon c">' + icon('list') + '</div><div><div class="gph-title">Audit Log</div><div class="gph-sub">Who did what, when</div></div></div></div><div id="auditList"></div></div>';

    el.innerHTML = fpHTML + methodsHTML + sessHTML + auditHTML;
    renderAudit();
  }

  function renderAudit() {
    var list = $('auditList'); if (!list) return;
    // seed the audit log from data if we have it and haven't yet
    if (!State.audit.length && State.data && Array.isArray(State.data.auditLog) && State.data.auditLog.length) {
      State.audit = State.data.auditLog.slice().reverse();
      persistAudit();
    }
    if (!State.audit.length) { list.innerHTML = '<div class="dash-empty"><b>No admin actions recorded.</b></div>'; return; }
    list.innerHTML = State.audit.slice(0, 8).map(function (a) {
      return '<div class="audit-item"><span class="au-actor">' + esc(a.actor) + '</span><span class="au-action">' + esc(a.action) + (a.detail ? '<span style="color:var(--text4)"> — ' + esc(a.detail) + '</span>' : '') + '</span><span class="au-when">' + esc(a.when) + '</span></div>';
    }).join('');
  }

  function renderBell(notifications) {
    var c = $('bellCount'); if (!c) return;
    var list = Array.isArray(notifications) ? notifications : [];
    c.textContent = list.length;
    c.style.display = list.length ? 'flex' : 'none';
    var panel = $('bellList'); if (!panel) return;
    if (!list.length) { panel.innerHTML = '<div style="font-family:var(--ff-m);font-size:.78rem;color:var(--text3);padding:14px">No signal alerts.</div>'; return; }
    panel.innerHTML = list.map(function (n) {
      var color = { red: 'var(--red)', gold: 'var(--gold)', green: 'var(--emerald)', cyan: 'var(--cyan)' }[n.level] || 'var(--cyan)';
      return '<div style="display:flex;gap:10px;padding:11px 10px;border-bottom:1px solid var(--border-soft)"><span style="width:7px;height:7px;border-radius:50%;background:' + color + ';margin-top:6px;flex-shrink:0"></span><div><div style="font-size:.84rem;font-weight:600;color:var(--text)">' + esc(n.title) + '</div><div style="font-size:.76rem;color:var(--text3);line-height:1.5">' + esc(n.detail) + '</div><div style="font-family:var(--ff-m);font-size:.64rem;color:var(--text4);margin-top:3px">' + esc(n.meta) + '</div></div></div>';
    }).join('');
  }

  /* ──────────────────────────────────────────────────────────
     Signal export (CSV)
     ────────────────────────────────────────────────────────── */
  function exportSignals() {
    var list = State.data && Array.isArray(State.data.sessions) ? State.data.sessions : [];
    if (!list.length) { logAudit('Export signal log', 'no rows'); return; }
    var head = ['Date', 'Module', 'Market', 'Session P&L', 'Score', 'Primary Trigger', 'Status'];
    var rows = [head.join(',')].concat(list.map(function (s) {
      return [s.date, s.module, s.market, s.pnl, s.score, '"' + String(s.trigger).replace(/"/g, '""') + '"', s.status].join(',');
    }));
    var blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'signal-log.csv';
    document.body.appendChild(a); a.click(); a.remove();
    logAudit('Exported signal log', list.length + ' rows');
  }

  /* ──────────────────────────────────────────────────────────
     Login (demo gate — any credentials; 'wrong' password fails)
     ────────────────────────────────────────────────────────── */
  var loginAttempts = 0;
  function doLogin(skip) {
    var email = $('loginEmail'), pass = $('loginPass'), err = $('loginError'), btn = $('loginBtn');
    if (!skip && !email.value) { err.textContent = 'Please enter your email address.'; err.classList.add('show'); return; }
    err.classList.remove('show');
    btn.disabled = true; btn.innerHTML = '<span style="width:16px;height:16px;border:2px solid rgba(0,0,0,.3);border-top-color:#020408;border-radius:50%;animation:blink 0.7s linear infinite"></span> Authenticating…';
    setTimeout(function () {
      if (!skip && pass.value === 'wrong') {
        loginAttempts++;
        err.textContent = 'Invalid credentials. ' + Math.max(0, 3 - loginAttempts) + ' attempts remaining.';
        err.classList.add('show');
        btn.disabled = false; btn.innerHTML = 'Authorize';
      } else if (!skip && !$('twoFA').classList.contains('show') && pass.value.length > 0 && loginAttempts === 0) {
        $('twoFA').classList.add('show');
        btn.disabled = false; btn.innerHTML = 'Verify 2FA code';
        var t1 = $('t1'); if (t1) t1.focus();
      } else {
        loginSuccess(email && email.value ? email.value : 'Jaylu');
      }
    }, 700);
  }

  function loginSuccess(email) {
    var name = email.indexOf('@') > 0 ? email.split('@')[0] : 'Jaylu';
    name = name.charAt(0).toUpperCase() + name.slice(1);
    var initials = name.split(/\s+/).map(function (s) { return s[0]; }).join('').slice(0, 2).toUpperCase();
    $('navName').textContent = name;
    $('navAvatar').textContent = initials;
    var screen = $('loginScreen'), app = $('app');
    screen.style.transition = 'opacity .5s ease,transform .5s ease';
    screen.style.opacity = '0'; screen.style.transform = 'scale(.98)';
    setTimeout(function () {
      screen.style.display = 'none';
      app.hidden = false;
      logAudit('Signed in', 'Passkey · macOS · Boston, MA');
      loadAll().then(function (data) {
        State.data = data;
        renderAll();
      }).catch(function (e) {
        console.error('[CommandPortal] load failed:', e);
        ['statRow', 'intelBody', 'preflightBody', 'analysesBody', 'disciplineBody', 'propFirmsGrid', 'licenseBody', 'sentinelBody', 'profileBody', 'securityBody'].forEach(function (id) {
          showError(id, e.message || 'Could not reach the admin service.');
        });
      });
      // retry button re-runs load
    }, 500);
  }

  function doLogout() {
    var screen = $('loginScreen');
    logAudit('Signed out', '');
    setTimeout(function () {
      screen.style.display = 'flex'; screen.style.opacity = '0'; screen.style.transform = 'scale(.98)';
      requestAnimationFrame(function () { requestAnimationFrame(function () { screen.style.opacity = '1'; screen.style.transform = 'scale(1)'; }); });
      $('twoFA').classList.remove('show');
      $('loginEmail').value = ''; $('loginPass').value = '';
      loginAttempts = 0;
    }, 300);
  }

  /* ──────────────────────────────────────────────────────────
     Global click delegation
     ────────────────────────────────────────────────────────── */
  function onAction(el) {
    var action = el.getAttribute('data-action');
    switch (action) {
      case 'retry':
        loadAll().then(function (d) { State.data = d; renderAll(); }).catch(function (e) { console.error(e); });
        break;
      case 'sig-prev': State.sigPage = Math.max(0, State.sigPage - 1); renderSignals(State.data && State.data.sessions); break;
      case 'sig-next': State.sigPage++; renderSignals(State.data && State.data.sessions); break;
      case 'review-signal': logAudit('Reviewed signal', 'id ' + el.getAttribute('data-id')); break;
      case 'copy-key':
        copyText(el.getAttribute('data-key'), el);
        logAudit('Copied license key', '');
        break;
      case 'copy-link':
        copyText(el.getAttribute('data-link'), el);
        logAudit('Copied referral link', '');
        break;
      case 'reveal-pii':
        State.piiRevealed = !State.piiRevealed;
        renderSecurity(State.data && State.data.security, State.data && State.data.fingerprint);
        renderLicense(State.data && State.data.licenses, State.data && State.data.billing, State.data && State.data.downloads, State.data && State.data.specialLicenses, State.data && State.data.memberAccess);
        logAudit(State.piiRevealed ? 'Revealed PII' : 'Masked PII', '');
        break;
      case 'signout-all':
        logAudit('Signed out all other sessions', '');
        var ses = document.querySelectorAll('.session-item');
        ses.forEach(function (s) { var btn = s.querySelector('[data-action="revoke-session"]'); if (btn) s.remove(); });
        break;
      case 'revoke-session': logAudit('Revoked session', 'id ' + el.getAttribute('data-id')); el.closest('.session-item').remove(); break;
      case 'cycle-prop': logAudit('Cycled prop status', 'id ' + el.getAttribute('data-id')); break;
      case 'download': logAudit('Downloaded', el.getAttribute('data-file')); break;
      case 'manage-billing': logAudit('Opened billing management', ''); break;
      case 'upgrade': logAudit('Requested license upgrade', ''); break;
      case 'save-profile': logAudit('Saved trader profile', ''); break;
      case 'export-signals': exportSignals(); break;
      case 'refresh-intel': loadAll().then(function (d) { State.data = d; renderAll(); }); break;
    }
  }

  function copyText(text, btn) {
    if (!btn) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { flashCopied(btn); });
    } else {
      var ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); flashCopied(btn); } catch (e) {}
      ta.remove();
    }
  }
  function flashCopied(btn) {
    var orig = btn.innerHTML; btn.innerHTML = icon('check') + ' Copied';
    setTimeout(function () { btn.innerHTML = orig; }, 1500);
  }

  /* ──────────────────────────────────────────────────────────
     Init
     ────────────────────────────────────────────────────────── */
  function init() {
    initScopeCursor();
    initTheme();
    initNavDropdowns();
    initTicker();
    buildSidebar();
    loadAudit();

    // login controls
    var loginBtn = $('loginBtn');
    if (loginBtn) loginBtn.addEventListener('click', function () { doLogin(false); });
    var pass = $('loginPass');
    if (pass) pass.addEventListener('keydown', function (e) { if (e.key === 'Enter') doLogin(false); });
    var passToggle = $('passToggle');
    if (passToggle && pass) passToggle.addEventListener('click', function () { pass.type = pass.type === 'password' ? 'text' : 'password'; });
    document.querySelectorAll('[data-bio]').forEach(function (b) {
      b.addEventListener('click', function () { doLogin(true); });
    });
    var forgot = $('forgotLink');
    if (forgot) forgot.addEventListener('click', function (e) { e.preventDefault(); logAudit('Requested password reset', ''); });

    // sign out
    var signOut = $('signOutBtn');
    if (signOut) signOut.addEventListener('click', doLogout);
    var bell = $('bellBtn');
    if (bell) {
      bell.addEventListener('click', function (e) {
        e.stopPropagation();
        var p = $('bellPanel'); if (!p) return;
        var open = p.style.display === 'block';
        p.style.display = open ? 'none' : 'block';
        bell.setAttribute('aria-expanded', String(!open));
      });
      document.addEventListener('click', function (e) {
        if (!e.target.closest('.bell-wrap')) { var p = $('bellPanel'); if (p) p.style.display = 'none'; bell.setAttribute('aria-expanded', 'false'); }
      });
    }

    // section nav (sidebar + any data-section element)
    document.addEventListener('click', function (e) {
      var link = e.target.closest('[data-section]');
      if (link) { e.preventDefault(); showSection(link.getAttribute('data-section')); return; }
      var act = e.target.closest('[data-action]');
      if (act) { onAction(act); return; }
      var pf = e.target.closest('.pf-status');
      if (pf) { /* future: status detail modal */ }
    });

    // filter select
    var filter = $('sigFilter');
    if (filter) filter.addEventListener('change', function () { State.sigFilter = filter.value; State.sigPage = 0; renderSignals(State.data && State.data.sessions); });

    // 2FA auto-advance
    for (var i = 1; i <= 6; i++) {
      (function (n) {
        var inp = $('t' + n); if (!inp) return;
        inp.addEventListener('input', function () {
          if (inp.value && n < 6) { var nx = $('t' + (n + 1)); if (nx) nx.focus(); }
        });
      })(i);
    }

    showSection('overview');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Minimal public surface for console debugging + automated verification.
  window.ST = { showSection: showSection, doLogin: doLogin, loginSuccess: loginSuccess, loadAll: loadAll, renderAll: renderAll, State: State };
})();
