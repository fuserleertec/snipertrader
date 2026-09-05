# Preview the Conviction Terminal

## Why the old PR preview was marketing HTML

The Git-connected Vercel project `snipertrader` (`prj_U2PT9S5OZuNgmj0s9EnnroUpThlx`)
has **Root Directory = null** (repo root) and root `vercel.json` used
`"framework": null` plus static `*.html`. Vercel therefore publishes
`index.html` / `stock_picks.html`. `/dashboard` 404s because that file
does not exist on the marketing site.

`rootDirectory` is a **Vercel project setting**, not a supported
`vercel.json` key (see Vercel project-configuration). Changing the live
project’s Root Directory to `frontend` would break production marketing
on `main`.

## What this PR does (option A — preview/staging)

On **this branch only**, root `vercel.json` builds the Next app as a
paper static export and publishes `frontend/out`:

```
install: npm install --prefix frontend
build:   SNIPER_STATIC_EXPORT=1 NEXT_PUBLIC_USE_MOCKS=true npm run build --prefix frontend
output:  frontend/out
```

- `/` is the Conviction Terminal (not `index.html`)
- `/dashboard` redirects to `/`
- `NEXT_PUBLIC_USE_MOCKS=true` (also `frontend/.env.production`)
- No `live_trading`, no Quant/DE keys required
- Production `main` is unchanged — it still uses marketing `vercel.json`

Marketing recipe is saved at [`/vercel.marketing.json`](../vercel.marketing.json).
Do **not** merge this branch’s root `vercel.json` to `main` without restoring
that file.

## Local

```bash
cd frontend
npm install
NEXT_PUBLIC_USE_MOCKS=true npm run dev
# http://localhost:3000
```

Repo root: `npm run dev:dashboard`.

## Full Next.js runtime (second Vercel project)

For SSR + `/v1` rewrites (not required for paper mocks), sniperteam
creates a **separate** Vercel project (do not edit the marketing project):

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework preset | Next.js |
| Install | `npm install` |
| Build | `NEXT_PUBLIC_USE_MOCKS=true npm run build` |
| Env | `NEXT_PUBLIC_USE_MOCKS=true` |
| Production branch | do **not** point `snipertrader.ai` here |

`frontend/vercel.json` is the config for that project.

## Blockers if Git preview is still marketing

1. Vercel project **Root Directory** is still `.` and the deploy ignored this
   branch’s `outputDirectory` — check the deployment build logs.
2. Deployment Protection / SSO on `*.vercel.app` — use the team preview
   login, not an anonymous curl.
3. `main` deploys will stay marketing until someone copies this
   `vercel.json` there (do not — that is a production flip).
