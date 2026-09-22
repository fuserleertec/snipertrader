#!/usr/bin/env python3
"""Inject results.json into terminal_template.html -> terminal.html and
   forecaster_template.html -> sniper_market_forecaster.html."""
import json
from datetime import datetime, timezone

TMPL = "/Users/snipertrader/snipertrader/teardown/terminal_template.html"
TMPL_FC = "/Users/snipertrader/snipertrader/teardown/forecaster_template.html"
OUT = "/Users/snipertrader/snipertrader/market_terminal.html"
OUT_FC = "/Users/snipertrader/snipertrader/sniper_market_forecaster.html"
OUT_LOCAL = "/Users/snipertrader/snipertrader/teardown/terminal.html"
RES = "/Users/snipertrader/snipertrader/teardown/results.json"
RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
SUM = "/Users/snipertrader/snipertrader/teardown/backtest_summary.json"
CAT = "/Users/snipertrader/snipertrader/teardown/catalysts.json"

with open(RES) as f:
    res = json.load(f)
with open(RAW) as f:
    raw = json.load(f)
with open(SUM) as f:
    summary = json.load(f)
with open(CAT) as f:
    res["catalysts"] = json.load(f)
res["trade_backtest"] = summary

# human-readable as-of from the latest regularMarketTime across symbols
ts = 0
for rec in raw.values():
    ts = max(ts, rec.get("meta", {}).get("regularMarketTime") or 0)
as_of = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z") if ts else "—"
res["as_of"] = as_of

payload = json.dumps(res, separators=(",", ":"))

with open(TMPL) as f:
    tpl = f.read()
html = tpl.replace("__DATA__", payload)
with open(OUT, "w") as f:
    f.write(html)
with open(OUT_LOCAL, "w") as f:
    f.write(html)
print(f"wrote {OUT}  ({len(html)} bytes, data {len(payload)} bytes, as_of={as_of})")
print(f"wrote {OUT_LOCAL}")

with open(TMPL_FC) as f:
    tpl_fc = f.read()
html_fc = tpl_fc.replace("__DATA__", payload)
with open(OUT_FC, "w") as f:
    f.write(html_fc)
print(f"wrote {OUT_FC}  ({len(html_fc)} bytes)")
