/*!
 * SniperTrader.ai — Assistant chat widget (self-contained, zero-dependency).
 *
 * Loaded on every page via: <script src="/assets/assistant-widget.js" defer></script>
 * Renders a floating launcher + chat panel that calls POST /api/assistant/chat.
 *   - session id persisted in localStorage
 *   - sources rendered flat under each answer (no accordion)
 *   - inline [n] citations link to their source row
 *   - thumbs up/down -> POST /api/assistant/feedback
 *   - dark by default; follows the page's light-mode class when present
 */
(function () {
  'use strict';

  var NS = 'stassist';
  var API = (window.ST_ASSISTANT_API || '') + '/api/assistant';
  var LS_SESSION = 'st_assistant_session_id';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      var v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  function sessionId() {
    var s = null;
    try { s = localStorage.getItem(LS_SESSION); } catch (e) {}
    if (!s) { s = uuid(); try { localStorage.setItem(LS_SESSION, s); } catch (e) {} }
    return s;
  }

  function isLight() {
    var b = document.body;
    var h = document.documentElement;
    return !!(b && (b.classList.contains('light') || b.classList.contains('light-mode')))
      || !!(h && h.classList.contains('light'));
  }

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  var CSS = [
    '.' + NS + '-root{--s-bg:var(--bg,#0b0f0d);--s-card:var(--card,#12191c);--s-border:var(--border,#20303a);',
    '--s-fg:var(--foreground,#e6eef0);--s-muted:var(--muted-foreground,#7e8f98);--s-accent:var(--emerald,#10b981);--s-accent2:var(--cyan,#22d3ee);}',
    '.' + NS + '-root.' + NS + '-light{--s-bg:#f3f6f5;--s-card:#ffffff;--s-border:#dde3e1;--s-fg:#1a2224;--s-muted:#5d6a70;--s-accent:#0ea371;--s-accent2:#0aa2c0;}',
    '.' + NS + '-launcher{position:fixed;right:20px;bottom:20px;z-index:2147483000;width:56px;height:56px;border-radius:50%;',
    'border:1px solid var(--s-border);background:linear-gradient(135deg,var(--s-accent),var(--s-accent2));color:#04110c;',
    'cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px rgba(0,0,0,.35);transition:transform .15s ease;}',
    '.' + NS + '-launcher:hover{transform:scale(1.06);}',
    '.' + NS + '-launcher svg{width:26px;height:26px;fill:currentColor;}',
    '.' + NS + '-dot{position:absolute;top:2px;right:2px;width:10px;height:10px;border-radius:50%;background:var(--s-accent);border:2px solid #04110c;animation:' + NS + '-pulse 2s infinite;}',
    '@keyframes ' + NS + '-pulse{0%,100%{opacity:1}50%{opacity:.35}}',
    '.' + NS + '-panel{position:fixed;right:20px;bottom:88px;z-index:2147483000;width:min(400px,calc(100vw - 32px));height:min(640px,calc(100vh - 120px));',
    'display:flex;flex-direction:column;background:var(--s-bg);border:1px solid var(--s-border);border-radius:16px;overflow:hidden;',
    'box-shadow:0 20px 60px rgba(0,0,0,.45);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;}',
    '.' + NS + '-panel.' + NS + '-hidden{display:none;}',
    '.' + NS + '-head{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--s-border);background:var(--s-card);}',
    '.' + NS + '-head-badge{width:10px;height:10px;border-radius:50%;background:var(--s-accent);box-shadow:0 0 0 3px rgba(16,185,129,.2);flex:0 0 auto;}',
    '.' + NS + '-head-title{flex:1;font-size:14px;font-weight:600;color:var(--s-fg);letter-spacing:.2px;}',
    '.' + NS + '-head-sub{font-size:11px;color:var(--s-muted);font-weight:400;margin-top:1px;}',
    '.' + NS + '-close{background:none;border:none;color:var(--s-muted);cursor:pointer;font-size:20px;line-height:1;padding:2px 6px;}',
    '.' + NS + '-close:hover{color:var(--s-fg);}',
    '.' + NS + '-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;}',
    '.' + NS + '-msg{max-width:86%;font-size:13.5px;line-height:1.5;padding:10px 13px;border-radius:12px;word-wrap:break-word;}',
    '.' + NS + '-msg-user{align-self:flex-end;background:linear-gradient(135deg,var(--s-accent),var(--s-accent2));color:#04110c;}',
    '.' + NS + '-msg-asst{align-self:flex-start;background:var(--s-card);border:1px solid var(--s-border);color:var(--s-fg);}',
    '.' + NS + '-msg-asst strong{color:var(--s-fg);}',
    '.' + NS + '-cite{display:inline-block;margin:0 2px;padding:0 5px;border-radius:6px;background:var(--s-accent);color:#04110c;font-size:10.5px;font-weight:700;line-height:1.6;cursor:pointer;border:none;vertical-align:baseline;}',
    '.' + NS + '-cite:hover{filter:brightness(1.1);}',
    '.' + NS + '-srcs{margin-top:8px;display:flex;flex-direction:column;gap:6px;align-self:flex-start;max-width:92%;}',
    '.' + NS + '-src{border:1px solid var(--s-border);border-radius:10px;padding:8px 10px;background:var(--s-card);font-size:11.5px;color:var(--s-muted);transition:border-color .2s,box-shadow .2s;}',
    '.' + NS + '-src.' + NS + '-flash{border-color:var(--s-accent);box-shadow:0 0 0 2px rgba(16,185,129,.25);}',
    '.' + NS + '-src-top{display:flex;gap:6px;align-items:baseline;}',
    '.' + NS + '-src-idx{flex:0 0 auto;background:var(--s-accent);color:#04110c;border-radius:5px;padding:0 5px;font-size:10px;font-weight:700;}',
    '.' + NS + '-src-title{color:var(--s-fg);font-weight:600;font-size:11.5px;}',
    '.' + NS + '-src-section{color:var(--s-muted);}',
    '.' + NS + '-src-snip{color:var(--s-muted);margin-top:3px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}',
    '.' + NS + '-fb{display:flex;gap:6px;align-self:flex-start;margin-top:-4px;}',
    '.' + NS + '-fb button{background:var(--s-card);border:1px solid var(--s-border);color:var(--s-muted);border-radius:8px;padding:3px 8px;font-size:12px;cursor:pointer;}',
    '.' + NS + '-fb button:hover{color:var(--s-fg);border-color:var(--s-accent);}',
    '.' + NS + '-typing{align-self:flex-start;background:var(--s-card);border:1px solid var(--s-border);color:var(--s-muted);border-radius:12px;padding:10px 14px;font-size:13px;}',
    '.' + NS + '-typing span{display:inline-block;width:6px;height:6px;margin:0 1px;border-radius:50%;background:var(--s-accent);animation:' + NS + '-b 1.2s infinite;}',
    '.' + NS + '-typing span:nth-child(2){animation-delay:.2s}',
    '.' + NS + '-typing span:nth-child(3){animation-delay:.4s}',
    '@keyframes ' + NS + '-b{0%,60%,100%{opacity:.2}30%{opacity:1}}',
    '.' + NS + '-input{display:flex;gap:8px;padding:12px;border-top:1px solid var(--s-border);background:var(--s-card);}',
    '.' + NS + '-input textarea{flex:1;resize:none;background:var(--s-bg);border:1px solid var(--s-border);border-radius:10px;color:var(--s-fg);',
    'font-family:inherit;font-size:13.5px;padding:10px 12px;max-height:120px;min-height:40px;line-height:1.4;outline:none;}',
    '.' + NS + '-input textarea:focus{border-color:var(--s-accent);}',
    '.' + NS + '-send{flex:0 0 auto;background:linear-gradient(135deg,var(--s-accent),var(--s-accent2));color:#04110c;border:none;border-radius:10px;',
    'padding:0 16px;font-weight:700;font-size:13px;cursor:pointer;font-family:inherit;}',
    '.' + NS + '-send:disabled{opacity:.5;cursor:default;}'
  ].join('\n');

  var style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  var ICON = '<svg viewBox="0 0 24 24"><path d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm-3 9h-2v2h-2v-2h-2V9h2V7h2v2h2v2z"/></svg>';

  var launcher = el('button', NS + '-launcher ' + NS + '-root');
  launcher.setAttribute('aria-label', 'Open SniperTrader AI assistant');
  launcher.innerHTML = ICON + '<span class="' + NS + '-dot"></span>';

  var panel = el('div', NS + '-panel ' + NS + '-root ' + NS + '-hidden');
  panel.innerHTML =
    '<div class="' + NS + '-head">' +
      '<span class="' + NS + '-head-badge"></span>' +
      '<div class="' + NS + '-head-title">SniperTrader AI<div class="' + NS + '-head-sub">answers from platform docs · not financial advice</div></div>' +
      '<button class="' + NS + '-close" aria-label="Close">×</button>' +
    '</div>' +
    '<div class="' + NS + '-msgs"></div>' +
    '<div class="' + NS + '-input">' +
      '<textarea placeholder="Ask about indicators, courses, tools…" rows="1"></textarea>' +
      '<button class="' + NS + '-send">Send</button>' +
    '</div>';

  document.body.appendChild(launcher);
  document.body.appendChild(panel);

  var msgs = panel.querySelector('.' + NS + '-msgs');
  var textarea = panel.querySelector('textarea');
  var sendBtn = panel.querySelector('.' + NS + '-send');
  var closeBtn = panel.querySelector('.' + NS + '-close');

  function applyTheme() {
    var l = isLight();
    [launcher, panel].forEach(function (n) {
      if (l) n.classList.add(NS + '-light');
      else n.classList.remove(NS + '-light');
    });
  }

  function openPanel() {
    applyTheme();
    panel.classList.remove(NS + '-hidden');
    textarea.focus();
  }
  function closePanel() { panel.classList.add(NS + '-hidden'); }
  launcher.addEventListener('click', openPanel);
  closeBtn.addEventListener('click', closePanel);

  function scrollBottom() { msgs.scrollTop = msgs.scrollHeight; }

  function addMsg(role, html) {
    var m = el('div', NS + '-msg ' + (role === 'user' ? NS + '-msg-user' : NS + '-msg-asst'), html);
    msgs.appendChild(m);
    scrollBottom();
    return m;
  }

  function renderText(text) {
    var s = esc(text);
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\[(\d+)\]/g, '<button class="' + NS + '-cite" data-cite="$1" type="button">$1</button>');
    s = s.replace(/\n/g, '<br>');
    return s;
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return null;
    var wrap = el('div', NS + '-srcs');
    sources.forEach(function (s) {
      var sec = s.section ? '<span class="' + NS + '-src-section"> · ' + esc(s.section) + '</span>' : '';
      var row = el('div', NS + '-src', null);
      row.setAttribute('data-source-idx', s.index);
      row.innerHTML =
        '<div class="' + NS + '-src-top"><span class="' + NS + '-src-idx">' + s.index + '</span>' +
        '<span class="' + NS + '-src-title">' + esc(s.title) + sec + '</span></div>' +
        '<div class="' + NS + '-src-snip">' + esc(s.snippet) + '</div>';
      wrap.appendChild(row);
    });
    return wrap;
  }

  function flashSource(idx) {
    var row = panel.querySelector('.' + NS + '-src[data-source-idx="' + idx + '"]');
    if (!row) return;
    row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    row.classList.add(NS + '-flash');
    setTimeout(function () { row.classList.remove(NS + '-flash'); }, 1400);
  }

  function renderAssistant(content, sources) {
    var m = addMsg('assistant', renderText(content));
    if (sources && sources.length) {
      m.appendChild(renderSources(sources));
      m.appendChild(el('div', NS + '-fb',
        '<span style="font-size:11px;color:var(--s-muted);align-self:center;">Helpful?</span>' +
        '<button data-rating="5">👍</button><button data-rating="1">👎</button>'));
    }
    var citeButtons = m.querySelectorAll('.' + NS + '-cite');
    citeButtons.forEach(function (b) {
      b.addEventListener('click', function () { flashSource(b.getAttribute('data-cite')); });
    });
    return m;
  }

  function showTyping() {
    var t = el('div', NS + '-typing', '<span></span><span></span><span></span>');
    msgs.appendChild(t);
    scrollBottom();
    return t;
  }

  function showError(text) {
    var m = addMsg('assistant', '<span style="color:var(--s-muted)">' + esc(text) + '</span>');
    return m;
  }

  var busy = false;
  function send() {
    var text = textarea.value.trim();
    if (!text || busy) return;
    textarea.value = '';
    textarea.style.height = 'auto';
    addMsg('user', renderText(text));
    busy = true;
    sendBtn.disabled = true;
    var typing = showTyping();

    var payload = { message: text, session_id: sessionId() };
    fetch(API + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
    }).then(function (res) {
      typing.remove();
      if (!res.ok) {
        if (res.status === 429) return showError('Sending too quickly — give it a moment.');
        if (res.status === 403) return showError('That message was blocked.');
        return showError(res.body && res.body.error ? res.body.error : 'Something went wrong.');
      }
      var m = renderAssistant(res.body.content || '', res.body.sources || []);
      m.setAttribute('data-message-id', res.body.message_id || '');
      var fb = m.querySelector('.' + NS + '-fb');
      if (fb && res.body.message_id) {
        fb.querySelectorAll('button').forEach(function (b) {
          b.addEventListener('click', function () {
            fetch(API + '/feedback', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ message_id: Number(res.body.message_id), rating: Number(b.getAttribute('data-rating')) })
            }).catch(function () {});
            fb.innerHTML = '<span style="font-size:11px;color:var(--s-muted);">Thanks — feedback recorded.</span>';
          });
        });
      }
    }).catch(function () {
      typing.remove();
      showError('Can’t reach the assistant right now — check your connection.');
    }).finally(function () {
      busy = false;
      sendBtn.disabled = false;
    });
  }

  sendBtn.addEventListener('click', send);
  textarea.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
  textarea.addEventListener('input', function () {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  });

  if (window.MutationObserver) {
    var mo = new MutationObserver(applyTheme);
    mo.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }
})();
