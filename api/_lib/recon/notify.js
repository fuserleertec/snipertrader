'use strict';
// api/_lib/recon/notify.js
// ---------------------------------------------------------------------------
// Layer 6.2 — alert & digest formatting. Formats the recon payload into
// Telegram/email-ready plain text. DELIVERY is HONESTLY GATED: if the channel
// credentials are not set, send* returns {delivered:false, reason:'not
// configured'} — it never fabricates a delivery.
// ---------------------------------------------------------------------------

function fmtTime(iso) {
  try { return new Date(iso).toLocaleString('en-US', { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' }); }
  catch (_) { return iso || '—'; }
}

// Plain-text digest of a recon payload (works for Telegram + email bodies).
function formatDigest(p) {
  const picks = p.picks || [], crypto = p.crypto || [], alerts = p.sellAlerts || [], orders = p.simulatedOrders || [];
  const lines = [];
  lines.push(`🔭 SNIPERTRADER PRE-RUN RECON — ${fmtTime(p.generatedAt)}`);
  lines.push(`universe ${p.universeScanned} · picks ${picks.length} · crypto ${crypto.length} · simulated orders ${orders.length} · dump alerts ${alerts.length}`);
  lines.push('');
  const decs = (p.decisions || []).filter(d => d.signal !== 'HOLD');
  if (decs.length) {
    lines.push('SIGNALS:');
    for (const d of decs) lines.push(`  ${d.signal} ${d.symbol} [${d.assetType}] weighted ${d.weightedScore}/100${d.sizing ? ` · size $${d.sizing.dollars}` : ''}`);
  } else {
    lines.push('SIGNALS: none (all HOLD, or zero passed confirmation gates).');
  }
  if (alerts.length) {
    lines.push('');
    lines.push('⚠️ DUMP/EXIT ALERTS:');
    for (const a of alerts) for (const x of a.alerts) lines.push(`  ${x.level} ${a.symbol}: ${x.msg}`);
  }
  lines.push('');
  lines.push('SIMULATION ONLY — no orders placed. Gated inputs: ' + ((p.screeningGaps || []).length + (p.dumpGated || []).length) + ' (see payload for the full list).');
  return lines.join('\n');
}

// Telegram delivery — gated behind TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.
async function sendTelegram(text) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chat = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chat) return { delivered: false, channel: 'telegram', reason: 'TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set' };
  try {
    const r = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chat, text })
    });
    const j = await r.json();
    return { delivered: !!(j && j.ok), channel: 'telegram', reason: j && j.ok ? null : (j.description || 'send failed') };
  } catch (e) {
    return { delivered: false, channel: 'telegram', reason: String(e.message || e) };
  }
}

module.exports = { formatDigest, sendTelegram };
