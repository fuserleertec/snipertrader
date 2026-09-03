# Cognitive Pipeline — Heartbeat Dashboard

Production-ready React + WebSocket reimplementation of the `cognitive-pipeline-dashboard.html`
mockup. A Node `ws` server emits a full-state "heartbeat" payload every 3 seconds
(simulation mode); the React frontend subscribes, renders the 8-stage pipeline and the
Quantum Ensemble Picks table, and re-animates live on every frame.

> **All data is synthetic demo data** — clearly labeled `SYNTHETIC DATA` in the UI. This is
> an interface simulation, not live market data or investment advice.

## Structure

```
backend/
  server.js          # WebSocket heartbeat server (ws) — full-state payload every 3s
  extract-seed.mjs   # regenerates data/seed.json from the canonical HTML mockup
  data/seed.json     # 8 stages + 35 picks (7 categories), extracted verbatim
frontend/
  src/
    types/index.ts          # HeartbeatPayload / Pick / PipelineStage types
    stores/appStore.ts      # Zustand store (pipelineStages, picks, mode/cat/sub, expanded)
    hooks/useHeartbeat.ts   # WS client hook (reconnect w/ 2s backoff)
    components/
      CognitivePipeline.tsx # 8-stage horizontal flow + animated arrows
      PicksTable.tsx        # mode toggle, category/sub tabs, conviction bars, engine chips
      EngineBreakdown.tsx   # expandable per-engine vote cards
    data/seed.json          # initial-state fallback (renders before first heartbeat)
  package.json              # React 18 + Vite + TypeScript + Tailwind + Zustand
```

## Run it

Backend (WebSocket heartbeat on **:8787**):

```bash
cd backend
npm install
npm run extract          # regenerate data/seed.json from the HTML mockup (already committed)
npm start                # ws://0.0.0.0:8787  (PORT / HEARTBEAT_MS overridable)
```

Frontend:

```bash
cd frontend
npm install
npm run dev              # Vite dev server on :5173
# or production: npm run build && npm run preview   (:4173)
```

The frontend connects to `ws://<hostname>:8787` by default; override with
`VITE_WS_URL=ws://host:port npm run dev` (or set it at build time).

## Ports

`:8080` and `:8081` are occupied by the host's own `node src/server.js`, so the heartbeat
server defaults to **8787**. Override with `PORT` (backend) and `VITE_WS_URL` (frontend).

## Simulation behaviour

Each 3s frame re-sends the full stage list and picks, with a gentle bounded random-walk on
`conviction` (±2) so the bars visibly "pulse". Prices, signals, reasons, and engine stances
are anchored to the seed and do not change.
