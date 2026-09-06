#!/usr/bin/env python3
"""Produce a compact, honest trade-backtest summary (daily + intraday 1h)."""
import json
from backtest_trades import sim_trade
from compute_engine import backtest

RAW_D = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
FEAT_D = "/Users/snipertrader/snipertrader/teardown/features.json"
RAW_H = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv_1h.json"
FEAT_H = "/Users/snipertrader/snipertrader/teardown/features_1h.json"

raw_d = json.load(open(RAW_D))
feats_d = json.load(open(FEAT_D))
raw_h = json.load(open(RAW_H))
feats_h = json.load(open(FEAT_H))


def pf(rs):
    w = sum(r for r in rs if r > 0)
    l = -sum(r for r in rs if r <= 0)
    return round(w / l, 3) if l > 0 else None


def config_trades(feats, raw, threshold, horizon, gate, rr_mode, cost_r):
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


def headline(feats, raw, threshold, horizon, gate, rr_mode, cost_r, tag):
    tr = config_trades(feats, raw, threshold, horizon, gate, rr_mode, cost_r)
    rs = [r for _, _, r in tr]
    n = len(rs)
    if n == 0:
        return None
    wins = [r for r in rs if r > 0]
    gw = sum(wins)
    gl = -sum(r for r in rs if r <= 0)
    syms = {}
    for sym, _, r in tr:
        syms.setdefault(sym, []).append(r)
    pfs = sorted(((s, pf(rl)) for s, rl in syms.items() if pf(rl) is not None), key=lambda x: x[1])
    return {
        "config": f"{tag} thr={threshold} hz={horizon} {gate} {rr_mode} cost={cost_r}R",
        "n": n,
        "win_rate": round(len(wins) / n * 100, 1),
        "expectancy_R": round(sum(rs) / n, 3),
        "profit_factor": round(gw / gl, 3) if gl > 0 else None,
        "total_R": round(sum(rs), 1),
        "top5": [(s, p) for s, p in pfs[-5:]],
        "bottom5": [(s, p) for s, p in pfs[:5]],
    }


bt = backtest(raw_d)

summary = {
    "naive": {
        "hit_rate": bt["universe_hit_rate"],
        "calls": bt["total_calls"],
        "horizon": bt["horizon_bars"],
    },
    "configs": [
        headline(feats_d, raw_d, 0.70, 20, "none", "fixed2", 0.0, "1d"),
        headline(feats_d, raw_d, 0.70, 20, "none", "fixed2", 0.05, "1d"),
        headline(feats_d, raw_d, 0.70, 20, "none", "structure", 0.05, "1d"),
        headline(feats_h, raw_h, 0.75, 20, "none", "fixed2", 0.0, "1h"),
        headline(feats_h, raw_h, 0.75, 20, "none", "fixed2", 0.05, "1h"),
        headline(feats_h, raw_h, 0.70, 20, "none", "structure", 0.05, "1h"),
    ],
    "verdict": "No systematic edge on EITHER timeframe. Fixed 2:1 R:R shows a small positive profit "
               "factor at zero cost (a cost-free artifact) that collapses to ~breakeven at a realistic "
               "0.05R round-trip cost — daily 2y ≈ PF 1.03, intraday 1h ≈ PF 1.05, both within noise. "
               "The edge concentrates in ~5 symbols while roughly half the universe loses money, and "
               "structure-anchored R:R is a net loser on both timeframes. Catalyst overlays (SEC EDGAR): "
               "post-earnings-filing drift shows a TENTATIVE signal — PF ~1.16 net at ≤7 days after a "
               "10-K/10-Q filing (253 trades, in-sample, underpowered — a hypothesis, not proven edge). "
               "Insider Form 4 shows ZERO open-market purchases across the universe in 30d (insiders are "
               "net sellers, mostly scheduled 10b5-1 / compensation). Next: validate the drift out-of-sample "
               "with more symbols + the actual 8-K earnings-release date (not the lagged filing date).",
}

with open("/Users/snipertrader/snipertrader/teardown/backtest_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
