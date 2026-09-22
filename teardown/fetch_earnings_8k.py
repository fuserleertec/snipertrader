#!/usr/bin/env python3
"""Fetch the ACTUAL earnings-release dates via 8-K Item 2.02 (key-less, SEC EDGAR).

The existing `earnings_dates` are 10-K / 10-Q / 20-F FILING dates, which trail the
earnings release by days-to-weeks. An 8-K with Item 2.02 ("Results of Operations and
Financial Condition") must be filed within 4 business days of the earnings release, so
its filing date is a far tighter point-in-time proxy for when the market actually got
the news. This script adds `earnings_8k_dates` alongside the filing dates — no other
fields are touched.
"""
import json
import time
import urllib.request

CAT = "/Users/snipertrader/snipertrader/teardown/catalysts.json"
UA = {"User-Agent": "snipertrader-research@example.com", "Accept": "application/json"}


def http_get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=25).read().decode())


def main():
    cat = json.load(open(CAT))
    for sym, rec in cat.items():
        cik = rec.get("cik")
        if not cik:
            continue
        try:
            j = http_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
            r = j["filings"]["recent"]
            forms, dates, items = r["form"], r["filingDate"], r.get("items", [])
            rel = []
            for i in range(len(forms)):
                it = items[i] if i < len(items) else ""
                if forms[i] == "8-K" and "2.02" in it:
                    rel.append(dates[i])
            rec["earnings_8k_dates"] = rel
            print(f"OK  {sym:6s} 8-K(2.02)={len(rel)}  filing={len(rec.get('earnings_dates', []))}  "
                  f"latest_8k={rel[0] if rel else '—'}")
        except Exception as e:
            print(f"ERR {sym}: {e}")
            rec["earnings_8k_dates"] = []
        time.sleep(0.25)

    json.dump(cat, open(CAT, "w"), indent=2, default=str)
    print("\nSaved catalysts.json with earnings_8k_dates")


if __name__ == "__main__":
    main()
