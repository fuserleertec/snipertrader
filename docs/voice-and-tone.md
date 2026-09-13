# Voice & Tone — Command Portal

The portal is **not** a generic SaaS dashboard. It is a calm, surgical control
surface for a trader whose edge depends on precision and discipline. Every
string is written to sound like it belongs to `snipertrader.ai` — the same
person who wrote "Precision over prediction."

## Brand keywords (from homepage copy)

**surgical · precision · institutional · calm · non-repainting · neural
baseline · discipline gate · liquidity · structure · execution**

The footer tagline carries the whole tone: **"Calm. Precise. Deliberate."**

## Principles

1. **Calm, not chatty.** Short declarative sentences. No exclamation points,
   no "Great!" / "Oops!" / "Awesome!".
2. **Surgical, not vague.** Name the mechanism — "non-repainting engine
   triggers", "neural baseline", "discipline gates" — instead of filler.
3. **Institutional, not consumer.** "License", "Authorize", "Execute",
   "Session", "Signal" — never "Plan", "Profile pic", "Get started!".
4. **Honest about data.** Simulated sections are visibly badged `SIMULATION`;
   demo data is badged `DEMO DATA`. Nothing is dressed up as live when it is not.
5. **Risk-aware.** No "guaranteed returns" language; the site-wide disclaimer
   stays in the footer.

## Replace (generic SaaS → brand)

| ❌ Avoid | ✅ Use |
|---|---|
| Dashboard | Command Portal |
| Notifications | Signal Alerts |
| Account Settings | Trader Profile |
| Billing & Plan | License & Billing |
| Settings | Trader Profile / Preferences |
| Get started | Authorize / Execute |
| Log in | Authorize (button) / Sign in (copy) |
| Upgrade / Downgrade | Upgrade License |
| Log out | Sign Out |
| Loading… / ◌ Loading | (skeleton shimmer — no text) |

## Button voice (action-first, imperative, one or two words)

Authorize · Execute · Review · Export · Refresh · Retry · Re-open · Revoke ·
Sign Out · Run Pre-Market Scan · Open Market Terminal · Open Chart AI ·
Manage Billing · Upgrade License · Sign out all others · Reveal PII

## Empty-state voice

> "No alerts in the last 7 days. Last check: 2026-09-12 06:42 EST."
> — with CTA **"Run Pre-Market Scan"**.

> "No signals logged yet." → **"Open Market Terminal"**

> "No pre-flight scan logged for today." → **"Run Pre-Market Scan"**

> "No saved analyses yet. Open a chart to generate one." → **"Open Chart AI"**

> "No prop firm accounts linked yet." → **"Open Command Center"**

Pattern: state the *fact* calmly, then offer one relevant action. No apology.

## Error-state voice

> "Connection interrupted. [reason]. Retry or contact support."

Logged to `console.error` for debugging. A single **Retry** action re-runs the
data load. Never blames the user; never shows raw stack traces in the UI.

## Section copy (as shipped)

- **Overview** — "Precision Suite · Elite license · Last check 06:42 EST"
- **Intelligence Feed** — "Live bias scores, key levels, and the catalyst
  calendar — the Market Intelligence Engine, at a glance."
- **Signal Log** — "Every scored signal from the ML screener — module, market,
  session P&L, and the primary trigger."
- **Pre-Flight Status** — "Neural baseline, the discipline gates, and
  authorization state — logged before every session."
- **Chart Analysis History** — "Saved structural analyses — FVG and order block
  flags, timeframe snapshots, ready to re-open."
- **Discipline Dashboard** — "Streak milestones, breach warnings, post-session
  reviews, and the psychology score."
- **Prop Firm Command Center** — "Accounts, rules, drawdown, payouts, and
  challenge progress."
- **License & Billing** — "Manage your Precision Suite access — plan, invoices,
  license keys, and downloads."
- **Trader Profile** — "Neural baseline and session preferences — plus your
  signal alert configuration."
- **Security** — "Passkey & Face ID, two-factor auth, active sessions, and
  device fingerprint."

## Names to never leak into public copy

No proprietary engine names (Kronos, MiroFish) and no indicator "recipe" in
any user-facing string. Signal alerts are described as "non-repainting engine
triggers and risk flags" — plain-English, neutral labels.
