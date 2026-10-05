# Meridian Equities

Stock and ETF trading desk for Meridian. Chart-centric layout: price and VWAP, a US scan, session tape, and headlines. Port **5174**.

```bash
cd meridian-dashboard/frontend
npm install
npm run dev
```

Open http://localhost:5174.

## Symbols

US equities and ETFs. The scan book is SPY, QQQ, IWM, DIA, SMH, XLF, XLE, TLT, GLD, IBIT, AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AMD, AVGO, and JPM. Any other cash ticker (for example `BRK-B`) can be typed into the symbol field. Futures notation (`ES1!`, `/ES`, `NQ=F`) is rejected.

Timeframes: 1m, 5m, 15m, 1h, 4h (hourly bars rolled into New York 4-hour buckets), 1D. **EXT** includes premarket and after-hours prints. VWAP resets each regular session (or the extended session when EXT is on). On the daily chart it is a window VWAP.

## Data

- `GET /api/stocks/klines` and `GET /api/news/catalyst` on `VITE_API_BASE` (default `http://127.0.0.1:8787`, `node api/_server.js`). Alpaca IEX replaces the chart during regular hours when that route returns bars.
- Otherwise the desk uses Yahoo Finance through the Vite `/market` proxy. That feed is delayed. There is no stock websocket; the desk polls.
