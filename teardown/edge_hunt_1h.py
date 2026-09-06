#!/usr/bin/env python3
"""Run the honest edge-hunt sweep on intraday 1h data."""
import json, os, itertools, time
from backtest_trades import precompute, run_config

RAW = "/Users/snipertrader/snipertrader/teardown/raw_ohlcv_1h.json"
FEAT = "/Users/snipertrader/snipertrader/teardown/features_1h.json"

with open(RAW) as f:
    raw = json.load(f)

if os.path.exists(FEAT):
    feats = json.load(open(FEAT))
    print(f"loaded cached 1h features ({len(feats)} symbols)")
else:
    t0 = time.time()
    feats = precompute(raw, FEAT)
    print(f"precompute 1h done in {time.time()-t0:.1f}s")

thresholds = [0.55, 0.60, 0.65, 0.70, 0.75]
horizons = [5, 10, 20, 48]        # 5/10/20 hours + ~2 days (48h)
gates = ["none", "trend"]
rr_modes = ["structure", "fixed2"]
costs = [0.0, 0.05, 0.15]

rows = []
for thr, hz, gate, rrm, cost in itertools.product(thresholds, horizons, gates, rr_modes, costs):
    m = run_config(feats, raw, thr, hz, gate, rrm, cost)
    if m.get("n", 0) < 30:
        continue
    rows.append({"threshold": thr, "horizon_bars": hz, "gate": gate, "rr": rrm, "cost_R": cost, **m})

rows.sort(key=lambda r: (r["profit_factor"] if r["profit_factor"] is not None else -1, r["expectancy_R"]), reverse=True)
with open("/Users/snipertrader/snipertrader/teardown/sweep_1h.json", "w") as f:
    json.dump(rows, f, indent=2)

print(f"\n{len(rows)} configs (>=30 trades). TOP 20 by profit factor:")
print(f"{'thr':>4} {'hz':>3} {'gate':>5} {'rr':>9} {'cost':>5} | {'n':>6} {'win%':>6} {'E[R]':>7} {'PF':>7} {'totalR':>8}")
for r in rows[:20]:
    print(f"{r['threshold']:>4} {r['horizon_bars']:>3} {r['gate']:>5} {r['rr']:>9} {r['cost_R']:>5.2f} | "
          f"{r['n']:>6} {r['win_rate']*100:>5.1f}% {r['expectancy_R']:>+7.3f} "
          f"{r['profit_factor'] if r['profit_factor'] is not None else '—':>7} {r['total_R']:>+8.1f}")

# best net-of-cost config
best_net = [r for r in rows if r['cost_R'] == 0.05 and r['profit_factor'] is not None]
best_net.sort(key=lambda r: r['profit_factor'], reverse=True)
print("\nBest NET-of-cost (0.05R) config:", json.dumps(best_net[0], indent=2) if best_net else "none")
