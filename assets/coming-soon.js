/* Fills a coming-soon combo page from SniperCatalog. Does not send email. */
(function () {
  function boot() {
    var C = window.SniperCatalog;
    var root = document.getElementById('combo');
    if (!C || !root) return;
    var id = root.getAttribute('data-combo');
    var item = C.byId(C.comingSoon, id);
    if (!item) return;
    document.title = item.name + ' — coming soon | SniperTrader.ai';
    root.querySelector('[data-field="name"]').textContent = item.name;
    root.querySelector('[data-field="blurb"]').textContent = item.blurb;
    root.querySelector('[data-field="price"]').textContent = C.money(item.once);
    root.querySelector('[data-field="contents"]').innerHTML = item.contents.map(function (line) {
      return '<li>' + line.replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }) + '</li>';
    }).join('');
    var ph = C.paymentPlaceholders.items[id];
    var note = root.querySelector('[data-field="pay"]');
    if (note && ph) note.textContent = 'Pre-sell payment link: ' + ph.paymentLinkOnce + ' · Stripe price: ' + ph.once;

    var form = document.getElementById('waitlist');
    var done = document.getElementById('waitlistDone');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var email = (form.email.value || '').trim();
      if (!email || email.indexOf('@') < 1) {
        form.email.focus();
        return;
      }
      try {
        var key = 'sniper-waitlist-' + id;
        var list = JSON.parse(localStorage.getItem(key) || '[]');
        if (list.indexOf(email) < 0) list.push(email);
        localStorage.setItem(key, JSON.stringify(list));
      } catch (err) {}
      form.hidden = true;
      done.hidden = false;
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
