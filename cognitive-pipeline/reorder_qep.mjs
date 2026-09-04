import fs from 'fs';
const p = '/Users/snipertrader/snipertrader/stock_picks.html';
let s = fs.readFileSync(p, 'utf8');

function rep(oldS, newS) {
  if (!s.includes(oldS)) throw new Error('NOT FOUND: ' + oldS.slice(0, 80));
  s = s.split(oldS).join(newS);
}

// ── 1. Extract the QEP block (style + section + script) ──────────────
const cssMarker = '/* ── Quantum Ensemble Picks (synthetic demo) ── */';
const cssIdx = s.indexOf(cssMarker);
if (cssIdx < 0) throw new Error('QEP CSS marker not found');
const styleStart = s.lastIndexOf('<style>', cssIdx);
const scriptBodyIdx = s.indexOf('var PICKS = [', styleStart);
const scriptEnd = s.indexOf('</script>', scriptBodyIdx);
const blockEnd = scriptEnd + '</script>'.length;
const block = s.slice(styleStart, blockEnd).replace(/\s+$/, '');

// ── 2. Remove it from its current position (between Categorized + Narrative) ──
s = s.slice(0, styleStart) + s.slice(blockEnd);

// ── 3. Insert before the Live Simulation View section ────────────────
const liveAnchor = '<!-- SECTION 2: Live Simulation View → Ranked Velocity Leaderboard -->';
const insIdx = s.indexOf(liveAnchor);
if (insIdx < 0) throw new Error('Live Sim anchor not found');
s = s.slice(0, insIdx) + block + '\n\n' + s.slice(insIdx);

// ── 4. Renumber .ix spans (with h2 text for uniqueness) ──────────────
rep('<span class="ix">04</span><h2>Quantum Ensemble Picks</h2>',
    '<span class="ix">02</span><h2>Quantum Ensemble Picks</h2>');
rep('<span class="ix">02</span><h2>Live Market Simulation View</h2>',
    '<span class="ix">03</span><h2>Live Market Simulation View</h2>');
rep('<span class="ix">03</span><h2>Categorized Stock Picks</h2>',
    '<span class="ix">04</span><h2>Categorized Stock Picks</h2>');

// ── 5. Fix HTML section comments (full-string, unambiguous) ──────────
rep('<!-- SECTION 4: Quantum Ensemble Picks (synthetic demo) -->',
    '<!-- SECTION 2: Quantum Ensemble Picks (synthetic demo) -->');
rep('<!-- SECTION 2: Live Simulation View → Ranked Velocity Leaderboard -->',
    '<!-- SECTION 3: Live Simulation View → Ranked Velocity Leaderboard -->');
rep('<!-- SECTION 3: Picks Grid -->',
    '<!-- SECTION 4: Picks Grid -->');
rep('<!-- SECTION 4: Narrative -->',
    '<!-- SECTION 5: Narrative -->');
rep('<!-- SECTION 5: Execution -->',
    '<!-- SECTION 6: Execution -->');
rep('<!-- SECTION 6: Recon Audit -->',
    '<!-- SECTION 7: Recon Audit -->');
rep('<!-- SECTION 7: Education -->',
    '<!-- SECTION 8: Education -->');

// ── 6. Fix stale cross-references ────────────────────────────────────
rep('/* leaderboard (Section 02 ranked velocity) */',
    '/* leaderboard (Section 03 ranked velocity) */');
rep('The Recon Audit (Section 06) candidates',
    'The Recon Audit (Section 07) candidates');

// ── 7. Cap the leaderboard at 20 tickers ─────────────────────────────
rep('  scored.sort((a,b)=>b.netBias-a.netBias);     // top run-up → bottom dump\n  LEADERBOARD=scored;\n  renderLeaderboard(scored);',
    '  scored.sort((a,b)=>b.netBias-a.netBias);     // top run-up → bottom dump\n  LEADERBOARD=scored.slice(0,20);              // cap leaderboard at 20 tickers\n  renderLeaderboard(LEADERBOARD);');
rep('  return scored;', '  return LEADERBOARD;');

fs.writeFileSync(p, s);
console.log('OK — wrote', p);
