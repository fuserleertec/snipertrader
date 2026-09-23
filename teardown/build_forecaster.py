#!/usr/bin/env python3
"""Refresh the embedded data in sniper_market_forecaster.html IN PLACE.

The forecaster is hand-edited directly (search box, narration, self-rendered
candlestick chart) — NOT regenerated from forecaster_template.html, which is
stale. This script patches ONLY the <script id="data"> block in the live file
and preserves every other byte. Run this instead of build_html.py when the
forecaster's snapshot data (results / catalysts / backtest) needs a refresh.
"""
import json
import re
from datetime import datetime, timezone

OUT_FC = "/Users/snipertrader/snipertrader/sniper_market_forecaster.html"
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

ts = 0
for rec in raw.values():
    ts = max(ts, rec.get("meta", {}).get("regularMarketTime") or 0)
as_of = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z") if ts else "—"
res["as_of"] = as_of

payload = json.dumps(res, separators=(",", ":"))

with open(OUT_FC) as f:
    html = f.read()

new_block = f'<script id="data" type="application/json">{payload}</script>'
html_new, n = re.subn(
    r'<script id="data" type="application/json">.*?</script>',
    lambda m: new_block,
    html,
    count=1,
    flags=re.S,
)

if n != 1:
    raise SystemExit('ERROR: could not find exactly one <script id="data"> block to patch — aborting (forecaster NOT modified).')

with open(OUT_FC, "w") as f:
    f.write(html_new)
print(f"patched {OUT_FC}  (data {len(payload)} bytes, as_of={as_of})")
