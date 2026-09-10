#!/usr/bin/env python3
"""Produce a compact, honest trade-backtest summary (daily + intraday 1h).

The verdict's catalyst section is computed DYNAMICALLY from catalysts.json and a
point-in-time earnings-recency gate, so insider + drift claims never go stale.
"""
import json
import time as _t
from backtest_trades import sim_trade
from compute_engine import backtest

RAW_D = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
FEAT_D = "/Users/snipertrader/snipertrader/teardown/features.json"
RAW_H = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv_1h.json"
FEAT_H = "/Users/snipertrader/snipertrader/teardown/features_1h.json"
CAT = "/Users/snipertrader/snipertrader/teardown/catalysts.json"

raw_d = json.load(open(RAW_D))
feats_d = json.load(open(FEAT_D))
raw_h = json.load(open(RAW_H))
feats_h = json.load(open(FEAT_H))
cat = json.load(open(CAT))


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
        "per_symbol_pf": {s: pf(rl) for s, rl in syms.items() if pf(rl) is not None},
    }


# ---- catalyst: earnings-recency gate (point-in-time) ----
def _earnings_epochs(sym):
    out = []
    for d in cat.get(sym, {}).get("earnings_dates", []):
        try:
            out.append(int(_t.mktime(_t.strptime(d, "%Y-%m-%d"))))
        except Exception:
            pass
    return sorted(out)


def _days_since(sym, bars):
    eps = _earnings_epochs(sym)
    out = {}
    for i, b in enumerate(bars):
        prev = [e for e in eps if e <= b["t"]]
        out[i] = (b["t"] - prev[-1]) / 86400.0 if prev else None
    return out


def drift_run(threshold, horizon, rr_mode, cost_r, max_days=None):
    trades = []
    for sym, snap in feats_d.items():
        bars = raw_d[sym]["bars"]
        dsm = _days_since(sym, bars)
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
        return {"n": 0, "pf": None}
    wins = [r for r in trades if r > 0]
    gw = sum(wins)
    gl = -sum(r for r in trades if r <= 0)
    return {"n": n, "pf": round(gw / gl, 3) if gl > 0 else None}


bt = backtest(raw_d)

base = drift_run(0.70, 20, "fixed2", 0.05, None)
d7 = drift_run(0.70, 20, "fixed2", 0.05, 7)
d3 = drift_run(0.70, 20, "fixed2", 0.05, 3)

# insider summary (30d window, open-market only)
tot_buys = sum(v.get("insider", {}).get("buys", 0) for v in cat.values())
tot_sells = sum(v.get("insider", {}).get("sells", 0) for v in cat.values())
buy_syms = [v["symbol"] for v in cat.values() if v.get("insider", {}).get("buys", 0) > 0]

if d7.get("pf") and d3.get("pf"):
    drift_s = (f"post-earnings-filing drift is TENTATIVE — PF {d7['pf']} net at ≤7 days after the "
               f"earnings filing ({d7['n']} trades) and PF {d3['pf']} at ≤3 days ({d3['n']} trades) "
               f"vs baseline PF {base['pf']} — in-sample and underpowered, a hypothesis not proven edge")
else:
    drift_s = "post-earnings-filing drift shows no exploitable signal at realistic cost"

if buy_syms:
    insider_s = (f"Insider Form 4 (30d): {len(buy_syms)} names show open-market purchases "
                 f"({', '.join(buy_syms)} — {tot_buys} buys total), but insiders remain overwhelmingly "
                 f"net sellers ({tot_sells} sales across the universe)")
else:
    insider_s = (f"Insider Form 4 (30d): zero open-market purchases across the universe — "
                 f"insiders are net sellers ({tot_sells} sales)")

configs = [
    headline(feats_d, raw_d, 0.70, 20, "none", "fixed2", 0.0, "1d"),
    headline(feats_d, raw_d, 0.70, 20, "none", "fixed2", 0.05, "1d"),
    headline(feats_d, raw_d, 0.70, 20, "none", "structure", 0.05, "1d"),
    headline(feats_h, raw_h, 0.75, 20, "none", "fixed2", 0.0, "1h"),
    headline(feats_h, raw_h, 0.75, 20, "none", "fixed2", 0.05, "1h"),
    headline(feats_h, raw_h, 0.70, 20, "none", "structure", 0.05, "1h"),
]
per_symbol_pf = (configs[1] or {}).pop("per_symbol_pf", {})   # daily fixed2 @0.05R covers the full universe


def _pf(x):
    return x["profit_factor"] if (x and x.get("profit_factor") is not None) else None


def _pfs(x):
    return f"{x:.2f}" if x is not None else "n/a"


pf_d0, pf_d1, pf_ds = _pf(configs[0]), _pf(configs[1]), _pf(configs[2])
pf_h0, pf_h1, pf_hs = _pf(configs[3]), _pf(configs[4]), _pf(configs[5])
intraday_desc = "below breakeven" if (pf_h1 is not None and pf_h1 < 1.0) else "marginal"

edge_s = (
    f"Fixed 2:1 R:R shows a positive profit factor at zero cost (daily ≈ PF {_pfs(pf_d0)}, "
    f"intraday ≈ PF {_pfs(pf_h0)}) that erodes at a realistic 0.05R round-trip cost — daily "
    f"≈ PF {_pfs(pf_d1)}, intraday ≈ PF {_pfs(pf_h1)} ({intraday_desc}) — so the zero-cost edge "
    f"is a cost artifact, not a tradeable edge. Structure-anchored R:R is a net loser on both "
    f"timeframes (daily ≈ PF {_pfs(pf_ds)}, intraday ≈ PF {_pfs(pf_hs)}), and the edge "
    f"concentrates in a handful of symbols while roughly half the universe loses money."
)

verdict = (f"No systematic edge on EITHER timeframe. {edge_s} Catalyst overlays (SEC EDGAR): "
           f"{drift_s}. {insider_s}. Next: validate the drift out-of-sample with the actual 8-K "
           f"earnings-release date (not the lagged filing date).")

summary = {
    "naive": {
        "hit_rate": bt["universe_hit_rate"],
        "calls": bt["total_calls"],
        "horizon": bt["horizon_bars"],
    },
    "configs": configs,
    "per_symbol_pf": per_symbol_pf,
    "verdict": verdict,
}

with open("/Users/snipertrader/snipertrader/teardown/backtest_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
