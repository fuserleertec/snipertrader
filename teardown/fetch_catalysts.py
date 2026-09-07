#!/usr/bin/env python3
"""Fetch SEC EDGAR catalysts (key-less) for the equity universe:
  - earnings dates  = 10-K / 10-Q filing dates (proxy for earnings release)
  - insider (Form 4) = parse (A) buys / (D) sells from the most recent Form 4s
Pipeline per snipertrader-market-recon skill (verified). Saves catalysts.json.
"""
import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

EQUITY = ["AAPL", "AMD", "AMZN", "AVGO", "CRWD", "META", "MSFT", "NVDA", "PLTR", "TSLA",
          "GOOGL", "NFLX", "ADBE", "ORCL", "CRM", "QCOM", "INTC", "TSM", "MU", "COIN",
          "NOW", "SNOW", "UBER", "ABNB", "PYPL", "SHOP", "XYZ", "DDOG", "PANW", "NET"]

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 snipertrader-research@example.com",
      "Accept": "application/json, text/html;q=0.9"}


def http_get(url, as_json=True, retries=3):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body) if as_json else body
        except Exception as e:
            if a == retries - 1:
                raise
            time.sleep(1.5 * (a + 1))


def ticker_to_cik():
    j = http_get("https://www.sec.gov/files/company_tickers.json")
    out = {}
    for rec in j.values():
        out[rec["ticker"]] = rec["cik_str"]
    return out


def get_filings(cik):
    cik_pad = str(cik).zfill(10)
    j = http_get(f"https://data.sec.gov/submissions/CIK{cik_pad}.json")
    return j["filings"]["recent"]


def parse_form4_direction(cik_int, acc_no, primary_doc):
    acc = acc_no.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{primary_doc}"
    html = http_get(url, as_json=False) or ""
    # transaction codes live in <span class="SmallFormData">X</span> (single letter)
    codes = re.findall(r'class="SmallFormData">([A-Z])<', html)
    p = codes.count("P")   # open-market Purchase  → conviction BUY
    s = codes.count("S")   # open-market Sale      → SELL
    a = codes.count("A")   # Award / grant         → compensation (not conviction)
    d = codes.count("D")   # Disposition           → return to issuer
    return {"P": p, "S": s, "A": a, "D": d}


def insider_score(buys, sells):
    if buys == 0:
        return 0.0
    if buys >= 3:
        return 1.0
    if buys == 1:
        return 0.7 if sells == 0 else 0.6
    return 0.8 if sells <= 1 else 0.7  # buys == 2


def main():
    cik_map = ticker_to_cik()
    out = {}
    for sym in EQUITY:
        rec = {"symbol": sym, "cik": None, "earnings_dates": [], "insider": {"buys": 0, "sells": 0, "score": 0.0, "recent": []}}
        try:
            cik = cik_map.get(sym)
            if not cik:
                print(f"ERR {sym}: no CIK")
                out[sym] = rec
                continue
            rec["cik"] = cik
            cik_int = int(cik)
            f = get_filings(cik)
            forms = f["form"]
            dates = f["filingDate"]
            accs = f["accessionNumber"]
            docs = f["primaryDocument"]

            # earnings = 10-K / 10-Q (US) or 20-F (foreign issuers, e.g. TSM ADR).
            # NOTE: 6-K is NOT used — it's a catch-all for foreign current reports, too
            # noisy to proxy earnings (TSM files ~1/day). Foreign issuers get annual-only.
            for i in range(len(forms)):
                if forms[i] in ("10-K", "10-Q", "20-F"):
                    rec["earnings_dates"].append(dates[i])

            # recent Form 4s (last 30 days), parse direction
            import datetime as _dt
            cutoff = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
            f4 = [(dates[i], accs[i], docs[i]) for i in range(len(forms))
                  if forms[i] == "4" and dates[i] >= cutoff]
            tot_p = tot_s = 0
            tot_a = tot_d = 0
            for dt, acc, doc in f4[:10]:
                try:
                    cd = parse_form4_direction(cik_int, acc, doc)
                    tot_p += cd["P"]; tot_s += cd["S"]; tot_a += cd["A"]; tot_d += cd["D"]
                    rec["insider"]["recent"].append({"date": dt, **cd})
                except Exception as e:
                    rec["insider"]["recent"].append({"date": dt, "error": str(e)[:80]})
                time.sleep(0.25)
            rec["insider"]["window_days"] = 30
            rec["insider"]["n_form4"] = len(f4)
            rec["insider"]["buys"] = tot_p        # open-market purchases (conviction)
            rec["insider"]["sells"] = tot_s       # open-market sales
            rec["insider"]["awards"] = tot_a      # compensation grants
            rec["insider"]["dispositions"] = tot_d
            rec["insider"]["score"] = insider_score(tot_p, tot_s)
            print(f"OK  {sym:6s} cik={cik} earnings={len(rec['earnings_dates'])} "
                  f"last_earnings={rec['earnings_dates'][0] if rec['earnings_dates'] else '—'} "
                  f"P={tot_p} S={tot_s} A={tot_a} D={tot_d} score={rec['insider']['score']}")
        except Exception as e:
            print(f"ERR {sym}: {e}")
        out[sym] = rec
        time.sleep(0.3)

    with open("/Users/snipertrader/snipertrader/teardown/catalysts.json", "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print("\nSaved catalysts.json")


if __name__ == "__main__":
    main()
