#!/usr/bin/env python3
"""Out-of-sample earnings-drift validation.

Compares the post-earnings drift edge measured from two date anchors:
  1. `earnings_dates`    = 10-K / 10-Q / 20-F FILING dates (current baseline — LAGGED)
  2. `earnings_8k_dates` = 8-K Item 2.02 dates (true release, filed within 4 days)

And checks temporal stability (train vs test split) so the "edge" is not an
in-sample artifact. Honest output — no prettying.
"""
import json
import time as _t
from backtest_trades import sim_trade

RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
FEAT = "/Users/snipertrader/snipertrader/teardown/features.json"
CAT = "/Users/snipertrader/snipertrader/teardown/catalysts.json"

raw = json.load(open(RAW))
feats = json.load(open(FEAT))
cat = json.load(open(CAT))

SPLIT = "2025-06-01"  # temporal out-of-sample cutoff
SPLIT_EPOCH = int(_t.mktime(_t.strptime(SPLIT, "%Y-%m-%d")))


def epochs(sym, key):
    out = []
    for d in cat.get(sym, {}).get(key, []):
        try:
            out.append(int(_t.mktime(_t.strptime(d, "%Y-%m-%d"))))
        except Exception:
            pass
    return sorted(out)


def days_since(sym, bars, key):
    eps = epochs(sym, key)
    out = {}
    for i, b in enumerate(bars):
        prev = [e for e in eps if e <= b["t"]]
        out[i] = (b["t"] - prev[-1]) / 86400.0 if prev else None
    return out


def pf(rs):
    w = sum(r for r in rs if r > 0)
    l = -sum(r for r in rs if r <= 0)
    return round(w / l, 3) if l > 0 else None


def drift(key, max_days, split=None):
    """Collect drift trades. split=None → all; 'early' → bar<cutoff; 'late' → bar>=cutoff."""
    rs = []
    for sym, snap in feats.items():
        bars = raw[sym]["bars"]
        dsm = days_since(sym, bars, key)
        for s in snap:
            cons = s["consensus"]
            d = "LONG" if cons >= 0.70 else ("SHORT" if cons <= 0.30 else None)
            if d is None:
                continue
            ds = dsm.get(s["i"])
            if ds is None or (max_days is not None and ds > max_days):
                continue
            t = bars[s["i"]]["t"]
            if split == "early" and t >= SPLIT_EPOCH:
                continue
            if split == "late" and t < SPLIT_EPOCH:
                continue
            r = sim_trade(bars, s, d, 20, "fixed2")
            if r is not None:
                rs.append(r - 0.05)
    n = len(rs)
    if n == 0:
        return {"n": 0, "pf": None, "win": None}
    wins = [r for r in rs if r > 0]
    return {"n": n, "pf": pf(rs), "win": round(len(wins) / n * 100, 1)}


def row(label, key):
    a7 = drift(key, 7)
    a3 = drift(key, 3)
    return f"{label:26s}  ≤7d: PF {a7['pf'] if a7['pf'] else '—':>6}  n={a7['n']:>4}  win {a7['win'] if a7['win'] is not None else '—':>5}%   " \
           f"≤3d: PF {a3['pf'] if a3['pf'] else '—':>6}  n={a3['n']:>4}  win {a3['win'] if a3['win'] is not None else '—':>5}%"


print("=" * 100)
print("EARNINGS-DRIFT VALIDATION  (threshold 0.70 · horizon 20 · fixed 2:1 · 0.05R cost)")
print("=" * 100)
print(row("FILING dates (baseline)", "earnings_dates"))
print(row("8-K release dates (fix)", "earnings_8k_dates"))
print("-" * 100)
print(f"Out-of-sample split @ {SPLIT}  (8-K dates):")
print(row("  train (before split)", "earnings_8k_dates") if False else "")
a = drift("earnings_8k_dates", 7, "early")
b = drift("earnings_8k_dates", 7, "late")
c = drift("earnings_8k_dates", 3, "early")
d = drift("earnings_8k_dates", 3, "late")
print(f"  ≤7d train: PF {a['pf'] if a['pf'] else '—':>6} n={a['n']:>4} win {a['win'] if a['win'] is not None else '—':>5}%")
print(f"  ≤7d test : PF {b['pf'] if b['pf'] else '—':>6} n={b['n']:>4} win {b['win'] if b['win'] is not None else '—':>5}%")
print(f"  ≤3d train: PF {c['pf'] if c['pf'] else '—':>6} n={c['n']:>4} win {c['win'] if c['win'] is not None else '—':>5}%")
print(f"  ≤3d test : PF {d['pf'] if d['pf'] else '—':>6} n={d['n']:>4} win {d['win'] if d['win'] is not None else '—':>5}%")

# filing-date lag (median days the 10-K/10-Q lags the 8-K release)
lags = []
for sym, rec in cat.items():
    e8 = epochs(sym, "earnings_8k_dates")
    ef = epochs(sym, "earnings_dates")
    # match each 8-K to the nearest later filing date
    for e in e8:
        later = [f for f in ef if f >= e]
        if later:
            lags.append((min(later) - e) / 86400.0)
lags.sort()
if lags:
    med = lags[len(lags) // 2]
    print("-" * 100)
    print(f"Median filing-date lag behind release: {med:.1f} days (n={len(lags)} matched) — "
          f"this is how far off the current drift anchor is.")
