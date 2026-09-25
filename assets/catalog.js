/* SniperTrader.ai — product & price catalog (single source of truth).
   Savings labels are computed here. Do not hard-code percentages in pages.
   Payment IDs below are placeholders. Do not create or update live Stripe
   products from this file. */
(function (root, factory) {
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.SniperCatalog = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  var PLATFORMS = ['TradingView', 'Thinkorswim', 'NinjaTrader'];

  function money(n) {
    var v = Math.round(Number(n) || 0);
    return '$' + v.toLocaleString('en-US');
  }

  /** Annual vs paying monthly for 12 months. "2 months free" only when annual === 10× monthly. */
  function annualOffer(monthly, annual) {
    var list = monthly * 12;
    var saved = list - annual;
    var pct = list > 0 ? Math.round((saved / list) * 100) : 0;
    var twoMonthsFree = annual === monthly * 10;
    return {
      list: list,
      saved: saved,
      pct: pct,
      twoMonthsFree: twoMonthsFree,
      label: twoMonthsFree ? '2 months free' : ('Save ' + pct + '%')
    };
  }

  /** Bundle price vs the sum of its parts on the same billing cycle. */
  function bundleOffer(listPrice, bundlePrice) {
    var saved = listPrice - bundlePrice;
    var pct = listPrice > 0 ? Math.round((saved / listPrice) * 100) : 0;
    return {
      list: listPrice,
      saved: saved,
      pct: pct,
      label: 'Save ' + pct + '% vs buying separately'
    };
  }

  function byId(list, id) {
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }

  var engines = [
    {
      id: 'pivot',
      name: 'No Repaint Pivot',
      blurb: 'Entry-level non-repaint structure, anchored VWAP, and a trend cloud. Signals confirm at the bar close.',
      monthly: 79,
      annual: 599,
      platforms: ['TradingView', 'Thinkorswim'],
      href: '/NoRepaint_Pivot_indicator.html',
      tier: 'Engine 01'
    },
    {
      id: 'ict',
      name: 'USME ICT Core',
      blurb: '3-Gate Smart Money Concepts — bias, liquidity, and the entry model.',
      monthly: 199,
      annual: 1999,
      platforms: PLATFORMS.slice(),
      href: '/USME_ICT_Core.html',
      tier: 'Engine 02'
    },
    {
      id: 'vwap',
      name: 'USME VWAP Suite',
      blurb: 'Multi-anchor VWAP with deviation bands and graded conviction.',
      monthly: 249,
      annual: 2490,
      platforms: PLATFORMS.slice(),
      href: '/USME_VWAP_Elite_Suite.html',
      tier: 'Engine 03'
    },
    {
      id: 'meridian',
      name: 'Meridian Engine',
      blurb: 'Regime-aware lattice, liquidity memory, and path tracking.',
      monthly: 449,
      annual: 4490,
      platforms: ['TradingView'],
      href: '/Meridian_Engine.html',
      tier: 'Engine 04'
    },
    {
      id: 'ofi',
      name: 'Meridian OFI Engine',
      blurb: 'Apex order-flow intelligence on Meridian — CVD, absorption, and imbalance.',
      includesStackedImbalance: true,
      featureLabel: 'Includes Stacked Imbalance Logic',
      monthly: 599,
      annual: 5990,
      platforms: ['TradingView'],
      href: '/Meridian_OFI_Engine.html',
      featureHref: '/Meridian_OFI_Stacked_imbalance_logic_Engine.html',
      tier: 'Engine 05'
    }
  ];

  var intelligence = [
    {
      id: 'preflight',
      name: 'Preflight Protocol',
      blurb: 'Daily pre-market playbook — bias, key levels, and catalysts.',
      monthly: 49,
      annual: 490,
      href: '/traderedge_preflight.html'
    },
    {
      id: 'forecaster',
      name: 'Market Forecaster',
      blurb: 'Structure, liquidity zones, and price targets from live market data.',
      monthly: 49,
      annual: 490,
      href: '/market_forecaster.html'
    },
    {
      id: 'radar',
      name: 'Daily Market Radar',
      blurb: 'Ranked daily watchlist — structure, volume, filings, and news.',
      monthly: 79,
      annual: 790,
      href: '/market_radar.html'
    }
  ];

  var intelligenceSuite = {
    id: 'intel-suite',
    name: 'Intelligence Suite',
    blurb: 'Preflight Protocol, Market Forecaster, and Daily Market Radar — one subscription.',
    monthly: 119,
    annual: 1190,
    bestValue: true,
    includes: ['preflight', 'forecaster', 'radar'],
    href: '/checkout.html#intelligence-suite'
  };

  var courses = [
    { id: 'challenge', name: '30-Day Funded Challenge Blueprint', once: 297, href: '/30_days_funded_challenge.html' },
    { id: 'masterplan', name: 'Prop Firm Masterplan', once: 447, href: '/Prop_firm_MasterPlan.html' },
    { id: 'futures', name: 'USME Futures Mastercourse', once: 797, href: '/USME_Masterplan_Course.html' },
    { id: 'complete', name: 'The Complete Course / MasterClass', once: 1297, href: '/complete_snipertrader_course.html' },
    { id: 'academy', name: 'Sniper Academy', blurb: 'Foundations, live room, and mentorship.', monthly: 247, annual: 2297, href: '/Traders_Couch.html' }
  ];

  var comingSoon = [
    {
      id: 'funded-path',
      name: 'Funded Path Bundle',
      blurb: '30-Day Funded Challenge, Prop Firm Masterplan, and Preflight Protocol.',
      once: 597,
      href: '/bundle_funded_path.html',
      contents: ['30-Day Funded Challenge Blueprint', 'Prop Firm Masterplan', 'Preflight Protocol']
    },
    {
      id: 'usme-edu',
      name: 'USME Education Pack',
      blurb: 'The USME course stack in one pre-sell pack.',
      once: 1497,
      href: '/bundle_usme_education.html',
      contents: ['USME ICT Core companion course', 'USME VWAP Suite course', 'USME Futures Mastercourse']
    },
    {
      id: 'meridian-mastery',
      name: 'Meridian Mastery',
      blurb: 'Meridian OFI Engine, the Stacked Imbalance course, and live Q&A.',
      once: 697,
      href: '/bundle_meridian_mastery.html',
      contents: ['Meridian OFI Engine', 'Stacked Imbalance course', 'Live Q&A']
    }
  ];

  function findSellable(id) {
    return byId(engines, id) || byId(intelligence, id) || (intelligenceSuite.id === id ? intelligenceSuite : null) || byId(courses, id);
  }

  function cyclePrice(item, cycle) {
    if (item.once != null && item.monthly == null) return item.once;
    return cycle === 'annual' ? item.annual : item.monthly;
  }

  function componentList(includeIds, cycle) {
    var total = 0;
    var parts = [];
    includeIds.forEach(function (id) {
      var item = findSellable(id);
      if (!item) return;
      var price = cyclePrice(item, cycle);
      total += price;
      parts.push({ id: id, name: item.name, price: price });
    });
    return { total: total, parts: parts };
  }

  var bundles = [
    {
      id: 'starter',
      name: 'Starter Precision',
      blurb: 'No Repaint Pivot, Preflight Protocol, and Market Forecaster.',
      monthly: 129,
      annual: 1290,
      includes: ['pivot', 'preflight', 'forecaster'],
      bestValue: false
    },
    {
      id: 'smart-money',
      name: 'Smart Money Stack',
      blurb: 'USME ICT Core, USME VWAP Suite, and the Intelligence Suite.',
      monthly: 449,
      annual: 4490,
      includes: ['ict', 'vwap', 'intel-suite'],
      bestValue: false
    },
    {
      id: 'flagship-ofi',
      name: 'Flagship Meridian OFI',
      blurb: 'Meridian OFI Engine (includes Stacked Imbalance Logic) plus the Intelligence Suite.',
      monthly: 649,
      annual: 6490,
      includes: ['ofi', 'intel-suite'],
      bestValue: true
    },
    {
      id: 'full-suite',
      name: 'Everything / Full Suite',
      blurb: 'All 5 engines plus the Intelligence Suite.',
      monthly: 999,
      annual: 9990,
      includes: ['pivot', 'ict', 'vwap', 'meridian', 'ofi', 'intel-suite'],
      bestValue: true
    }
  ];

  function bundleMath(bundle, cycle) {
    var list = componentList(bundle.includes, cycle);
    var price = cyclePrice(bundle, cycle);
    return {
      price: price,
      parts: list.parts,
      vsParts: bundleOffer(list.total, price),
      annual: annualOffer(bundle.monthly, bundle.annual)
    };
  }

  /** Credit equals the current Meridian plan price. Due = OFI price − Meridian price. */
  function meridianUpgrade(cycle) {
    var from = byId(engines, 'meridian');
    var to = byId(engines, 'ofi');
    var credit = cyclePrice(from, cycle);
    var full = cyclePrice(to, cycle);
    return {
      from: from,
      to: to,
      cycle: cycle,
      credit: credit,
      full: full,
      due: full - credit,
      annual: annualOffer(full - credit === 0 ? 0 : (to.monthly - from.monthly), to.annual - from.annual)
    };
  }

  /**
   * Placeholder payment handles. Replace each TODO before charging customers.
   * These are not live Stripe price IDs.
   */
  var paymentPlaceholders = {
    note: 'TODO: create Stripe prices (or payment links) and paste the IDs here. This catalog does not call Stripe.',
    items: {}
  };

  function placeholderFor(item) {
    var entry = { id: item.id, name: item.name };
    if (item.once != null && item.monthly == null) {
      entry.once = 'TODO_STRIPE_PRICE_' + item.id.toUpperCase().replace(/-/g, '_') + '_ONCE';
      entry.paymentLinkOnce = 'TODO_PAYMENT_LINK_' + item.id.toUpperCase().replace(/-/g, '_') + '_ONCE';
    } else {
      entry.monthly = 'TODO_STRIPE_PRICE_' + item.id.toUpperCase().replace(/-/g, '_') + '_MONTHLY';
      entry.annual = 'TODO_STRIPE_PRICE_' + item.id.toUpperCase().replace(/-/g, '_') + '_ANNUAL';
      entry.paymentLinkMonthly = 'TODO_PAYMENT_LINK_' + item.id.toUpperCase().replace(/-/g, '_') + '_MONTHLY';
      entry.paymentLinkAnnual = 'TODO_PAYMENT_LINK_' + item.id.toUpperCase().replace(/-/g, '_') + '_ANNUAL';
    }
    return entry;
  }

  engines.concat(intelligence).concat([intelligenceSuite]).concat(bundles).concat(courses).concat(comingSoon).forEach(function (item) {
    paymentPlaceholders.items[item.id] = placeholderFor(item);
  });
  paymentPlaceholders.items['ofi-upgrade'] = {
    id: 'ofi-upgrade',
    name: 'Upgrade to Meridian OFI',
    monthly: 'TODO_STRIPE_PRICE_OFI_UPGRADE_MONTHLY',
    annual: 'TODO_STRIPE_PRICE_OFI_UPGRADE_ANNUAL',
    paymentLinkMonthly: 'TODO_PAYMENT_LINK_OFI_UPGRADE_MONTHLY',
    paymentLinkAnnual: 'TODO_PAYMENT_LINK_OFI_UPGRADE_ANNUAL',
    proration: 'TODO: Stripe subscription update with proration is not wired. The quote is list-price difference only.'
  };

  var retired = [
    {
      id: 'chart-analyzer',
      name: 'AI Chart Analyzer',
      page: '/traderedge_chartai.html',
      replacement: '/checkout.html#intelligence-suite',
      replacementName: 'Intelligence Suite'
    },
    {
      id: 'pre-run',
      name: 'Daily Pre-Run Detection',
      page: '/market_terminal.html#radar',
      replacement: '/checkout.html#intelligence-suite',
      replacementName: 'Intelligence Suite'
    }
  ];

  return {
    platforms: PLATFORMS,
    engines: engines,
    intelligence: intelligence,
    intelligenceSuite: intelligenceSuite,
    bundles: bundles,
    courses: courses,
    comingSoon: comingSoon,
    retired: retired,
    paymentPlaceholders: paymentPlaceholders,
    money: money,
    annualOffer: annualOffer,
    bundleOffer: bundleOffer,
    findSellable: findSellable,
    cyclePrice: cyclePrice,
    componentList: componentList,
    bundleMath: bundleMath,
    meridianUpgrade: meridianUpgrade,
    byId: byId
  };
});
