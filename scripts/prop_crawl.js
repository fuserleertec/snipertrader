#!/usr/bin/env node
'use strict';
/**
 * scripts/prop_crawl.js — manual CLI for the Prop-Firm crawler (and the seed
 * generator). Runs the same refreshAll() path the cron endpoint uses, then
 * writes data/prop_firms.json.
 *
 * Usage:
 *   node scripts/prop_crawl.js            # refresh every firm, write data/
 *   node scripts/prop_crawl.js <id>       # refresh a single firm by id
 */
const { refreshAll, extractFirm } = require('../api/_lib/prop/crawler');
const store = require('../api/_lib/prop/store');

(async () => {
  const only = process.argv[2];
  if (only) {
    const data = store.load();
    const firm = (data.firms || []).find((f) => f.id === only);
    if (!firm) { console.error('unknown firm id: ' + only); process.exit(1); }
    console.log('Crawling ' + firm.name + ' (' + firm.website + ') ...');
    const r = await extractFirm(firm);
    if (r.ok) {
      console.log('OK — ' + JSON.stringify(r.firm, null, 2));
      const idx = data.firms.findIndex((f) => f.id === only);
      data.firms[idx] = r.firm;
      data.meta.last_refreshed = new Date().toISOString();
      store.save(data);
    } else {
      console.error('FAILED [' + (r.status || '?') + ']: ' + r.error);
      process.exit(1);
    }
    return;
  }

  console.log('Refreshing all prop firms ...');
  const { data, summary } = await refreshAll(store, {
    onProgress: (i, n, id, ok) => console.log(`  [${i}/${n}] ${id} ${ok ? 'OK' : 'FAILED'}`)
  });
  const wroteRepo = store.save(data);
  console.log('\nDone. updated=' + summary.updated + ' failed=' + summary.failed + ' persisted=' + (wroteRepo ? 'repo' : 'tmp-only'));
  console.log('Failed:');
  summary.results.filter((r) => !r.ok).forEach((r) => console.log('  - ' + r.id + ': ' + r.error));
})().catch((e) => { console.error(e); process.exit(1); });
