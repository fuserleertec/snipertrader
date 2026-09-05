# Deploy the Conviction Terminal

Two Vercel projects. Do not point both at `snipertrader.ai`.

`rootDirectory` is a **Vercel project setting** (Dashboard → Project →
Settings → General). It is **not** a `vercel.json` key. Changing it on the
wrong project is a production flip.

## Project A — marketing (already live)

Confirmed by sniperteam: Git project **`snipertrader`**
(`prj_U2PT9S5OZuNgmj0s9EnnroUpThlx`, team `sniper-8ee72a26`) has

**Root Directory = `null` (repo root).**

| Setting | Value |
|---|---|
| Root Directory | *empty / `.`* — **leave this** |
| Framework | Other / `null` |
| Config | repo-root [`vercel.json`](../vercel.json) |
| Serves | static `*.html` + `api/*` serverless |
| Crons | `/api/recon/refresh` at `0 13` and `0 22` UTC |
| Domain | `snipertrader.ai` |

Do **not** set this project’s Root Directory to `frontend`. That would stop
marketing HTML and the recon crons from deploying.

PR previews on **this** Git connection are marketing HTML. `/` is
`index.html`. `/dashboard` 404s (that file does not exist). That is expected.

## Project B — Conviction Terminal (FE must create / link)

**Live paper preview (P0 #2 closed pass):**
https://snipertrader-dashboard-36y96ypn3-sniper-8ee72a26.vercel.app

Separate Vercel project. Root Directory = `frontend`.
`NEXT_PUBLIC_USE_MOCKS=true`. Confirmed Next HTML (`Conviction Terminal`),
not marketing `index.html`.

Frontend confirmed: the Next app **must** use

**Root Directory = `frontend`.**

[`frontend/vercel.json`](./vercel.json) sets `"framework": "nextjs"` so a
deploy whose cwd / Root Directory is `frontend/` does not inherit repo-root
`"framework": null`. Create a **second** Vercel project (do not edit Project A):

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework preset | Next.js |
| Config | [`frontend/vercel.json`](./vercel.json) (`"framework": "nextjs"`) |
| Install | `npm install` |
| Build | `NEXT_PUBLIC_USE_MOCKS=true npm run build` |
| Env (preview) | `NEXT_PUBLIC_USE_MOCKS=true` |
| Production branch / domain | do **not** attach `snipertrader.ai` |

When Root Directory is `frontend`, Vercel reads `frontend/vercel.json` and
`frontend/package.json`. Root `vercel.json` (marketing + crons) is ignored
for this project — that is the point.

Paper / staging stays on mocks. Live Quant (`:8001`) / Data Eng (`:8000`)
is env-only (`NEXT_PUBLIC_USE_MOCKS=false` plus the `NEXT_PUBLIC_*_BASE`
vars). No `live_trading`. No production flip.

## Local (no Vercel)

```bash
cd frontend
npm install
NEXT_PUBLIC_USE_MOCKS=true npm run dev
# http://localhost:3000
```

Repo root: `npm run dev:dashboard`.

## Why a second project (not a root `vercel.json` hijack)

An earlier experiment rewrote root `vercel.json` to static-export
`frontend/out` on this branch. That **drops** `functions` + `crons` and
would break marketing if merged to `main`. Do not do that.

| Wrong | Right |
|---|---|
| Set Project A Root Directory to `frontend` | Leave Project A at repo root |
| Replace root `vercel.json` with a Next build | Keep root `vercel.json` as marketing + crons |
| Expect `/dashboard` on the marketing preview | Use Project B, or `npm run dev` locally |

## SSO

Project B preview URLs may be behind Vercel Deployment Protection.
Anonymous `curl` will 302 to SSO. Team members open the URL while logged
into Vercel.
