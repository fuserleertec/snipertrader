#!/usr/bin/env python3
"""
Proper trade-level backtest for the SniperTrader ensemble.

Replaces the naive "did price move in the called direction" check with a real
trade simulation: entry at close, stop + target from structure or fixed R:R,
walked forward until TP/SL is hit or the horizon expires (mark-to-market).
Reports win rate, expectancy (in R), and profit factor — the metrics that
actually determine whether the ensemble has edge, net of costs.

Sweeps thresholds/horizon/regime-gate/RR-mode/cost transparently and prints
the full table so nothing is cherry-picked.
"""
import json
import itertools
from compute_engine import kronos, mirofish, atr_series

RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json"
FEAT = "/Users/snipertrader/snipertrader/teardown/features.json"

MIN_HIST = 60

def precompute(raw, cache_path=FEAT):
    """Point-in-time features per symbol per bar (>= MIN_HIST). Computed once,
    cached. This is the O(n^2) part; the sweep reads from here and is fast."""
    feats = {}
    for sym, rec in raw.items():
        bars = rec["bars"]
        snap = []
        for i in range(MIN_HIST, len(bars)):
            window = bars[: i + 1]
            k = kronos(window)
            mf = mirofish(window, k)
            atr = atr_series(window)
            snap.append({
                "i": i,
                "close": bars[i]["c"],
                "consensus": mf["consensus"],
                "trend": k["trend"],
                "mss": k["mss"],
                "support": k["support"],
                "resistance": k["resistance"],
                "atr": atr[-1] if atr else None,
            })
        feats[sym] = snap
        print(f"  precompute {sym:10s} {len(snap)} snapshots")
    with open(cache_path, "w") as f:
        json.dump(feats, f)
    return feats

def sim_trade(bars, s, direction, horizon, rr_mode):
    """Simulate one trade. Returns realized R (win>0, loss<0). s = snapshot."""
    entry = s["close"]
    atr = s["atr"]
    if atr is None or atr <= 0:
        return None
    if direction == "LONG":
        if rr_mode == "structure":
            stop = min(s["support"], entry - atr) if s["support"] and s["support"] < entry else entry - atr
            target = min(s["resistance"], entry + 3.0 * atr) if s["resistance"] and s["resistance"] > entry else entry + 2.0 * atr
            target = max(target, entry + atr)
        else:  # fixed2
            stop = entry - atr
            target = entry + 2.0 * atr
    else:  # SHORT
        if rr_mode == "structure":
            stop = max(s["resistance"], entry + atr) if s["resistance"] and s["resistance"] > entry else entry + atr
            target = max(s["support"], entry - 3.0 * atr) if s["support"] and s["support"] < entry else entry - 2.0 * atr
            target = min(target, entry - atr)
        else:
            stop = entry + atr
            target = entry - 2.0 * atr

    risk = abs(entry - stop)
    if risk <= 0:
        return None
    rr_target = abs(target - entry) / risk

    end = min(s["i"] + horizon, len(bars) - 1)
    for j in range(s["i"] + 1, end + 1):
        lo, hi = bars[j]["l"], bars[j]["h"]
        if direction == "LONG":
            # conservative: assume stop hit first if both touch in the same bar
            if lo <= stop:
                return -1.0
            if hi >= target:
                return rr_target
        else:
            if hi >= stop:
                return -1.0
            if lo <= target:
                return rr_target
    # horizon expired -> mark to market
    exit_px = bars[end]["c"]
    r = (exit_px - entry) / risk if direction == "LONG" else (entry - exit_px) / risk
    return r

def run_config(feats, raw, threshold, horizon, gate, rr_mode, cost_r):
    """Run the whole universe for one config. Returns aggregate metrics."""
    trades = []  # list of realized R (net of cost)
    for sym, snap in feats.items():
        bars = raw[sym]["bars"]
        for s in snap:
            cons = s["consensus"]
            direction = None
            if cons >= threshold:
                direction = "LONG"
            elif cons <= 1.0 - threshold:
                direction = "SHORT"
            if direction is None:
                continue
            if gate == "trend":
                if direction == "LONG" and s["trend"] != "up":
                    continue
                if direction == "SHORT" and s["trend"] != "down":
                    continue
            r = sim_trade(bars, s, direction, horizon, rr_mode)
            if r is not None:
                trades.append(r - cost_r)

    n = len(trades)
    if n == 0:
        return {"n": 0}
    wins = [r for r in trades if r > 0]
    losses = [r for r in trades if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "n": n,
        "win_rate": round(len(wins) / n, 4),
        "expectancy_R": round(sum(trades) / n, 4),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
        "total_R": round(sum(trades), 2),
        "avg_win_R": round(sum(wins) / len(wins), 3) if wins else None,
        "avg_loss_R": round(sum(losses) / len(losses), 3) if losses else None,
    }

def main():
    import os, time
    with open(RAW) as f:
        raw = json.load(f)
    if os.path.exists(FEAT):
        with open(FEAT) as f:
            feats = json.load(f)
        print(f"loaded cached features ({len(feats)} symbols)")
    else:
        t0 = time.time()
        feats = precompute(raw)
        print(f"precompute done in {time.time()-t0:.1f}s")

    thresholds = [0.55, 0.60, 0.65, 0.70, 0.75]
    horizons = [5, 10, 20]
    gates = ["none", "trend"]
    rr_modes = ["structure", "fixed2"]
    costs = [0.0, 0.05, 0.15]

    rows = []
    for thr, hz, gate, rrm, cost in itertools.product(thresholds, horizons, gates, rr_modes, costs):
        m = run_config(feats, raw, thr, hz, gate, rrm, cost)
        if m.get("n", 0) < 30:      # too few trades to be meaningful
            continue
        rows.append({
            "threshold": thr, "horizon": hz, "gate": gate, "rr": rrm, "cost_R": cost,
            **m,
        })
        print(f"thr={thr} hz={hz:2d} gate={gate:5s} rr={rrm:9s} cost={cost:4.2f} | "
              f"n={m['n']:4d} win={m['win_rate']*100:5.1f}%  E[R]={m['expectancy_R']:+.3f}  "
              f"PF={m['profit_factor']}  totalR={m['total_R']:+7.1f}")

    # rank by profit factor (tie-break expectancy), most meaningful configs first
    rows.sort(key=lambda r: (r["profit_factor"] if r["profit_factor"] is not None else -1, r["expectancy_R"]), reverse=True)
    with open("/Users/snipertrader/snipertrader/teardown/sweep_results.json", "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\n{len(rows)} configs with >=30 trades written to sweep_results.json")

if __name__ == "__main__":
    main()
