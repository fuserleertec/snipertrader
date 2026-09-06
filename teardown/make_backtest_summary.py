#!/usr/bin/env python3
"""Produce a compact, honest trade-backtest summary for the terminal UI."""
import json
from backtest_trades import sim_trade
from compute_engine import backtest

RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
FEAT = "/Users/snipertrader/snipertrader/teardown/features.json"

with open(RAW) as f:
    raw = json.load(f)
with open(FEAT) as f:
    feats = json.load(f)

def pf(rs):
    w = sum(r for r in rs if r > 0)
    l = -sum(r for r in rs if r <= 0)
    return round(w / l, 3) if l > 0 else None

def config_trades(threshold, horizon, gate, rr_mode, cost_r):
    """Return list of (sym, i, r_net)."""
    out = []
    for sym, snap in feats.items():
        bars = raw[sym]["bars"]
        for s in snap:
            cons = s["consensus"]
            d = "LONG" if cons >= threshold else ("SHORT" if cons <= 1 - threshold else None)
            if d is None:
                continue
            if gate == "trend":
                if d == "LONG" and s["trend"] != "up":
                    continue
                if d == "SHORT" and s["trend"] != "down":
                    continue
            r = sim_trade(bars, s, d, horizon, rr_mode)
            if r is not None:
                out.append((sym, s["i"], r - cost_r))
    return out

def headline(threshold, horizon, gate, rr_mode, cost_r):
    tr = config_trades(threshold, horizon, gate, rr_mode, cost_r)
    rs = [r for _, _, r in tr]
    n = len(rs)
    if n == 0:
        return None
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gw = sum(wins)
    gl = -sum(losses)
    # concentration: top-5 vs bottom-5 symbol PF
    syms = {}
    for sym, _, r in tr:
        syms.setdefault(sym, []).append(r)
    pfs = sorted(((s, pf(rl)) for s, rl in syms.items() if pf(rl) is not None), key=lambda x: x[1])
    return {
        "config": f"thr={threshold} hz={horizon} {gate} {rr_mode} cost={cost_r}R",
        "n": n,
        "win_rate": round(len(wins) / n * 100, 1),
        "expectancy_R": round(sum(rs) / n, 3),
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "total_R": round(sum(rs), 1),
        "top5": [(s, p) for s, p in pfs[-5:]],
        "bottom5": [(s, p) for s, p in pfs[:5]],
    }

# naive directional hit-rate (the dashboard's "61%" equivalent, measured honestly)
bt = backtest(raw)

summary = {
    "naive": {
        "hit_rate": bt["universe_hit_rate"],
        "calls": bt["total_calls"],
        "horizon": bt["horizon_days"],
    },
    "configs": [
        headline(0.70, 20, "none", "fixed2", 0.0),
        headline(0.70, 20, "none", "fixed2", 0.05),
        headline(0.70, 20, "none", "structure", 0.05),
    ],
    "verdict": "No systematic edge. The fixed 2:1 risk/reward shows a small positive profit factor at "
               "zero cost (a cost-free artifact), which collapses to ~breakeven at a realistic 0.05R "
               "round-trip cost, and the edge is concentrated in ~5 symbols while roughly half the "
               "universe loses money. Structure-anchored R:R (the current terminal's approach) is a "
               "net loser. Finding real alpha needs better inputs — intraday bars (VWAP/FVG/order-block "
               "are intraday concepts), catalyst overlays (SEC Form 4, earnings), and a focused "
               "single hypothesis rather than a naive 8-way vote.",
}

with open("/Users/snipertrader/snipertrader/teardown/backtest_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
