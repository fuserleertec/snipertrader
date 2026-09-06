# Preview the Conviction Terminal

Canonical deploy notes: [`DEPLOY.md`](./DEPLOY.md).

**Terminal is at `/` on the dashboard project.** Do not score the marketing
Git Ready preview (`index.html`) or the stale P0 #2 URL below.

## Redeploy this PR (sniperteam)

1. Open https://github.com/fuserleertec/snipertrader/pull/14
2. Branch: `cursor/frontend-multi-asset-desk-f4b0`
3. Redeploy Vercel project **snipertrader-dashboard**
   - Root Directory = `frontend`
   - Framework = Next.js
   - Env: `NEXT_PUBLIC_USE_MOCKS=true` on the preview host (no :8000/:8001)
4. Confirm the page is **Conviction Terminal** at `/`, not marketing HTML.

Paper QA against local backends:

```bash
cd frontend
NEXT_PUBLIC_USE_MOCKS=false \
  NEXT_PUBLIC_HTTP_BASE=http://localhost:8000 \
  NEXT_PUBLIC_WS_BASE=ws://localhost:8000 \
  NEXT_PUBLIC_QUANT_API_BASE=http://localhost:8001 \
  npm run dev
```

DE `:8000` (`GET /v1/universe/top`) · Quant `:8001` (`/picks/*`, `/signals`).
`live_trading` stays false.

## Stale URL — do not QA this PR against it

https://snipertrader-dashboard-36y96ypn3-sniper-8ee72a26.vercel.app

That host is the **P0 #2 closed pass**. It still shows MOCK FALLBACK + a
4-symbol lock. This PR’s lists come from `GET /v1/universe/top` + Quant
ensemble/categorized/history.

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

## Local

```bash
cd frontend
npm install
NEXT_PUBLIC_USE_MOCKS=true npm run dev
# http://localhost:3000
```

Repo root: `npm run dev:dashboard`.
