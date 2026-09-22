#!/usr/bin/env python3
"""Directional catalyst backtest: does insider Form-4 DIRECTION (open-market
net-buy vs net-sell) predict forward returns, out-of-sample?

Event study, point-in-time: for each Form 4 filing in the ~2y window, classify
net-buy (P > S) vs net-sell (S > P) vs flat, then measure forward +5d/+20d return
vs the universe mean. Split pre/post 2025-06-01 (out-of-sample).

Why this exists: the earnings-drift work (edge_hunt_catalyst.py / validate_drift.py)
tested EARNINGS RECENCY but never tested insider DIRECTION as a forward-return
signal — only the aggregate "insiders are net sellers" fact. This closes that gap
for the insider component of the live directional catalyst.

Honest caveats (reported, not hidden):
  - Form 4 = officers/directors/10% owners only; many sales are routine 10b5-1.
  - Open-market purchases (P) are the conviction signal; awards (A) & dispositions
    (D) are EXCLUDED from direction (they are compensation, not a bet).
  - The NEWS-direction component of the live catalyst is NOT backtestable key-less
    (Google News RSS has no historical feed) — it is validated forward-only by the
    recon track-record loop, not here. This script covers the insider leg only.

Usage:
  python3 backtest_catalyst_direction.py --limit 2   # smoke test (2 symbols)
  python3 backtest_catalyst_direction.py             # full 30-equity run (cached)
"""
import json
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
CACHE = "/Users/snipertrader/snipertrader/teardown/insider_history.json"

EQUITY = ["AAPL", "AMD", "AMZN", "AVGO", "CRWD", "META", "MSFT", "NVDA", "PLTR", "TSLA",
          "GOOGL", "NFLX", "ADBE", "ORCL", "CRM", "QCOM", "INTC", "TSM", "MU", "COIN",
          "NOW", "SNOW", "UBER", "ABNB", "PYPL", "SHOP", "XYZ", "DDOG", "PANW", "NET"]

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 snipertrader-research@example.com",
      "Accept": "application/json, text/html;q=0.9"}

SPLIT = "2025-06-01"
HORIZONS = [5, 20]
BACKTEST_DAYS = 730  # ~2 years of Form 4 history


_rate_lock = threading.Lock()
_rate_next = [0.0]


def throttle():
    with _rate_lock:
        now = time.time()
        wait = max(0.0, _rate_next[0] - now)
        _rate_next[0] = max(now, _rate_next[0]) + 0.13  # ~7.7 req/s, under SEC's 10/s
    if wait > 0:
        time.sleep(wait)


def http_get(url, as_json=True, retries=4):
    for a in range(retries):
        throttle()
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body) if as_json else body
        except Exception as e:
            if a == retries - 1:
                raise
            time.sleep(1.5 * (a + 1))


def parse_form4(cik_int, acc_no, primary_doc):
    acc = acc_no.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{primary_doc}"
    html = http_get(url, as_json=False) or ""
    codes = re.findall(r'class="SmallFormData">([A-Z])<', html)
    return {"P": codes.count("P"), "S": codes.count("S"),
            "A": codes.count("A"), "D": codes.count("D")}


def fetch_insider_history(sym, cik, since_iso):
    """Full Form 4 history (date + P/S/A/D) since `since_iso`, cached."""
    cik_pad = str(cik).zfill(10)
    f = http_get(f"https://data.sec.gov/submissions/CIK{cik_pad}.json")["filings"]["recent"]
    forms, dates, accs, docs = f["form"], f["filingDate"], f["accessionNumber"], f["primaryDocument"]
    cik_int = int(cik)
    f4s = []
    for i in range(len(forms)):
        if forms[i] == "4" and dates[i] >= since_iso:
            f4s.append((dates[i], accs[i], docs[i]))

    rows = [None] * len(f4s)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(parse_form4, cik_int, a, d): idx for idx, (_, a, d) in enumerate(f4s)}
        for fut in as_completed(futs):
            idx = futs[fut]
            dt = f4s[idx][0]
            try:
                rows[idx] = {"date": dt, **fut.result()}
            except Exception:
                rows[idx] = {"date": dt, "error": True}
    return [r for r in rows if r is not None]


def load_cache():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}


def main():
    args = sys.argv[1:]
    limit = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    refetch = "--refetch" in args
    nofetch = "--no-fetch" in args

    raw = json.load(open(RAW))
    cache = load_cache()

    since = (datetime.now(timezone.utc).date().toordinal() - BACKTEST_DAYS)
    since_iso = datetime.fromordinal(since).isoformat()

    # fetch (cached) Form 4 history for each equity
    cik_map = None
    syms = EQUITY if limit is None else EQUITY[:limit]
    if not nofetch:
        for sym in syms:
            if sym in cache and not refetch:
                print(f"cache {sym}: {len(cache[sym]['form4'])} Form 4s")
                continue
            if cik_map is None:
                cik_map = {rec["ticker"]: rec["cik_str"] for rec in
                           http_get("https://www.sec.gov/files/company_tickers.json").values()}
            cik = cik_map.get(sym)
            if not cik:
                print(f"ERR {sym}: no CIK")
                continue
            try:
                rows = fetch_insider_history(sym, cik, since_iso)
                cache[sym] = {"form4": rows, "fetched": datetime.now(timezone.utc).isoformat()}
                print(f"OK {sym}: {len(rows)} Form 4s since {since_iso}")
            except Exception as e:
                print(f"ERR {sym}: {e}")
            json.dump(cache, open(CACHE, "w"), indent=2)
        json.dump(cache, open(CACHE, "w"), indent=2)
    else:
        syms = [s for s in syms if s in cache]
        print(f"--no-fetch: backtesting on {len(syms)} cached symbols")

    # ---- event-study backtest ----
    # universe baseline: mean forward return across all equity bars at each horizon
    def universe_mean_fwd(h):
        rs = []
        for sym, rec in raw.items():
            bars = rec["bars"]
            for i in range(len(bars) - h):
                if bars[i]["c"] and bars[i + h]["c"]:
                    rs.append(bars[i + h]["c"] / bars[i]["c"] - 1)
        return sum(rs) / len(rs) if rs else 0.0

    base5 = universe_mean_fwd(5)
    base20 = universe_mean_fwd(20)
    print(f"\nuniverse baseline fwd: +5d={base5*100:+.2f}%  +20d={base20*100:+.2f}%  "
          f"(all equities, all bars)")

    # bar index lookup per symbol: date-epoch -> first bar index >= that epoch
    def build_lookup(bars):
        return [b["t"] for b in bars]

    def fwd_return(bars, i, h):
        if i + h >= len(bars) or not bars[i]["c"] or not bars[i + h]["c"]:
            return None
        return bars[i + h]["c"] / bars[i]["c"] - 1

    split_epoch = int(time.mktime(time.strptime(SPLIT, "%Y-%m-%d")))

    events = []  # (direction, excess5, excess20, epoch)
    for sym in syms:
        rec = cache.get(sym, {}).get("form4", [])
        bars = raw.get(sym, {}).get("bars", [])
        if not bars:
            continue
        ts = build_lookup(bars)
        for f4 in rec:
            if f4.get("error") or f4.get("date") is None:
                continue
            p, s = f4.get("P", 0), f4.get("S", 0)
            if p == 0 and s == 0:
                continue
            direction = "buy" if p > s else "sell"
            try:
                epoch = int(time.mktime(time.strptime(f4["date"], "%Y-%m-%d")))
            except Exception:
                continue
            # first bar at/after the filing date
            i = None
            for idx, t in enumerate(ts):
                if t >= epoch:
                    i = idx
                    break
            if i is None:
                continue
            e5 = fwd_return(bars, i, 5)
            e20 = fwd_return(bars, i, 20)
            if e5 is None and e20 is None:
                continue
            events.append((direction, e5, e20, epoch))

    def summarize(evs):
        out = {}
        for d in ("buy", "sell"):
            es = [e for e in evs if e[0] == d]
            if not es:
                out[d] = {"n": 0}
                continue
            n = len(es)
            f5 = [e[1] for e in es if e[1] is not None]
            f20 = [e[2] for e in es if e[2] is not None]
            out[d] = {
                "n": n,
                "n5": len(f5), "mean5": round(sum(f5) / len(f5) * 100, 2) if f5 else None,
                "excess5": round((sum(f5) / len(f5) - base5) * 100, 2) if f5 else None,
                "hit5": round(sum(1 for x in f5 if x > 0) / len(f5) * 100, 1) if f5 else None,
                "n20": len(f20), "mean20": round(sum(f20) / len(f20) * 100, 2) if f20 else None,
                "excess20": round((sum(f20) / len(f20) - base20) * 100, 2) if f20 else None,
                "hit20": round(sum(1 for x in f20 if x > 0) / len(f20) * 100, 1) if f20 else None,
            }
        return out

    all_ev = summarize(events)
    early = summarize([e for e in events if e[3] < split_epoch])
    late = summarize([e for e in events if e[3] >= split_epoch])

    def pr(label, agg):
        print(f"\n--- {label} ---")
        for d in ("buy", "sell"):
            m = agg[d]
            if not m.get("n"):
                print(f"  {d:4s}: n=0")
                continue
            print(f"  {d:4s}: n={m['n']:4d}  "
                  f"+5d {m['mean5'] if m['mean5'] is not None else '—':>7}%  "
                  f"(excess {m['excess5'] if m['excess5'] is not None else '—':>+7}% · "
                  f"hit {m['hit5'] if m['hit5'] is not None else '—':>5}%)   "
                  f"+20d {m['mean20'] if m['mean20'] is not None else '—':>7}%  "
                  f"(excess {m['excess20'] if m['excess20'] is not None else '—':>+7}% · "
                  f"hit {m['hit20'] if m['hit20'] is not None else '—':>5}%)")

    print("\n" + "=" * 100)
    print("INSIDER DIRECTION → FORWARD RETURN (event study, point-in-time)")
    print("=" * 100)
    pr("ALL (full window)", all_ev)
    pr(f"TRAIN (before {SPLIT})", early)
    pr(f"TEST  (after {SPLIT}) — out-of-sample", late)
    print("\n(note: 'buy' = net open-market purchases P > S in a filing; "
          "'sell' = net sales. A = awards, D = dispositions excluded from direction.)")

    out = {"generatedAt": datetime.now(timezone.utc).isoformat(),
           "universeBaseline": {"fwd5": round(base5 * 100, 2), "fwd20": round(base20 * 100, 2)},
           "split": SPLIT, "all": all_ev, "train": early, "test": late}
    json.dump(out, open("/Users/snipertrader/snipertrader/teardown/backtest_catalyst_direction_result.json", "w"), indent=2)
    print("\nwrote backtest_catalyst_direction_result.json")


if __name__ == "__main__":
    main()
