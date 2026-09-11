'use strict';
/**
 * api/_lib/traderedge/policy.js — Layer 3: graduated intervention orchestrator.
 *
 * Policy over the graph, not if-then rules. Force is graduated:
 *   0 none · 1 nudge · 2 friction · 3 gate
 * Every intervention is logged to `traderedge_interventions`; the trader's
 * response (accept/override) becomes LABELED training data for the bandit.
 * v1 uses a transparent deterministic ladder; Thompson-sampling arm selection
 * is the documented next step once enough override labels accumulate.
 */
const db = require('./db');
const fusion = require('./fusion');

function chooseLevel(bundle, fusionResult) {
  if (!fusionResult.actuate) return 0;
  const state = String(bundle.state || '').toUpperCase();
  const drawdownBreach = !!bundle.drawdownBreach;
  if (state === 'REVENGE' || drawdownBreach) return 3;
  if (Number(bundle.losingStreak) >= 3 || bundle.sizeUp) return 2;
  return 1;
}

function actionFor(level, bundle) {
  const state = String(bundle.state || '').toUpperCase();
  switch (level) {
    case 3: return {
      action: state === 'REVENGE' ? 'block_revenge' : 'block_drawdown',
      message: state === 'REVENGE'
        ? 'Revenge state detected. Order entry blocked for 15 minutes — step away, log a DUMP, then return.'
        : 'Drawdown limit breached. Order entry blocked — review your last 3 trades before resuming.'
    };
    case 2: return {
      action: bundle.sizeUp ? 'confirm_size' : 'confirm_after_streak',
      message: bundle.sizeUp
        ? 'Size increase detected during a losing streak. Confirm your size and type a reason to proceed.'
        : 'You are on a losing streak. A 5-second hold before the next entry — confirm you are following your plan.'
    };
    case 1: return {
      action: 'nudge',
      message: 'Conditions look suboptimal (fatigue / volatility). A quick pause before this trade?'
    };
    default: return { action: 'none', message: '' };
  }
}

async function intervene(bundle) {
  const fusionResult = fusion.score(bundle);
  const level = chooseLevel(bundle, fusionResult);
  const { action, message } = actionFor(level, bundle);

  let interventionId = null;
  if (level > 0) {
    const row = await db.query(
      `insert into traderedge_interventions (ts, trader_id, level, action, message)
       values (now(), $1, $2, $3, $4) returning intervention_id`,
      [String(bundle.traderId || 'local-trader').slice(0, 120), level, action, message]
    );
    interventionId = row.rows[0].intervention_id;
  }

  return { level, action, message, interventionId, evidence: fusionResult.evidence, hits: fusionResult.hits };
}

async function respond(interventionId, decision, note) {
  const dec = decision === 'override' ? 'override' : 'accept';
  await db.query(
    `update traderedge_interventions
     set decision = $1, note = $2, responded_at = now()
     where intervention_id = $3`,
    [dec, String(note || '').slice(0, 500), interventionId]
  );
  return { interventionId, decision: dec };
}

module.exports = { intervene, respond, chooseLevel };
