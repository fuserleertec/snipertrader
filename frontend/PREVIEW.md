# Preview the Conviction Terminal

Canonical deploy notes: [`DEPLOY.md`](./DEPLOY.md).

## Paper preview (P0 #2 closed pass)

https://snipertrader-dashboard-36y96ypn3-sniper-8ee72a26.vercel.app

Separate Vercel project · Root Directory = `frontend` ·
`NEXT_PUBLIC_USE_MOCKS=true` · [`frontend/vercel.json`](./vercel.json)
(`"framework": "nextjs"`).

## Confirmed facts

- sniperteam: the Git-connected Vercel project **`snipertrader`** has
  **Root Directory = `null`** (repo root). It builds marketing static HTML
  + `api/*` + `/api/recon/refresh` crons from root [`vercel.json`](../vercel.json).
- Frontend: the Next dashboard **must** use a **second** Vercel project with
  **Root Directory = `frontend`**. Config: [`frontend/vercel.json`](./vercel.json)
  (`"framework": "nextjs"`).
- `rootDirectory` is a Vercel **project setting**, not a `vercel.json` key.

## Do not

- Set the marketing project’s Root Directory to `frontend` (breaks
  `snipertrader.ai` + recon crons).
- Replace root `vercel.json` with a Next / `frontend/out` build (drops
  `functions` and `crons` if merged to `main`).
- Expect the marketing Git preview to serve this app. `/` is `index.html`.
  `/dashboard` 404s.

## Do

1. Local paper: `cd frontend && NEXT_PUBLIC_USE_MOCKS=true npm run dev`
2. FE: create/link a Vercel project, Root Directory = `frontend`, Framework =
   Next.js, env `NEXT_PUBLIC_USE_MOCKS=true`. Do not attach `snipertrader.ai`.
3. Open that project’s preview URL (SSO/Deployment Protection may apply).

## Local

```bash
cd frontend
npm install
NEXT_PUBLIC_USE_MOCKS=true npm run dev
# http://localhost:3000
```

Repo root: `npm run dev:dashboard`.
