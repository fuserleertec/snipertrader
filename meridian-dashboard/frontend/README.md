# Meridian Equities

Stock and ETF desk on the futures dashboard layout and color tokens. Vite port **5174**.

```bash
cd meridian-dashboard/frontend
npm install
npm run dev
```

Open http://localhost:5174.

The API base is `VITE_API_URL`, default `http://127.0.0.1:8010` (`uvicorn app.main:app --host 127.0.0.1 --port 8010`).

## Symbols

The scanner uses `GET /api/symbols` (SPY, QQQ, IWM, NVDA, TSLA, AAPL on the stock provider). Press Enter in the symbol field for any other cash ticker. Futures notation (`ES1!`, `/ES`, `NQ=F`) is rejected.

Timeframes match the futures desk: 5m, 15m, 1h. Grades: WATCH, PRIME, ELITE, SINGULAR.

## Data

- `GET /api/state?symbol=&timeframe=&min_grade=` — engine document (regime, lattice, gates, CVD, OFI, liquidity, VWAP, signal, path, series).
- `GET /api/meta`, `GET /api/health`, `GET /api/quote` (Alpaca IEX). With no Alpaca keys the quote route errors, so the desk skips it and uses the engine close. The positions badge stays `SIMULATED · no key`.
- `GET /api/broker`, `POST /api/broker/deploy`, `POST /api/broker/disconnect`, `GET /api/broker/positions`.
- `WS /ws` — state push for the symbol last read by `/api/state`.
- Headlines come from Yahoo Finance. The stock API has no news route. If `:8010` is down, the chart also falls back to Yahoo and the engine panels stay empty.
- This UI does not call `POST /api/broker/order`. Start Trading is a local arm flag.

The clock is America/New_York cash hours: premarket 04:00, RTH 09:30–16:00, after hours until 20:00. Signals arm only during RTH. Holidays are not skipped.

Light is the turquoise field (`data-theme=blue`). Night is the blue-gray field. The choice is stored in `meridian-equities-theme`.
