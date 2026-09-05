# Preview the Conviction Terminal (not the marketing site)

The GitHub/Vercel project attached to **snipertrader.ai** deploys the **static
marketing site** from the repo root (`vercel.json` + `*.html`). That preview
will show the old landing page. `/` is **not** the Next.js dashboard.

## Local (paper window — this is the proof path)

```bash
cd frontend
npm install
NEXT_PUBLIC_USE_MOCKS=true npm run dev
# http://localhost:3000
```

From repo root: `npm run dev:dashboard`.

## Live Quant / Data Eng (still paper — no production flip)

```bash
cd frontend
NEXT_PUBLIC_USE_MOCKS=false \
NEXT_PUBLIC_WS_BASE=ws://localhost:8000 \
NEXT_PUBLIC_HTTP_BASE=http://localhost:8000 \
NEXT_PUBLIC_QUANT_API_BASE=http://localhost:8001 \
NEXT_PUBLIC_QUANT_WS_BASE=ws://localhost:8001 \
npm run dev
```

DE Phase 2 streams (PR #5) when that API is up:

- `WS /v1/ws/avwap?symbol=`
- `WS /v1/ws/volume-profile?symbol=`
- `WS /v1/ws/kill-zone?symbol=`

Mocks stay the default. Missing live frames fall back to weekly `vwap_values`
(AVWAP) and in-browser kill-zone / volume-profile seeds.

## Optional second Vercel project (dashboard only)

Create a **separate** Vercel project (do not change the marketing project's
Root Directory):

1. Root Directory = `frontend`
2. Framework = Next.js (see `frontend/vercel.json`)
3. Env: `NEXT_PUBLIC_USE_MOCKS=true` for paper

```bash
cd frontend && npx vercel
```
