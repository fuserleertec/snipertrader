#!/usr/bin/env python3
"""Long/short momentum-factor backtest — the correct test for cross-sectional
relative momentum (an ALLOCATION signal, not a timing signal).

At each rebalance date, rank the universe by the `window`-bar rate-of-change
(skipping the most recent `skip` bars — the classic momentum-factor convention),
go long the top `top_frac`, short the bottom `top_frac`, equal-weight, and hold
to the next rebalance.  Rebalancing is on a CALENDAR grid (`rebalance_days`),
so "monthly" really is ~30 days.  No lookahead: signal uses data <= rebalance
time, returns are measured over the following holding period.

Reports the long/short spread: total return, hit rate, t-stat, Sharpe, turnover,
and net-of-cost.  Distinct from the per-symbol TP/SL timing backtest.
"""
import json
import math
from bisect import bisect_right

from compute_engine import cross_sectional

RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"


def _close_lookup(raw):
    """{sym: ([sorted ts], [closes])}."""
    out = {}
    for sym, rec in raw.items():
        out[sym] = ([b["t"] for b in rec["bars"]], [b["c"] for b in rec["bars"]])
    return out


def _close_at(cm, sym, t):
    ts, cl = cm[sym]
    i = bisect_right(ts, t) - 1
    return cl[i] if i >= 0 else None


def _compound(rets):
    x = 1.0
    for r in rets:
        x *= (1.0 + r)
    return x - 1.0


def _sharpe(rets, periods_per_year):
    n = len(rets)
    if n < 3:
        return None
    m = sum(rets) / n
    var = sum((r - m) ** 2 for r in rets) / n
    sd = math.sqrt(var)
    if sd <= 1e-12:
        return None
    return m / sd * math.sqrt(periods_per_year)


def factor_backtest(raw, window=20, top_frac=0.2, rebalance_days=1, cost_side=0.0005, skip=0):
    roc_series, _ = cross_sectional(raw, window, skip=skip)
    cm = _close_lookup(raw)
    t_lists = {sym: [x[0] for x in ser] for sym, ser in roc_series.items()}
    r_lists = {sym: [x[1] for x in ser] for sym, ser in roc_series.items()}
    all_ts = sorted({t for ser in roc_series.values() for (t, _) in ser})
    t0, t1 = all_ts[0], all_ts[-1]
    interval = rebalance_days * 86400
    grid = list(range(t0, t1 + 1, interval))

    spread_rets, long_rets, short_rets = [], [], []
    turnovers = []
    prev_long, prev_short = set(), set()
    k = 0

    for idx in range(len(grid) - 1):
        t = grid[idx]
        t_next = grid[idx + 1]
        scored = []
        for sym in roc_series:
            i = bisect_right(t_lists[sym], t) - 1
            if i >= 0:
                scored.append((sym, r_lists[sym][i]))
        if len(scored) < 6:
            continue
        scored.sort(key=lambda x: x[1])
        k = max(1, int(len(scored) * top_frac))
        longs = [s for s, _ in scored[-k:]]
        shorts = [s for s, _ in scored[:k]]

        lr, sr = [], []
        for s in longs:
            c0, c1 = _close_at(cm, s, t), _close_at(cm, s, t_next)
            if c0 and c1 is not None and c0 > 0:
                lr.append(c1 / c0 - 1)
        for s in shorts:
            c0, c1 = _close_at(cm, s, t), _close_at(cm, s, t_next)
            if c0 and c1 is not None and c0 > 0:
                sr.append(c1 / c0 - 1)
        if not lr or not sr:
            continue

        long_ret = sum(lr) / len(lr)
        short_ret = sum(sr) / len(sr)
        spread_rets.append(long_ret - short_ret)
        long_rets.append(long_ret)
        short_rets.append(short_ret)

        cur_long, cur_short = set(longs), set(shorts)
        if prev_long:
            turn = (len(cur_long - prev_long) + len(cur_short - prev_short)) / (2.0 * k)
            turnovers.append(turn)
        prev_long, prev_short = cur_long, cur_short

    n = len(spread_rets)
    if n == 0:
        return {"n": 0}

    days = (t1 - t0) / 86400.0
    ppy = 365.0 / rebalance_days

    m = sum(spread_rets) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in spread_rets) / n)
    t_stat = (m / (sd / math.sqrt(n))) if sd > 1e-12 else 0.0
    hits = sum(1 for r in spread_rets if r > 0)

    gross_ret = _compound(spread_rets)
    long_ret = _compound(long_rets)
    short_ret = _compound(short_rets)

    avg_turn = sum(turnovers) / len(turnovers) if turnovers else 0.0
    net_rets = [r - (2.0 * avg_turn * cost_side) for r in spread_rets]
    net_ret = _compound(net_rets)

    sharpe = _sharpe(spread_rets, ppy)

    return {
        "n": n,
        "days": round(days, 0),
        "window": window,
        "skip": skip,
        "rebalance_days": rebalance_days,
        "top_frac": top_frac,
        "cost_side": cost_side,
        "leg_size": k,
        "mean_spread_bps": round(m * 10000, 1),
        "t_stat": round(t_stat, 2),
        "hit_rate": round(hits / n, 3),
        "sharpe_gross": round(sharpe, 2) if sharpe is not None else None,
        "gross_return_pct": round(gross_ret * 100, 1),
        "avg_turnover": round(avg_turn, 3),
        "net_return_pct": round(net_ret * 100, 1),
        "long_return_pct": round(long_ret * 100, 1),
        "short_return_pct": round(short_ret * 100, 1),
    }


def main():
    raw = json.load(open(RAW))
    print(f"universe: {len(raw)} symbols, "
          f"{min(len(r['bars']) for r in raw.values())}-{max(len(r['bars']) for r in raw.values())} bars/symbol\n")
    configs = [
        # (window, skip, rebalance_days, top_frac, cost_side)
        (20,   0,  1, 0.2, 0.0005),   # 1-month momentum, daily (reversal baseline)
        (60,  20,  7, 0.2, 0.0005),   # 3-month momentum, 1-month skip, weekly
        (120, 20,  7, 0.2, 0.0005),   # 6-month momentum, 1-month skip, weekly
        (120, 20, 30, 0.2, 0.0005),   # 6-month momentum, 1-month skip, monthly
        (180, 20, 30, 0.2, 0.0005),   # 9-month momentum, 1-month skip, monthly
        (240, 20, 30, 0.2, 0.0005),   # 12-month momentum, 1-month skip, monthly (thin sample)
    ]
    for window, skip, rebal, frac, cost in configs:
        r = factor_backtest(raw, window=window, skip=skip, rebalance_days=rebal, top_frac=frac, cost_side=cost)
        if r["n"] == 0:
            print(f"window={window} skip={skip} rebal={rebal}d: no trades")
            continue
        print(f"window={window:3d} skip={skip:2d} rebal={rebal:2d}d top_frac={frac} cost={cost:.4f}  leg={r['leg_size']}  n={r['n']:4d}")
        print(f"    spread {r['mean_spread_bps']:+.1f} bps/rebal  t={r['t_stat']:+.2f}  "
              f"hit={r['hit_rate']:.0%}  Sharpe(gross)={r['sharpe_gross']}")
        print(f"    gross {r['gross_return_pct']:+.1f}%  net {r['net_return_pct']:+.1f}%  "
              f"long {r['long_return_pct']:+.1f}% / short {r['short_return_pct']:+.1f}%  turnover {r['avg_turnover']:.0%}/rebal")
        print()


if __name__ == "__main__":
    main()
