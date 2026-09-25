/* Renders checkout.html from assets/catalog.js. Prices and savings are computed. */
(function () {
  var C, cycle, platform, cart, subscriber;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
    });
  }

  function toast(msg) {
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { el.classList.remove('show'); }, 2400);
  }

  function planName(item) {
    if (item.monthly == null) return 'One-time';
    return cycle === 'annual' ? 'Annual' : 'Monthly';
  }

  function cadence(item) {
    if (item.monthly == null) return '';
    return cycle === 'annual' ? '/yr' : '/mo';
  }

  function offerChips(item) {
    var html = '';
    if (item.monthly != null && cycle === 'annual') {
      var ann = C.annualOffer(item.monthly, item.annual);
      html += '<span class="offer-chip">' + esc(ann.label) + '</span>';
    }
    if (item.includes) {
      var math = C.bundleMath(item, cycle);
      html += '<div class="vs-note">' + esc(math.vsParts.label) + ' (' + esc(C.money(math.vsParts.list)) + ' list)</div>';
    }
    return html;
  }

  function platformList(item) {
    if (item.platforms) return item.platforms.slice();
    if (!item.includes) return null;
    var plats = null;
    item.includes.forEach(function (id) {
      var part = C.findSellable(id);
      if (!part || !part.platforms) return;
      if (!plats) plats = part.platforms.slice();
      else plats = plats.filter(function (p) { return part.platforms.indexOf(p) > -1; });
    });
    return plats;
  }

  function platformOk(item) {
    var plats = platformList(item);
    if (!plats) return { ok: true, plats: null };
    return { ok: plats.indexOf(platform) > -1, plats: plats };
  }

  function priceHtml(item) {
    var amount = item.monthly == null ? item.once : C.cyclePrice(item, cycle);
    return '<div class="price-now">' + esc(C.money(amount)) + (cadence(item) ? '<sub>' + esc(cadence(item)) + '</sub>' : '') + '</div>';
  }

  function guarantee() {
    return '<div class="gtee">✓ 14-day money-back guarantee</div>';
  }

  function platTags(plats, ok) {
    if (!plats) return '';
    return '<div class="card-platforms">' + plats.map(function (p) {
      var on = p === platform;
      return '<span class="plat-tag"' + (on ? ' style="border-color:var(--gold);color:var(--gold)"' : '') + '>' + esc(p) + '</span>';
    }).join('') + '</div>' + (ok ? '' : '<div class="plat-miss">Not available on ' + esc(platform) + '. Switch platform to add this.</div>');
  }

  function cardShell(opts) {
    return '<article class="card ' + esc(opts.accent) + (opts.wide ? ' wide' : '') + '" data-sku="' + esc(opts.sku) + '">' +
      (opts.badge ? '<div class="badge-pop">' + esc(opts.badge) + '</div>' : '') +
      '<div class="card-body">' +
        '<div class="card-top"><div class="card-icon">' + opts.icon + '</div><div class="card-tier">' + esc(opts.tier) + '</div></div>' +
        '<h3>' + esc(opts.name) + '</h3>' +
        (opts.flag ? '<div class="stack-flag">' + esc(opts.flag) + '</div>' : '') +
        '<div class="card-desc">' + esc(opts.blurb) + '</div>' +
        (opts.features || '') +
        opts.price +
        opts.chips +
        guarantee() +
        (opts.plats || '') +
        '<button class="add-btn" data-sku="' + esc(opts.sku) + '" data-kind="' + esc(opts.kind) + '"' + (opts.disabled ? ' disabled' : '') + '>' + esc(opts.cta || '+ Add to order') + '</button>' +
      '</div>' +
      (opts.side || '') +
    '</article>';
  }

  function features(lines) {
    return '<ul class="card-features">' + lines.map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('') + '</ul>';
  }

  function renderEngines() {
    var mount = document.getElementById('engineGrid');
    if (!mount) return;
    var accents = { pivot: 'pivot', ict: 'ict', vwap: 'vwap', meridian: 'meridian', ofi: 'ofi' };
    mount.innerHTML = C.engines.map(function (item) {
      var gate = platformOk(item);
      return cardShell({
        sku: item.id,
        kind: 'engine',
        accent: accents[item.id] || 'mi',
        icon: item.id === 'ofi' ? '◈' : '◎',
        tier: item.tier,
        name: item.name,
        flag: item.featureLabel || '',
        blurb: item.blurb,
        price: priceHtml(item),
        chips: offerChips(item),
        plats: platTags(gate.plats, gate.ok),
        disabled: !gate.ok,
        cta: cart[item.id] ? '✓ In order' : '+ Add to order'
      });
    }).join('');
    mount.querySelectorAll('.add-btn.added, .add-btn').forEach(function (btn) {
      if (cart[btn.dataset.sku]) btn.classList.add('added');
    });
  }

  function renderIntelligence() {
    var suite = document.getElementById('intelSuite');
    var grid = document.getElementById('intelGrid');
    var item = C.intelligenceSuite;
    var math = C.bundleMath({ includes: item.includes, monthly: item.monthly, annual: item.annual }, cycle);
    var lines = math.parts.map(function (p) { return p.name; });
    if (suite) {
      var side = '<div class="wide-side"><div class="card-tier" style="margin-bottom:12px;">À la carte · ' + esc(C.money(math.vsParts.list)) + (cycle === 'annual' ? '/yr' : '/mo') + '</div><div class="breakdown">' +
        math.parts.map(function (p) {
          return '<div class="breakdown-row"><span>' + esc(p.name) + '</span><span class="bd-price">' + esc(C.money(p.price)) + '</span></div>';
        }).join('') +
        '<div class="breakdown-row" style="border-bottom:none;"><b>Suite price</b><b style="color:var(--acc);font-family:var(--ff-d);font-size:1.1rem;">' + esc(C.money(C.cyclePrice(item, cycle))) + (cycle === 'annual' ? '/yr' : '/mo') + '</b></div></div>' +
        '<div class="breakdown-save">' + esc(math.vsParts.label) + '</div></div>';
      suite.innerHTML = cardShell({
        sku: item.id,
        kind: 'suite',
        accent: 'combo',
        wide: true,
        badge: 'BEST VALUE',
        icon: '⚡',
        tier: 'Intelligence Suite',
        name: 'All 3 services. One subscription.',
        blurb: item.blurb,
        features: features(lines),
        price: priceHtml(item),
        chips: offerChips(item),
        side: side,
        cta: cart[item.id] ? '✓ In order' : '+ Add the suite'
      });
      var btn = suite.querySelector('.add-btn');
      if (btn && cart[item.id]) btn.classList.add('added');
    }
    if (grid) {
      grid.innerHTML = C.intelligence.map(function (svc) {
        return cardShell({
          sku: svc.id,
          kind: 'intel',
          accent: 'mi',
          icon: '◉',
          tier: 'Standalone',
          name: svc.name,
          blurb: svc.blurb,
          price: priceHtml(svc),
          chips: offerChips(svc),
          cta: cart[svc.id] ? '✓ In order' : '+ Add'
        });
      }).join('');
      grid.querySelectorAll('.add-btn').forEach(function (btn) {
        if (cart[btn.dataset.sku]) btn.classList.add('added');
      });
    }
  }

  function renderBundles() {
    var mount = document.getElementById('bundleGrid');
    if (!mount) return;
    mount.innerHTML = C.bundles.map(function (b) {
      var gate = platformOk(b);
      var math = C.bundleMath(b, cycle);
      return cardShell({
        sku: b.id,
        kind: 'bundle',
        accent: b.bestValue ? 'suite' : 'combo',
        badge: b.bestValue ? 'BEST VALUE' : '',
        icon: '▣',
        tier: 'Bundle',
        name: b.name,
        blurb: b.blurb,
        features: features(math.parts.map(function (p) { return p.name + ' · ' + C.money(p.price); })),
        price: priceHtml(b),
        chips: offerChips(b),
        plats: platTags(gate.plats, gate.ok),
        disabled: !gate.ok,
        cta: cart[b.id] ? '✓ In order' : '+ Add bundle'
      });
    }).join('');
    mount.querySelectorAll('.add-btn').forEach(function (btn) {
      if (cart[btn.dataset.sku]) btn.classList.add('added');
    });
  }

  function renderUpgrade() {
    var mount = document.getElementById('upgradeMount');
    if (!mount) return;
    var up = C.meridianUpgrade(cycle);
    var ann = C.annualOffer(up.to.monthly - up.from.monthly, up.to.annual - up.from.annual);
    mount.innerHTML =
      '<div class="card meridian">' +
        '<div class="card-body">' +
          '<div class="card-top"><div class="card-icon">↑</div><div class="card-tier">Meridian subscribers</div></div>' +
          '<h3>Upgrade to Meridian OFI</h3>' +
          '<div class="stack-flag">Includes Stacked Imbalance Logic</div>' +
          '<div class="card-desc">Move from Meridian Engine to Meridian OFI Engine. The credit equals your current Meridian list price. You pay the difference.</div>' +
          '<label class="sub-check"><input type="checkbox" id="meridianSubscriber"' + (subscriber ? ' checked' : '') + '> I have an active Meridian Engine subscription</label>' +
          (subscriber
            ? '<div class="breakdown">' +
                '<div class="breakdown-row"><span>Meridian OFI ' + (cycle === 'annual' ? 'annual' : 'monthly') + '</span><span class="bd-price">' + esc(C.money(up.full)) + '</span></div>' +
                '<div class="breakdown-row"><span>Meridian credit</span><span class="bd-price">−' + esc(C.money(up.credit)) + '</span></div>' +
                '<div class="breakdown-row" style="border-bottom:none;"><b>Due for the upgrade</b><b style="color:var(--acc)">' + esc(C.money(up.due)) + (cycle === 'annual' ? '/yr' : '/mo') + '</b></div>' +
              '</div>' +
              (cycle === 'annual' ? '<div class="vs-note" style="margin-top:10px">' + esc(ann.label) + ' on the upgrade difference</div>' : '') +
              guarantee() +
              '<p class="plat-miss" style="color:var(--text4)">Proration against unused time on a live subscription is not connected. This quote is the list-price difference only. TODO: wire a Stripe subscription update with proration. Price id: ' + esc(C.paymentPlaceholders.items['ofi-upgrade'][cycle]) + '</p>' +
              '<button class="add-btn" data-sku="ofi-upgrade" data-kind="upgrade">' + (cart['ofi-upgrade'] ? '✓ In order' : '+ Add upgrade') + '</button>'
            : '<p class="card-desc">Check the box if you already subscribe to Meridian Engine. Otherwise add Meridian OFI at the full price in the engines section.</p>' + guarantee()) +
        '</div></div>';
    var box = document.getElementById('meridianSubscriber');
    if (box) box.addEventListener('change', function () {
      subscriber = box.checked;
      renderAll();
    });
    var btn = mount.querySelector('.add-btn');
    if (btn && cart['ofi-upgrade']) btn.classList.add('added');
  }

  function renderCourses() {
    var mount = document.getElementById('courseGrid');
    if (!mount) return;
    mount.innerHTML = C.courses.map(function (course) {
      return cardShell({
        sku: course.id,
        kind: 'course',
        accent: 'ebook',
        icon: '✎',
        tier: course.monthly != null ? 'Membership' : 'One-time',
        name: course.name,
        blurb: course.blurb || 'One-time course purchase.',
        price: priceHtml(course),
        chips: offerChips(course),
        cta: cart[course.id] ? '✓ In order' : '+ Add'
      });
    }).join('');
    mount.querySelectorAll('.add-btn').forEach(function (btn) {
      if (cart[btn.dataset.sku]) btn.classList.add('added');
    });
  }

  function renderComing() {
    var mount = document.getElementById('comingGrid');
    if (!mount) return;
    mount.innerHTML = C.comingSoon.map(function (item) {
      return '<article class="card combo">' +
        '<div class="badge-pop">COMING SOON</div>' +
        '<div class="card-body">' +
          '<div class="card-tier">Training combo</div>' +
          '<h3>' + esc(item.name) + '</h3>' +
          '<div class="card-desc">' + esc(item.blurb) + '</div>' +
          features(item.contents) +
          '<div class="price-now">' + esc(C.money(item.once)) + '<sub> one-time</sub></div>' +
          guarantee() +
          '<a class="add-btn" style="display:block;text-align:center;text-decoration:none;" href="' + esc(item.href) + '">Join the waitlist</a>' +
        '</div></article>';
    }).join('');
  }

  function renderBill() {
    document.querySelectorAll('#billToggle button').forEach(function (btn) {
      btn.classList.toggle('on', btn.dataset.cycle === cycle);
    });
    document.querySelectorAll('.pfm-pill').forEach(function (btn) {
      btn.classList.toggle('selected', btn.dataset.platform === platform);
    });
    var hint = document.getElementById('platformHint');
    if (hint) hint.textContent = 'Engines and engine bundles are quoted for ' + platform + '. Market Intelligence does not need a platform. 14-day money-back guarantee on every paid product.';
  }

  function lookup(sku) {
    if (sku === 'ofi-upgrade') return { id: sku, name: 'Upgrade to Meridian OFI', upgrade: true };
    return C.byId(C.engines, sku) || C.byId(C.intelligence, sku) ||
      (sku === C.intelligenceSuite.id ? C.intelligenceSuite : null) ||
      C.byId(C.bundles, sku) || C.byId(C.courses, sku);
  }

  function addSku(sku) {
    var item = lookup(sku);
    if (!item) return;
    if (sku === 'ofi-upgrade') {
      if (!subscriber) { toast('Confirm an active Meridian subscription first'); return; }
      var up = C.meridianUpgrade(cycle);
      cart[sku] = {
        product: 'Upgrade to Meridian OFI',
        plan: planName(C.engines[4]),
        price: up.due,
        cadence: cycle === 'annual' ? '/yr' : '/mo',
        platform: 'TradingView',
        cycle: cycle,
        placeholder: C.paymentPlaceholders.items['ofi-upgrade'][cycle]
      };
    } else {
      var gate = platformOk(item);
      if (!gate.ok) { toast(item.name + ' is not available on ' + platform); return; }
      var amount = item.monthly == null ? item.once : C.cyclePrice(item, cycle);
      var ph = C.paymentPlaceholders.items[item.id];
      var placeholder = item.monthly == null ? ph.once : ph[cycle];
      cart[sku] = {
        product: item.name,
        plan: planName(item),
        price: amount,
        cadence: cadence(item),
        platform: gate.plats ? platform : null,
        cycle: cycle,
        placeholder: placeholder
      };
    }
    renderAll();
    toast(cart[sku].product + ' added');
  }

  function renderCart() {
    var entries = Object.keys(cart).map(function (k) { return [k, cart[k]]; });
    var total = entries.reduce(function (s, e) { return s + e[1].price; }, 0);
    var bar = document.getElementById('cartBar');
    document.getElementById('cartBarCount').textContent = entries.length;
    document.getElementById('cartBarTotal').textContent = C.money(total);
    document.getElementById('cartBarEmpty').style.display = entries.length ? 'none' : 'block';
    if (bar) bar.classList.toggle('show', entries.length > 0);
    var list = document.getElementById('checkoutItems');
    list.innerHTML = entries.map(function (e) {
      var it = e[1];
      return '<div class="co-item"><div><div class="co-item-name">' + esc(it.product) + '</div>' +
        '<div class="co-item-meta">' + (it.platform ? esc(it.platform) + ' · ' : '') + esc(it.plan) + ' · ' + esc(C.money(it.price)) + esc(it.cadence) + '</div>' +
        '<div class="co-item-meta">Payment id: ' + esc(it.placeholder) + '</div></div>' +
        '<div style="display:flex;align-items:center;gap:10px;"><div class="co-item-price">' + esc(C.money(it.price)) + '</div>' +
        '<button class="co-remove" data-key="' + esc(e[0]) + '">✕</button></div></div>';
    }).join('');
    list.querySelectorAll('.co-remove').forEach(function (b) {
      b.addEventListener('click', function () {
        delete cart[b.dataset.key];
        renderAll();
        toast('Item removed');
      });
    });
    document.getElementById('checkoutTotal').textContent = C.money(total);
    document.getElementById('completeBtn').textContent = 'Review placeholders — ' + C.money(total);
    var todos = document.getElementById('payTodos');
    if (todos) {
      todos.innerHTML = entries.map(function (e) {
        return '<li><code>' + esc(e[1].placeholder) + '</code> — ' + esc(e[1].product) + '</li>';
      }).join('') || '<li>Add a product to see its placeholder payment id.</li>';
    }
  }

  function renderAll() {
    renderBill();
    renderEngines();
    renderIntelligence();
    renderBundles();
    renderUpgrade();
    renderCourses();
    renderComing();
    renderCart();
    document.querySelectorAll('.add-btn[data-sku]').forEach(function (btn) {
      btn.addEventListener('click', function () { addSku(btn.dataset.sku); });
    });
  }

  function bindStatic() {
    document.querySelectorAll('#billToggle button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        cycle = btn.dataset.cycle;
        renderAll();
      });
    });
    document.querySelectorAll('.pfm-pill').forEach(function (btn) {
      btn.addEventListener('click', function () {
        platform = btn.dataset.platform;
        renderAll();
      });
    });
    var modal = document.getElementById('checkoutModal');
    document.getElementById('openCheckout').addEventListener('click', function () {
      if (!Object.keys(cart).length) { toast('Add something to your order first'); return; }
      modal.classList.add('active');
    });
    document.getElementById('closeCheckout').addEventListener('click', function () { modal.classList.remove('active'); });
    modal.addEventListener('click', function (e) { if (e.target === modal) modal.classList.remove('active'); });
    document.getElementById('completeBtn').addEventListener('click', function () {
      if (!Object.keys(cart).length) return;
      toast('No charge was made. Payment links are still placeholders.');
    });
  }

  function init() {
    C = window.SniperCatalog;
    if (!C) return;
    cycle = 'annual';
    platform = 'TradingView';
    cart = {};
    subscriber = false;
    bindStatic();
    renderAll();
    var params = new URLSearchParams(location.search);
    var presell = params.get('presell');
    if (presell && document.getElementById('coming')) {
      document.getElementById('coming').scrollIntoView();
      toast('Pre-sell is waitlist-only until a payment link is added.');
    }
  }

  window.SniperCheckout = { init: init };
})();
