# Command Portal — Architecture & Admin Guide

Rebuild of `snipertrader.ai/admin.html` as the **Command Portal**: a native
extension of the marketing site, mapped to its product pillars, with honest
three-state data handling.

## File structure (new)

```
admin.html                     # shared shell + 10 sections + login gate
assets/css/tokens.css          # design tokens (extracted from index.html)
assets/css/admin.css           # portal components
assets/js/api.js               # real API client (SniperAPI)
assets/js/mock-api.js          # offline fallback + latency (MockAPI)
assets/js/admin.js             # app logic (nav, renderers, security, audit)
assets/data/mock-data.json     # demo dataset (seed + new sections)
assets/icons/*.svg             # 17 standalone SVG icons
docs/                          # this doc set
```

## Data flow (honest, layered)

1. **`SniperAPI.getAll()`** → `GET /api/admin/all` (real Vercel serverless
   function, backed by `api/_lib/admin/store.js` + `seed.json`, demo-labeled).
2. On success, sections the backend does **not** serve yet (`intelligence`,
   `chartAnalyses`, `auditLog`, `fingerprint`) are merged from
   `MockAPI.getExtended()` and flagged `State.simulated[k]=true` → rendered with
   a visible **SIMULATION** badge.
3. On failure (backend down / static-only host), the whole portal falls back to
   **`MockAPI.getAll()`** (`/assets/data/mock-data.json`, simulated latency).
4. `SniperAPI.propAccount()` → `GET /api/prop/account` (live Alpaca paper) is
   the **only live real-time source**; it degrades to an explicit
   "unavailable" message — never fabricated.

Every widget therefore has the required three states: **skeleton shimmer**
(`aria-busy`) → **data** / **empty** (with CTA) / **error** (with Retry,
logged to `console.error`). No "Loading…" text exists anywhere.

## API contract

| Endpoint | Method | Returns |
|---|---|---|
| `/api/admin/all` | GET | full payload (`meta` + `profile/overview/alerts/sessions/modules/licenses/billing/notifications/security/downloads/specialLicenses/memberAccess/propFirms/preflights`) |
| `/api/admin/<resource>` | GET | single section |
| `/api/admin/profile` | PATCH | update whitelisted profile fields |
| `/api/admin/propfirms` | PATCH | cycle prop account status |
| `/api/prop/account` | GET | live Alpaca paper account |

Auth: `Authorization: Bearer demo-admin-token` (demo gate — see security.md).
Zero new serverless functions were added; the Hobby 12-function cap is untouched.

## Section → pillar mapping

| Pillar (homepage) | Section | Data source |
|---|---|---|
| — | Overview | `overview` + `alerts` + live prop |
| Market Intelligence Engine | Intelligence Feed | mock (SIMULATION) + `alerts` |
| ML Screener | Signal Log | `sessions` (pagination, filter, CSV export) |
| Pre-Market Scan | Pre-Flight Status | `preflights` (empty → CTA) |
| AI Chart Analyzer | Chart Analysis History | mock (SIMULATION) |
| Psychology Gate | Discipline Dashboard | `overview` + `modules` + `alerts` |
| — | Prop Firm Command Center | `propFirms` + live prop |
| — | License & Billing | `licenses` + `billing` + downloads |
| — | Sentinel Affiliate Program | mock (SIMULATION) — tier, referrals, payouts |
| — | Trader Profile | `profile` + preferences |
| — | Security | `security` + `auditLog` + `fingerprint` |

## Key behaviors

- **Login gate** is a full-screen overlay (demo: any email; password `wrong`
  fails; conditional 2FA step). Passkey/Face ID/Google SSO are demo affordances.
- **Signal Log** paginates (6/page), filters by module, exports CSV
  (`signal-log.csv`), and logs the export to the audit trail.
- **Security** shows session integrity + "sign out all others" + revoke +
  PII masking (blur + explicit reveal) + audit log.
- **Bell** shows a real dropdown of `notifications` with a live badge count.
- **Ticker** is live (Binance WebSocket for crypto + stooq for indices), with
  the same static fallback as the homepage.
- **Theme** toggles `body.light` (dark/light), matching the homepage.

## Verification

- `node --check` on all three JS files: pass.
- `mock-data.json`: valid JSON, 19 top-level keys.
- Node `vm` harness #1 (mock fallback): **18/18** assertions.
- Node `vm` harness #2 (real API + merge, against real `seed.json`): **14/14**.
- Both harnesses run the actual shipped `assets/js/admin.js`.

**Not verified in this environment:** Lighthouse (no headless browser) and
rendered screenshots (the in-app preview detached mid-session). Scores are not
claimed; screenshots are pending a browser tab left open.

## Deploy (per AGENTS.md)

1. `git add admin.html assets/css assets/js assets/data assets/icons docs` —
   stage **named files only** (never `git add -A`).
2. `git commit -m "…"` (local only).
3. `git push origin main` — **only after explicit user confirmation** (a push
   is a live deploy to snipertrader.ai).

After push, verify with
`curl -sL https://snipertrader.ai/admin.html | grep -c 'data-action'` and
confirm `x-vercel-cache: MISS` / fresh `last-modified` before declaring live.
