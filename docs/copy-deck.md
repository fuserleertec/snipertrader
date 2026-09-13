# Copy Deck — Command Portal

Authoritative string inventory for `admin.html`. Keep this file in sync with
the markup; it is the single place to audit microcopy.

## Rename map (old admin → Command Portal)

| Legacy label | New label | New description |
|---|---|---|
| Dashboard | Overview | — |
| Session History | Signal Log | Every scored signal from the ML screener |
| Module Progress | Discipline Dashboard (module block) | Usage & completion across the suite |
| Account Settings | Trader Profile | Neural baseline & session preferences |
| Notifications | Signal Alerts | Non-repainting engine triggers & risk flags |
| Product Keys / Licenses/Downloads | License & Billing | Manage your Precision Suite access |
| Billing & Plan | License & Billing (current license) | Plan, invoices, license keys |
| Prop Firm Center | Prop Firm Command Center | Accounts, rules, drawdown, payouts |

## Sidebar (11 sections)

Overview · Intelligence Feed · Signal Log · Pre-Flight Status · Chart Analysis
History · Discipline Dashboard · Prop Firm Command Center · License & Billing ·
Sentinel Affiliate Program · Trader Profile · Security

Grouped under: **Market Intelligence Engine** (Intelligence Feed, Signal Log,
Pre-Flight Status, Chart Analysis History) · **Psychology Gate** (Discipline
Dashboard) · **Capital & Access** (Prop Firm Command Center, License & Billing,
Sentinel Affiliate Program) · **Account** (Trader Profile, Security).

## Header chrome

- User menu role label: **"Command Portal"** (not "Elite Trader").
- Theme toggle: **"Light" / "Dark"**.
- Bell accessible name: **"Signal alerts"**.
- Security badge: **"Security Status: Protected"** (links to Security section).
- Demo provenance: **"DEMO DATA"** badge (shown when `meta.isDemo`).
- Sign-out: **"Sign Out"**.

## Buttons

Authorize · Refresh · Export · Review · Re-open analysis · Cycle · Copy ·
Download · Save Changes · Manage Billing · Upgrade License · Run Pre-Market Scan
· Open Market Terminal · Open Chart AI · Open Command Center · Retry ·
Sign out all others · Revoke · Reveal PII

## Section copy

| Section | Title | Sub |
|---|---|---|
| Overview | Good morning, {name}. | Precision Suite · Elite license · Last check 06:42 EST |
| Intelligence Feed | Intelligence Feed | Live bias scores, key levels, and the catalyst calendar — the Market Intelligence Engine, at a glance. |
| Signal Log | Signal Log | Every scored signal from the ML screener — module, market, session P&L, and the primary trigger. |
| Pre-Flight Status | Pre-Flight Status | Neural baseline, the discipline gates, and authorization state — logged before every session. |
| Chart Analysis History | Chart Analysis History | Saved structural analyses — FVG and order block flags, timeframe snapshots, ready to re-open. |
| Discipline Dashboard | Discipline Dashboard | Streak milestones, breach warnings, post-session reviews, and the psychology score. |
| Prop Firm Command Center | Prop Firm Command Center | Accounts, rules, drawdown, payouts, and challenge progress — every funded and evaluation account in one place. |
| License & Billing | License & Billing | Manage your Precision Suite access — plan, invoices, license keys, and downloads. |
| Sentinel Affiliate Program | Sentinel Affiliate Program | Recurring commissions for educators and funded traders who teach ICT/USME methodology — your tier, referrals, and payouts. |
| Trader Profile | Trader Profile | Neural baseline and session preferences — plus your signal alert configuration. |
| Security | Security | Passkey & Face ID, two-factor auth, active sessions, and device fingerprint. |

## Table headers (Signal Log)

`<caption>`: "Signal log — Date, Module, Market, Session P&L, Score, Primary
Trigger, Status".

Columns: Date · Module · Market · Session P&L · Score · Primary Trigger ·
Status · (Actions, sr-only).

## States

**Empty**
- "No alerts in the last 7 days." → Run Pre-Market Scan
- "No signals logged yet." → Open Market Terminal
- "No pre-flight scan logged for today." → Run Pre-Market Scan
- "No saved analyses yet. Open a chart to generate one." → Open Chart AI
- "No prop firm accounts linked yet." → Open Command Center
- "No active licenses." / "No invoices yet." / "No downloads available." /
  "No special licenses." / "No member access." / "No active sessions reported."
  / "No admin actions recorded." / "No signal alerts."

**Error** — "Connection interrupted. {reason}. Retry or contact support."

**Loading** — skeleton shimmer only; **no "Loading…" text anywhere**.

## Legal (footer)

"DISCLAIMER: Trading involves substantial risk of loss and is not suitable for
every investor. Past performance does not guarantee future results. All content
on this site is for educational purposes only and does not constitute financial
or investment advice."

Footer bottom: "Calm. Precise. Deliberate."
