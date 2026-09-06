#!/usr/bin/env python3
"""Fetch intraday 1h OHLCV for the edge hunt (key-less):
  crypto  → Binance public klines (1h, paginated ~2000 bars ≈ 83 days)
  equity  → Yahoo Finance chart API (1h, ~6 months)
Saves to raw_ohlcv_1h.json in the same shape as raw_ohlcv.json.
"""
import json
import time
import urllib.request
import urllib.parse

CRYPTO = {"BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT", "SOLUSDT": "SOLUSDT",
          "LINKUSDT": "LINKUSDT", "AVAXUSDT": "AVAXUSDT", "DOGEUSDT": "DOGEUSDT"}
EQUITY = {"AAPL": "AAPL", "AMD": "AMD", "AMZN": "AMZN", "AVGO": "AVGO",
          "CRWD": "CRWD", "META": "META", "MSFT": "MSFT", "NVDA": "NVDA",
          "PLTR": "PLTR", "TSLA": "TSLA"}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
           "Accept": "application/json"}


def http_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_binance_1h(sym, target=2000):
    bars = []
    end = None
    while len(bars) < target:
        u = f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=1h&limit=1000"
        if end:
            u += f"&endTime={end}"
        j = http_get(u)
        if not j:
            break
        # prepend (klines come ascending)
        batch = [{"t": k[0] // 1000, "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
                  "c": float(k[4]), "v": float(k[5])} for k in j]
        if not bars:
            bars = batch
        else:
            # avoid overlap: drop any bar with t >= current oldest
            oldest = bars[0]["t"]
            batch = [b for b in batch if b["t"] < oldest]
            bars = batch + bars
        end = bars[0]["t"] * 1000 - 1
        if len(batch) < 1000:
            break
        time.sleep(0.3)
    return bars


def fetch_yahoo_1h(sym):
    q = urllib.parse.quote(sym)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range=6mo&interval=1h&includeAdjustedClose=true"
    body = http_get(url)
    res = body["chart"]["result"][0]
    ts = res.get("timestamp", [])
    quote = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        c = quote["close"][i]
        if c is None:
            continue
        rows.append({"t": t, "o": round(quote["open"][i], 6) if quote["open"][i] is not None else None,
                     "h": round(quote["high"][i], 6) if quote["high"][i] is not None else None,
                     "l": round(quote["low"][i], 6) if quote["low"][i] is not None else None,
                     "c": round(c, 6), "v": int(quote["volume"][i] or 0)})
    return rows


def main():
    out = {}
    for key, ysym in CRYPTO.items():
        try:
            bars = fetch_binance_1h(ysym)
            out[key] = {"yahoo_symbol": ysym, "meta": {"currency": "USDT"}, "bars": bars, "n_bars": len(bars)}
            print(f"OK  {key:10s} binance-1h  {len(bars)} bars  last={bars[-1]['c'] if bars else None}")
        except Exception as e:
            print(f"ERR {key:10s} binance-1h  {e}")
            out[key] = {"yahoo_symbol": ysym, "error": str(e), "bars": [], "n_bars": 0}
    for key, ysym in EQUITY.items():
        try:
            bars = fetch_yahoo_1h(ysym)
            out[key] = {"yahoo_symbol": ysym, "meta": {"currency": "USD"}, "bars": bars, "n_bars": len(bars)}
            print(f"OK  {key:10s} yahoo-1h    {len(bars)} bars  last={bars[-1]['c'] if bars else None}")
        except Exception as e:
            print(f"ERR {key:10s} yahoo-1h    {e}")
            out[key] = {"yahoo_symbol": ysym, "error": str(e), "bars": [], "n_bars": 0}

    with open("/Users/snipertrader/snipertrader/teardown/raw_ohlcv_1h.json", "w") as f:
        json.dump(out, f)
    print("\nSaved raw_ohlcv_1h.json")


if __name__ == "__main__":
    main()
