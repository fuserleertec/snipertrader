# Security — Command Portal

Given the domain's flagged reputation, the portal over-communicates security.
This doc records the posture that is **actually implemented** (client-side +
already-present infrastructure), and what remains to be done before production
auth.

## What the portal shows the user

### 1. Session integrity (Security section → "Session Integrity" panel)
Rendered from `data.fingerprint` (mock-store fallback; a real session/JWT would
supply these server-side):
- **Device** — e.g. `MacBook Pro 14" · macOS`
- **Fingerprint** — pseudo device ID, masked (`.masked` blur) until revealed
- **IP location** — masked until revealed
- **Last active** — timestamp
- **Trust** — "Recognized device" / "Unrecognized device"
- **2FA badge** — `2FA` enabled indicator (from `security.twoFactor`)

### 2. Active sessions + sign-out-all
- Per-session rows with a live dot (current = emerald), device, state, and a
  **Revoke** action for non-current sessions.
- **"Sign out all others"** — removes every non-current session row and logs an
  audit entry. (Demo: client-side only; wire to a real token-revocation endpoint
  before production.)

### 3. PII masking
- Phone: `+1 (***) ***-7834` (masked form only).
- Fingerprint ID and IP are blurred via `.masked` and require an explicit
  **Reveal PII** action; re-clicking masks again.
- License keys are blurred by default; **Copy** requires an explicit click.
- Every reveal/mask is written to the audit log.

### 4. Audit log ("who / what / when")
Admin actions are appended to an in-memory log (mirrored to `localStorage` key
`st_admin_audit`), seeded from `data.auditLog`, and rendered newest-first:
- Signed in / Signed out
- Exported signal log (with row count)
- Copied license key / Revealed PII / Masked PII
- Signed out all other sessions / Revoked session
- Saved trader profile / Cycled prop status / Download

### 5. Two-factor & passkey
- Security panel lists TOTP, SMS backup, and Passkey/Face ID methods (toggle
  state from `security.methods`).
- The login gate supports email/password → conditional 2FA code entry, plus
  Passkey / Face ID / Google SSO affordances (demo: any credential except
  password `wrong` authorizes; the 2FA step is illustrative).

## Infrastructure already in place (verified live)

- **HTTPS + HSTS** — live responses carry
  `strict-transport-security: max-age=63072000` (Vercel-managed). Confirmed via
  `curl -sIL https://snipertrader.ai/`.
- **CSP / secure cookies** — not yet set for this static site. Recommend adding
  a `vercel.json` `headers` block (see below) before treating the portal as a
  real authenticated surface.

## What is NOT yet done (do not claim otherwise)

- The login gate is a **demo gate** (`Authorization: Bearer demo-admin-token`
  against the existing `/api/admin` demo token). There is **no real
  session/JWT, no user database, no Stripe, no token revocation** in this repo.
- `CSP`, `Referrer-Policy`, `Permissions-Policy`, and `Secure`/`HttpOnly` cookie
  flags are **not** currently emitted.
- "Device fingerprint" and "IP location" are mock values, not real telemetry.

## Recommended `vercel.json` headers (for when auth goes real)

```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Strict-Transport-Security", "value": "max-age=63072000; includeSubDomains; preload" },
        { "key": "X-Content-Type-Options", "value": "nosniff" },
        { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
        { "key": "X-Frame-Options", "value": "DENY" },
        { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" }
      ]
    }
  ]
}
```

(Add a `Content-Security-Policy` tailored to the inline-free asset split once
inline styles in other pages are audited — a strict CSP today would break the
~50 inline-style pages.)

## Production auth checklist

1. Replace `ADMIN_DEMO_TOKEN` with real session/JWT + short-lived tokens.
2. Move `api/_lib/admin/store.js` from `seed.json` to a real datastore
   (Supabase/Firebase) — see `store.js` header comment.
3. Implement real token revocation for "Sign out all others".
4. Emit CSP + secure-cookie headers via `vercel.json`.
5. Keep PII masked server-side (never ship full PII to the client unless
   authorized).
