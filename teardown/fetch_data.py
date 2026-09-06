#!/usr/bin/env python3
"""Fetch real OHLCV for the SniperTrader scan universe from Yahoo Finance (key-less).

Daily bars, ~6 months, adjusted. Saves to raw_ohlcv.json.
Uses only stdlib (urllib) so no dependency install is needed.
"""
import json
import time
import urllib.request
import urllib.parse

SYMBOLS = {
    # equities
    "AAPL": "AAPL", "AMD": "AMD", "AMZN": "AMZN", "AVGO": "AVGO",
    "CRWD": "CRWD", "META": "META", "MSFT": "MSFT", "NVDA": "NVDA",
    "PLTR": "PLTR", "TSLA": "TSLA",
    # crypto (Yahoo uses USD pairs)
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD",
    "LINKUSDT": "LINK-USD", "AVAXUSDT": "AVAX-USD", "DOGEUSDT": "DOGE-USD",
    # futures
    "CL": "CL=F", "GC": "GC=F", "ES": "ES=F", "NQ": "NQ=F",
}

RANGE = "2y"
INTERVAL = "1d"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fetch(symbol: str) -> dict:
    q = urllib.parse.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?range={RANGE}&interval={INTERVAL}&includeAdjustedClose=true"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    out = {}
    for key, ysym in SYMBOLS.items():
        for attempt in range(3):
            try:
                body = fetch(ysym)
                res = body["chart"]["result"][0]
                ts = res.get("timestamp", [])
                quote = res["indicators"]["quote"][0]
                adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
                rows = []
                for i, t in enumerate(ts):
                    c = quote["close"][i]
                    if c is None:
                        continue
                    rows.append({
                        "t": t,
                        "o": round(quote["open"][i], 6) if quote["open"][i] is not None else None,
                        "h": round(quote["high"][i], 6) if quote["high"][i] is not None else None,
                        "l": round(quote["low"][i], 6) if quote["low"][i] is not None else None,
                        "c": round(c, 6),
                        "v": int(quote["volume"][i] or 0),
                        "adj": round(adj[i], 6) if i < len(adj) and adj[i] is not None else None,
                    })
                out[key] = {
                    "yahoo_symbol": ysym,
                    "meta": {
                        "currency": res.get("meta", {}).get("currency"),
                        "exchange": res.get("meta", {}).get("exchangeName"),
                        "fullExchangeName": res.get("meta", {}).get("fullExchangeName"),
                        "regularMarketPrice": res.get("meta", {}).get("regularMarketPrice"),
                        "regularMarketTime": res.get("meta", {}).get("regularMarketTime"),
                    },
                    "bars": rows,
                    "n_bars": len(rows),
                }
                print(f"OK  {key:10s} -> {ysym:10s}  {len(rows)} bars  last={rows[-1]['c'] if rows else None}")
                break
            except Exception as e:
                if attempt == 2:
                    print(f"ERR {key:10s} -> {ysym:10s}  {e}")
                    out[key] = {"yahoo_symbol": ysym, "error": str(e), "bars": [], "n_bars": 0}
                else:
                    time.sleep(1.5)

    with open("/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json", "w") as f:
        json.dump(out, f)
    print("\nSaved raw_ohlcv.json")


if __name__ == "__main__":
    main()
