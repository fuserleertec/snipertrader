/* ============================================================
   Extract the canonical seed data from the HTML mockup into
   backend/data/seed.json. Zero manual transcription — the source
   of truth is the mockup's own STAGES[] and DATA{} literals.

   NOTE: stages 6–8 are overridden to the "heartbeat" metrics from
   the build spec (STATUS Active / STATUS Monitoring / SIGNALS Live),
   which differ from the mockup's (SOURCES / PASS RATE / REFRESH).
============================================================ */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HTML_PATH = '/Users/snipertrader/Downloads/cognitive-pipeline-dashboard.html';
const src = readFileSync(HTML_PATH, 'utf8');

function grab(startMarker, endMarker) {
  const s = src.indexOf(startMarker);
  const e = src.indexOf(endMarker, s);
  if (s === -1 || e === -1) throw new Error(`markers not found: "${startMarker}" … "${endMarker}"`);
  const body = src.slice(s + startMarker.length, e).trim().replace(/;\s*$/, '');
  return new Function(`return (${body})`)();
}

const STAGES_HTML = grab('const STAGES = ', 'function renderPipeline');
const DATA_HTML = grab('const DATA = ', '// Materialize rows');

// Re-implement the mockup's row() mapper exactly.
function row(a) {
  const [
    ticker, name, signal, last, chg, target, conviction, stances,
    drift, similarity, sigma, epsSurprise, reason, source, latency, activityNote,
  ] = a;
  return {
    ticker,
    company: name,
    signal,
    last,
    chg,
    target,
    conviction: Number(conviction),
    engines: { K: stances[0], S: stances[1], M: stances[2], F: stances[3], Q: stances[4] },
    drift: Number(drift),
    similarity: Number(similarity),
    sigma: Number(sigma),
    epsSurprise: Number(epsSurprise),
    reason,
    source,
    latency,
    activityNote: activityNote || null,
  };
}

const picks = [];
const modes = {};
for (const mode of Object.keys(DATA_HTML)) {
  for (const category of Object.keys(DATA_HTML[mode])) {
    for (const arr of DATA_HTML[mode][category]) {
      picks.push({ ...row(arr), mode, category });
    }
  }
  modes[mode] = Object.keys(DATA_HTML[mode]);
}

// Stage overrides: keep mockup for 1–5, adopt the spec's "heartbeat" status
// metrics for 6–8.
const OVERRIDES = {
  6: { name: 'Fundamental Agent', plabel: 'STATUS', pvalue: 'Active', status: 'Active' },
  7: { name: 'Alpha Screening', plabel: 'STATUS', pvalue: 'Monitoring', status: 'Monitoring' },
  8: { name: 'Recommended Picks', plabel: 'SIGNALS', pvalue: 'Live', status: 'Live' },
};
const STATUS_DEFAULT = { 1: 'Running', 2: 'Installed', 3: 'Running', 4: 'Running', 5: 'Running' };

const pipelineStages = STAGES_HTML.map((s, i) => {
  const id = i + 1;
  const o = OVERRIDES[id] || {};
  return {
    id,
    name: o.name || s.name,
    desc: s.desc,
    plabel: o.plabel || s.plabel,
    pvalue: o.pvalue || s.pvalue,
    status: o.status || STATUS_DEFAULT[id],
  };
});

const seed = {
  timestamp: new Date().toISOString(),
  pipelineStages,
  picks,
  vetoes: [],
};

mkdirSync(join(__dirname, 'data'), { recursive: true });
writeFileSync(join(__dirname, 'data', 'seed.json'), JSON.stringify(seed, null, 2));
console.log(`Wrote ${picks.length} picks, ${pipelineStages.length} stages → backend/data/seed.json`);
console.log('Modes:', JSON.stringify(modes));
