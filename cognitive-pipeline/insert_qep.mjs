import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');
const seedPath = join(__dirname, 'frontend/src/data/seed.json');
const fragPath = join(__dirname, 'qep_fragment.html');
const pagePath = join(root, 'stock_picks.html');

const seed = JSON.parse(readFileSync(seedPath, 'utf8'));
const frag = readFileSync(fragPath, 'utf8');
let page = readFileSync(pagePath, 'utf8');

// 1) inject the picks data
const data = JSON.stringify(seed.picks);
if (!frag.includes('__QEP_PICKS__')) throw new Error('fragment missing __QEP_PICKS__ placeholder');
const section = frag.replace('__QEP_PICKS__', data);

// 2) insert before SECTION 4 (Narrative)
const anchor = '  <!-- SECTION 4: Narrative -->';
if (page.split(anchor).length !== 2) throw new Error('insertion anchor not found / not unique');
page = page.replace(anchor, section.trimEnd() + '\n\n' + anchor);

// 3) renumber subsequent sections (04..07 -> 05..08)
const renames = [
  ['>04</span><h2>Narrative', '>05</span><h2>Narrative'],
  ['>05</span><h2>Execution', '>06</span><h2>Execution'],
  ['>06</span><h2>Recon', '>07</span><h2>Recon'],
  ['>07</span><h2>Understanding', '>08</span><h2>Understanding'],
];
for (const [from, to] of renames) {
  if (!page.includes(from)) throw new Error('rename target missing: ' + from);
  page = page.replace(from, to);
}

writeFileSync(pagePath, page);

// verify
const checks = {
  'fragment inserted once': page.split('id="qepBody"').length === 2,
  'placeholder replaced': !page.includes('__QEP_PICKS__'),
  'ix renumbered': page.includes('>08</span><h2>Understanding') && !page.includes('>07</span><h2>Understanding'),
  'new section present': page.includes('>04</span><h2>Quantum Ensemble Picks'),
};
console.log(JSON.stringify(checks, null, 2));
const ix = [...page.matchAll(/class="ix">(\d+)<\/span><h2>([^<]+)/g)].map((m) => m[1] + ' ' + m[2]);
console.log('section ix map:', ix.join(' | '));
console.log('file size:', page.length, 'bytes');
