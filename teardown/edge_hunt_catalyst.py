#!/usr/bin/env python3
"""Catalyst edge hunt: does earnings-recency (10-K/10-Q filing date) gate improve PF?

Point-in-time: for each bar, days since the most recent 10-K/10-Q filing.
Tests post-earnings drift vs baseline on the best config (fixed2 thr=0.70 hz=20).
"""
import json
import time
from backtest_trades import sim_trade

RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
FEAT = "/Users/snipertrader/snipertrader/teardown/features.json"
CAT = "/Users/snipertrader/snipertrader/teardown/catalysts.json"

raw = json.load(open(RAW))
feats = json.load(open(FEAT))
cat = json.load(open(CAT))


def earnings_epochs(sym):
    dates = cat.get(sym, {}).get("earnings_dates", [])
    out = []
    for d in dates:
        try:
            out.append(int(time.mktime(time.strptime(d, "%Y-%m-%d"))))
        except Exception:
            pass
    return sorted(out)


def days_since_earnings(sym, bars):
    """map bar index -> days since most recent earnings filing (or None if none yet)."""
    eps = earnings_epochs(sym)
    out = {}
    for i, b in enumerate(bars):
        prev = [e for e in eps if e <= b["t"]]
        out[i] = (b["t"] - prev[-1]) / 86400.0 if prev else None
    return out


def run(threshold, horizon, rr_mode, cost_r, max_days=None):
    trades = []
    for sym, snap in feats.items():
        bars = raw[sym]["bars"]
        dsm = days_since_earnings(sym, bars)
        for s in snap:
            cons = s["consensus"]
            d = "LONG" if cons >= threshold else ("SHORT" if cons <= 1 - threshold else None)
            if d is None:
                continue
            if max_days is not None:
                ds = dsm.get(s["i"])
                if ds is None or ds > max_days:
                    continue
            r = sim_trade(bars, s, d, horizon, rr_mode)
            if r is not None:
                trades.append(r - cost_r)
    n = len(trades)
    if n == 0:
        return {"n": 0}
    wins = [r for r in trades if r > 0]
    gw = sum(wins)
    gl = -sum(r for r in trades if r <= 0)
    return {
        "n": n,
        "win_rate": round(len(wins) / n * 100, 1),
        "expectancy_R": round(sum(trades) / n, 3),
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "total_R": round(sum(trades), 1),
    }


print(f"{'gate':>22} | {'n':>6} {'win%':>6} {'E[R]':>7} {'PF':>7} {'totalR':>8}")
print("-" * 66)
for cost in (0.0, 0.05):
    print(f"--- cost {cost}R ---")
    for label, md in [("baseline (no gate)", None), ("<=60d since earnings", 60), ("<=30d", 30),
                      ("<=14d", 14), ("<=7d (post-earnings)", 7), ("<=3d", 3)]:
        m = run(0.70, 20, "fixed2", cost, md)
        if m.get("n", 0) == 0:
            print(f"{label:>22} | no trades")
            continue
        print(f"{label:>22} | {m['n']:>6} {m['win_rate']:>5.1f}% {m['expectancy_R']:>+7.3f} "
              f"{m['profit_factor'] if m['profit_factor'] is not None else '—':>7} {m['total_R']:>+8.1f}")
