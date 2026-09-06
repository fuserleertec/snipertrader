#!/usr/bin/env python3
"""Inject results.json into terminal_template.html -> terminal.html."""
import json
from datetime import datetime, timezone

TMPL = "/Users/snipertrader/snipertrader/teardown/terminal_template.html"
OUT = "/Users/snipertrader/snipertrader/market_terminal.html"
OUT_LOCAL = "/Users/snipertrader/snipertrader/teardown/terminal.html"
RES = "/Users/snipertrader/snipertrader/teardown/results.json"
RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
SUM = "/Users/snipertrader/snipertrader/teardown/backtest_summary.json"

with open(RES) as f:
    res = json.load(f)
with open(RAW) as f:
    raw = json.load(f)
with open(SUM) as f:
    summary = json.load(f)
res["trade_backtest"] = summary

# human-readable as-of from the latest regularMarketTime across symbols
ts = 0
for rec in raw.values():
    ts = max(ts, rec.get("meta", {}).get("regularMarketTime") or 0)
as_of = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z") if ts else "—"
res["as_of"] = f"data as of {as_of}"

with open(TMPL) as f:
    tpl = f.read()

payload = json.dumps(res, separators=(",", ":"))
html = tpl.replace("__DATA__", payload)

with open(OUT, "w") as f:
    f.write(html)
with open(OUT_LOCAL, "w") as f:
    f.write(html)
print(f"wrote {OUT}  ({len(html)} bytes, data {len(payload)} bytes, as_of={as_of})")
print(f"wrote {OUT_LOCAL}")
