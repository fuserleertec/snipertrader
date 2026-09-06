#!/usr/bin/env python3
"""
Real signal engine for the SniperTrader terminal redesign.

Every number here is a deterministic function of real OHLCV (Yahoo, key-less).
No Monte-Carlo-over-nothing, no random swarm votes.

Three engines:
  1. KRONOS  — structural detection from the actual k-lines:
     anchored VWAP, Fair Value Gaps, order blocks, liquidity sweeps,
     Market Structure Shift, trend structure.
  2. MIROFISH — an ensemble of 8 deterministic technical models, each casting
     a traceable Bull/Neutral/Bear vote with a confidence from a real formula.
     The "swarm" is the honest aggregate of those real votes (NOT random).
  3. CONE    — volatility-anchored probability: empirical distribution of
     forward returns over the lookback -> P(bull/base/bear). Not a simulated
     Monte-Carlo draw.

Outputs results.json consumed by the HTML prototype.
"""
import json
import math

ATR_N = 14
VWAP_N = 20
PIVOT_K = 3
FWD_BARS = 5

# --------------------------------------------------------------------------- #
# Indicators (standard definitions)
# --------------------------------------------------------------------------- #
def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n

def ema_series(vals, n):
    k = 2.0 / (n + 1)
    out = []
    prev = None
    for v in vals:
        prev = v if prev is None else (v * k + prev * (1 - k))
        out.append(prev)
    return out

def atr_series(bars, n=ATR_N):
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return None
    # Wilder smoothing
    atr = sum(trs[:n]) / n
    out = [None] * n + [atr]
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
        out.append(atr)
    return out

def rsi_series(bars, n=14):
    gains, losses = [], []
    for i in range(1, len(bars)):
        ch = bars[i]["c"] - bars[i - 1]["c"]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    if len(gains) < n:
        return None
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out = [None] * n
    out[-1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    return out

def rolling_vwap(bars, n=VWAP_N):
    """Anchored VWAP over the last n bars (typical price)."""
    if len(bars) < n:
        return None
    pv = vv = 0.0
    for b in bars[-n:]:
        tp = (b["h"] + b["l"] + b["c"]) / 3.0
        pv += tp * b["v"]
        vv += b["v"]
    return pv / vv if vv > 0 else None

def obv_series(bars):
    obv, run = [], 0.0
    for i, b in enumerate(bars):
        if i == 0:
            obv.append(run)
            continue
        if b["c"] > bars[i - 1]["c"]:
            run += b["v"]
        elif b["c"] < bars[i - 1]["c"]:
            run -= b["v"]
        obv.append(run)
    return obv

def swing_pivots(bars, k=PIVOT_K):
    """Return (index, kind, price) for pivot highs/lows. kind in {'H','L'}."""
    piv = []
    for i in range(k, len(bars) - k):
        win_h = [bars[j]["h"] for j in range(i - k, i + k + 1)]
        win_l = [bars[j]["l"] for j in range(i - k, i + k + 1)]
        if bars[i]["h"] == max(win_h):
            piv.append((i, "H", bars[i]["h"]))
        if bars[i]["l"] == min(win_l):
            piv.append((i, "L", bars[i]["l"]))
    return piv

def fwd_returns(bars, n=FWD_BARS):
    """Overlapping n-day simple returns, aligned to the start bar."""
    out = []
    closes = [b["c"] for b in bars]
    for i in range(len(closes) - n):
        out.append(closes[i + n] / closes[i] - 1.0)
    return out

# --------------------------------------------------------------------------- #
# KRONOS — structural detection
# --------------------------------------------------------------------------- #
def kronos(bars):
    c = bars[-1]["c"]
    piv = swing_pivots(bars)
    piv_h = [p for p in piv if p[1] == "H"]
    piv_l = [p for p in piv if p[1] == "L"]
    vwap = rolling_vwap(bars)

    # Trend structure: compare last two swing highs/lows
    trend = "range"
    if len(piv_h) >= 2 and len(piv_l) >= 2:
        hh = piv_h[-1][2] > piv_h[-2][2]
        ll = piv_l[-1][2] > piv_l[-2][2]
        if hh and ll:
            trend = "up"
        elif not hh and not ll:
            trend = "down"

    # Market Structure Shift: last close vs prior swing extreme
    mss = None
    if piv_h and c > piv_h[-1][2]:
        mss = "bullish"
    elif piv_l and c < piv_l[-1][2]:
        mss = "bearish"

    # Fair Value Gap (most recent, gated > 0.3%)
    fvg = None
    for i in range(len(bars) - 2, 1, -1):
        b0, b2 = bars[i - 2], bars[i]
        gap_up = b0["h"] < b2["l"]
        gap_dn = b0["l"] > b2["h"]
        if gap_up:
            sz = (b2["l"] - b0["h"]) / b0["h"]
            if sz > 0.003:
                fvg = {"dir": "bull", "zone": (b0["h"], b2["l"]), "bar": i, "gap_pct": round(sz * 100, 2)}
                break
        if gap_dn:
            sz = (b0["l"] - b2["h"]) / b0["l"]
            if sz > 0.003:
                fvg = {"dir": "bear", "zone": (b2["h"], b0["l"]), "bar": i, "gap_pct": round(sz * 100, 2)}
                break

    # Order block: last opposite-close candle before a strong impulse
    ob = None
    for i in range(len(bars) - 1, 1, -1):
        b0 = bars[i]
        impulse = (b0["c"] - b0["o"]) / b0["o"]
        if impulse > 0.012:  # strong up candle
            j = i - 1
            while j > 0 and bars[j]["c"] > bars[j]["o"]:
                j -= 1
            if bars[j]["c"] < bars[j]["o"]:
                ob = {"dir": "bull", "zone": (bars[j]["l"], bars[j]["h"]), "bar": j}
                break
        if impulse < -0.012:
            j = i - 1
            while j > 0 and bars[j]["c"] < bars[j]["o"]:
                j -= 1
            if bars[j]["c"] > bars[j]["o"]:
                ob = {"dir": "bear", "zone": (bars[j]["l"], bars[j]["h"]), "bar": j}
                break

    # Liquidity sweep: wick beyond prior k-bar extreme, closes back inside
    sweep = None
    lo_k = min(b["l"] for b in bars[-PIVOT_K - 1:-1])
    hi_k = max(b["h"] for b in bars[-PIVOT_K - 1:-1])
    last = bars[-1]
    if last["l"] < lo_k and last["c"] > lo_k:
        sweep = {"dir": "bull", "level": lo_k}
    elif last["h"] > hi_k and last["c"] < hi_k:
        sweep = {"dir": "bear", "level": hi_k}

    # Key levels
    # Nearest structural levels (nearest swing low below / high above price)
    piv_lows = sorted(p[2] for p in piv_l)
    piv_highs = sorted(p[2] for p in piv_h)
    below = [x for x in piv_lows if x < c]
    above = [x for x in piv_highs if x > c]
    support = max(below) if below else (min(b["l"] for b in bars[-VWAP_N:]))
    resistance = min(above) if above else (max(b["h"] for b in bars[-VWAP_N:]))

    return {
        "close": c,
        "vwap": round(vwap, 4) if vwap else None,
        "vwap_pct": round((c / vwap - 1) * 100, 2) if vwap else None,
        "trend": trend,
        "mss": mss,
        "fvg": fvg,
        "order_block": ob,
        "sweep": sweep,
        "support": round(support, 4),
        "resistance": round(resistance, 4),
    }

# --------------------------------------------------------------------------- #
# MIROFISH — 8 deterministic agents (real votes, traceable)
# --------------------------------------------------------------------------- #
def _conf(x, cap=1.0):
    return round(max(0.0, min(cap, abs(x))), 3)

def mirofish(bars, k):
    closes = [b["c"] for b in bars]
    ema12 = ema_series(closes, 12)[-1]
    ema26 = ema_series(closes, 26)[-1]
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200) if len(closes) >= 200 else sma(closes, len(closes))
    atr = atr_series(bars)
    atr_now = atr[-1] if atr else None
    atr_sma = sma([a for a in atr if a is not None], 20) if atr else None
    rsi = rsi_series(bars)
    rsi_now = rsi[-1] if rsi else None
    obv = obv_series(bars)
    obv_slope = (obv[-1] - obv[-10]) / (obv[-10] or 1) if len(obv) >= 10 else 0.0
    c = closes[-1]

    agents = []

    # 1. Momentum (10-bar ROC)
    if len(closes) >= 11:
        roc = (c / closes[-11] - 1) * 100
        sig = "bull" if roc > 0.5 else ("bear" if roc < -0.5 else "neutral")
        agents.append({"name": "Momentum", "signal": sig, "confidence": _conf(roc / 6), "why": f"10-bar ROC {roc:+.1f}%"})
    else:
        agents.append({"name": "Momentum", "signal": "neutral", "confidence": 0, "why": "insufficient bars"})

    # 2. Trend (EMA12 vs EMA26 + SMA50/200 stack)
    ema_sig = "bull" if ema12 > ema26 else "bear"
    stack = 0
    if sma50 and sma200:
        if c > sma50 > sma200:
            stack = 1
        elif c < sma50 < sma200:
            stack = -1
    spread = (ema12 / ema26 - 1) if ema26 else 0
    sig = "bull" if (ema_sig == "bull" and stack >= 0) else ("bear" if (ema_sig == "bear" and stack <= 0) else "neutral")
    agents.append({"name": "Trend", "signal": sig, "confidence": _conf(abs(spread) * 40 + 0.3 * stack),
                   "why": f"EMA12/26 {'above' if ema12 > ema26 else 'below'}, close vs SMA50 {('>' if c > sma50 else '<') if sma50 else '?'} " +
                           ((">" if sma50 > sma200 else "<") if (sma50 and sma200) else "") + " SMA200"})

    # 3. VWAP (close vs anchored VWAP)
    if k["vwap"]:
        d = (c / k["vwap"] - 1) * 100
        sig = "bull" if d > 0 else "bear"
        agents.append({"name": "VWAP", "signal": sig, "confidence": _conf(abs(d) / 3),
                       "why": f"close {d:+.2f}% vs 20-bar VWAP"})
    else:
        agents.append({"name": "VWAP", "signal": "neutral", "confidence": 0, "why": "no VWAP"})

    # 4. Order block (proximity to nearest OB)
    if k["order_block"]:
        obd = k["order_block"]["dir"]
        zl, zh = k["order_block"]["zone"]
        prox = (c - zl) / (zh - zl) if zh > zl else 0
        if obd == "bull" and c > zl:
            sig = "bull"
        elif obd == "bear" and c < zh:
            sig = "bear"
        else:
            sig = "neutral"
        agents.append({"name": "Order Block", "signal": sig, "confidence": _conf(1 - min(abs(prox), 1)),
                       "why": f"near {obd} OB [{zl:.2f}–{zh:.2f}]"})
    else:
        agents.append({"name": "Order Block", "signal": "neutral", "confidence": 0, "why": "no OB"})

    # 5. Volatility regime (ATR vs 20-bar ATR)
    if atr_now and atr_sma:
        vr = atr_now / atr_sma
        sig = "neutral"
        if vr > 1.25 and (c > sma50 if sma50 else True):
            sig = "bull"
        elif vr > 1.25:
            sig = "bear"
        agents.append({"name": "Volatility", "signal": sig, "confidence": _conf((vr - 1) / 1.5),
                       "why": f"ATR {vr:.2f}x its 20-bar mean"})
    else:
        agents.append({"name": "Volatility", "signal": "neutral", "confidence": 0, "why": "no ATR"})

    # 6. Volume (OBV slope)
    sig = "bull" if obv_slope > 0.02 else ("bear" if obv_slope < -0.02 else "neutral")
    agents.append({"name": "Volume", "signal": sig, "confidence": _conf(abs(obv_slope) * 5),
                   "why": f"OBV 10-bar slope {obv_slope:+.3f}"})

    # 7. Mean reversion (RSI contrarian)
    if rsi_now is not None:
        if rsi_now > 70:
            sig = "bear"
            conf = (rsi_now - 70) / 30
        elif rsi_now < 30:
            sig = "bull"
            conf = (30 - rsi_now) / 30
        else:
            sig = "neutral"
            conf = 0
        agents.append({"name": "Mean Rev", "signal": sig, "confidence": _conf(conf), "why": f"RSI {rsi_now:.0f}"})
    else:
        agents.append({"name": "Mean Rev", "signal": "neutral", "confidence": 0, "why": "no RSI"})

    # 8. Structure (trend + MSS + sweep)
    st = 0
    if k["trend"] == "up":
        st += 1
    elif k["trend"] == "down":
        st -= 1
    if k["mss"] == "bullish":
        st += 1
    elif k["mss"] == "bearish":
        st -= 1
    if k["sweep"] and k["sweep"]["dir"] == "bull":
        st += 0.5
    elif k["sweep"] and k["sweep"]["dir"] == "bear":
        st -= 0.5
    sig = "bull" if st >= 1 else ("bear" if st <= -1 else "neutral")
    agents.append({"name": "Structure", "signal": sig, "confidence": _conf(abs(st) / 2.5),
                   "why": f"trend={k['trend']} mss={k['mss']} sweep={k['sweep']['dir'] if k['sweep'] else '—'}"})

    # Consensus: confidence-weighted, with a uniform prior so a finite ensemble
    # never reads a fake 0% or 100%.  (NEU casts no directional vote.)
    bull = sum(a["confidence"] for a in agents if a["signal"] == "bull")
    bear = sum(a["confidence"] for a in agents if a["signal"] == "bear")
    n_bull = sum(1 for a in agents if a["signal"] == "bull")
    n_bear = sum(1 for a in agents if a["signal"] == "bear")
    n_neu = sum(1 for a in agents if a["signal"] == "neutral")
    consensus = round((bull + 0.5) / (bull + bear + 1.0), 3)
    return {"agents": agents, "bull": round(bull, 3), "bear": round(bear, 3),
            "n_bull": n_bull, "n_bear": n_bear, "n_neu": n_neu,
            "consensus": consensus, "consensus_pct": round(consensus * 100, 1)}

# --------------------------------------------------------------------------- #
# CONE — volatility-anchored probability (empirical, not simulated)
# --------------------------------------------------------------------------- #
def cone(bars):
    c = bars[-1]["c"]
    atr = atr_series(bars)
    atr_now = atr[-1] if atr else None
    fr = fwd_returns(bars, FWD_BARS)
    if not fr or atr_now is None:
        return None
    mu = sum(fr) / len(fr)
    sd = math.sqrt(sum((x - mu) ** 2 for x in fr) / len(fr))
    # empirical P(bull/base/bear) over the 5-bar forward-return distribution
    bull = sum(1 for x in fr if x > 0.5 * sd) / len(fr)
    bear = sum(1 for x in fr if x < -0.5 * sd) / len(fr)
    base = 1.0 - bull - bear
    up = c * (1 + sd)          # 1-sigma up cone
    dn = c * (1 - sd)          # 1-sigma down cone
    atr_pct = atr_now / c * 100
    return {
        "sigma_5d": round(sd * 100, 2),
        "bull": round(bull * 100, 1),
        "base": round(base * 100, 1),
        "bear": round(bear * 100, 1),
        "up": round(up, 4),
        "down": round(dn, 4),
        "atr": round(atr_now, 4),
        "atr_pct": round(atr_pct, 2),
        "horizon_bars": FWD_BARS,
    }

# --------------------------------------------------------------------------- #
# Trade levels (structure-anchored, honest R:R — NOT a fixed 2.1)
# --------------------------------------------------------------------------- #
def trade_levels(bars, k, cons):
    """Structure-anchored levels with an HONEST R:R (varies per name).

    LONG: stop = nearest swing low below close, target = nearest swing high above.
    Clamped to sane ATR multiples. If the structure yields R:R < 1.0, the name is
    downgraded to HOLD — that is the funnel working, not a fake number.
    """
    c = bars[-1]["c"]
    atr = atr_series(bars)
    atr_now = atr[-1] if atr else None
    entry = c
    stop = target = None

    if cons >= 0.60:                      # LONG
        direction = "LONG"
        # stop: nearest swing low, but never tighter than 1 ATR (noise guard)
        if k["support"] and k["support"] < c:
            stop = min(k["support"], c - atr_now) if atr_now else k["support"]
        else:
            stop = c - atr_now if atr_now else None
        # target: nearest swing high, capped at 3 ATR, floored at 1 ATR
        if k["resistance"] and k["resistance"] > c:
            target = min(k["resistance"], c + 3.0 * atr_now) if atr_now else k["resistance"]
        else:
            target = c + 2.0 * atr_now if atr_now else None
        if atr_now and target and target < c + atr_now:
            target = c + atr_now
    elif cons <= 0.40:                    # SHORT
        direction = "SHORT"
        if k["resistance"] and k["resistance"] > c:
            stop = max(k["resistance"], c + atr_now) if atr_now else k["resistance"]
        else:
            stop = c + atr_now if atr_now else None
        if k["support"] and k["support"] < c:
            target = max(k["support"], c - 3.0 * atr_now) if atr_now else k["support"]
        else:
            target = c - 2.0 * atr_now if atr_now else None
        if atr_now and target and target > c - atr_now:
            target = c - atr_now
    else:
        direction = "HOLD"

    rr = None
    if direction in ("LONG", "SHORT") and stop and target:
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr = round(reward / risk, 2) if risk > 0 else None
        # inversion guard + quality guard
        if direction == "LONG" and (stop >= entry or target <= entry):
            direction, rr = "HOLD", None
        elif direction == "SHORT" and (stop <= entry or target >= entry):
            direction, rr = "HOLD", None
        elif rr is not None and rr < 1.0:
            direction, rr = "HOLD", None   # poor structure -> no trade

    return {"direction": direction, "entry": entry, "stop": stop, "target": target, "rr": rr}

# --------------------------------------------------------------------------- #
# Analyze all symbols
# --------------------------------------------------------------------------- #
def conviction(cons, k):
    # conviction = consensus-driven, small structure kicker
    kicker = 0
    if k["trend"] == "up":
        kicker += 4
    elif k["trend"] == "down":
        kicker -= 4
    if k["mss"] == "bullish":
        kicker += 4
    elif k["mss"] == "bearish":
        kicker -= 4
    return round(max(0, min(100, cons * 100 + kicker)))

def analyze(raw):
    results = []
    for key, rec in raw.items():
        bars = rec["bars"]
        if not bars or len(bars) < 60:
            continue
        k = kronos(bars)
        mf = mirofish(bars, k)
        cn = cone(bars)
        cons = mf["consensus"]
        tl = trade_levels(bars, k, cons)
        prev_close = bars[-2]["c"] if len(bars) >= 2 else bars[-1]["c"]
        chg = (bars[-1]["c"] / prev_close - 1) * 100
        results.append({
            "symbol": key,
            "yahoo": rec["yahoo_symbol"],
            "currency": rec["meta"].get("currency", ""),
            "last": bars[-1]["c"],
            "chg_pct": round(chg, 2),
            "kronos": k,
            "mirofish": mf,
            "cone": cn,
            "trade": tl,
            "conviction": conviction(cons, k),
            "n_bars": len(bars),
        })
    # rank by conviction desc, but HOLD/direction-invalid names sink
    # rank: tradeable setups first (conviction desc), then no-trade names (conviction desc)
    results.sort(key=lambda r: (0 if r["trade"]["direction"] != "HOLD" else 1, -r["conviction"]))
    return results

def backtest(raw):
    """Walk-forward: at each bar (>=60 history), compute the ensemble's directional
    call, then measure the forward FWD_BARS return.  Aggregates hit rate across the
    universe — the honest replacement for the dashboard's unsourced 'walk-forward 61%'."""
    hits = calls = 0
    per_symbol = {}
    for key, rec in raw.items():
        bars = rec["bars"]
        sh = sc = 0
        closes = [b["c"] for b in bars]
        for i in range(60, len(bars) - FWD_BARS):
            window = bars[: i + 1]
            k = kronos(window)
            mf = mirofish(window, k)
            cons = mf["consensus"]
            if cons < 0.60 and cons > 0.40:
                continue                       # no directional call
            fwd = closes[i + FWD_BARS] / closes[i] - 1
            call = "bull" if cons >= 0.60 else "bear"
            hit = (call == "bull" and fwd > 0) or (call == "bear" and fwd < 0)
            sc += 1
            sh += 1 if hit else 0
        per_symbol[key] = {"calls": sc, "hits": sh, "hit_rate": round(sh / sc, 3) if sc else None}
        hits += sh
        calls += sc
    return {
        "universe_hit_rate": round(hits / calls, 3) if calls else None,
        "total_calls": calls,
        "per_symbol": per_symbol,
        "horizon_bars": FWD_BARS,
    }

def main():
    with open("/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json") as f:
        raw = json.load(f)
    results = analyze(raw)
    bt = backtest(raw)
    with open("/Users/snipertrader/snipertrader/teardown/results.json", "w") as f:
        json.dump({"results": results, "backtest": bt, "as_of": "see raw_ohlcv meta.regularMarketTime"}, f, indent=2)
    # print a compact audit
    for r in results:
        mf = r["mirofish"]
        tl = r["trade"]
        cn = r["cone"] or {}
        print(f"{r['symbol']:10s} {r['last']:>12.4f} {r['chg_pct']:+6.2f}%  conv={r['conviction']:3d}  "
              f"{tl['direction']:5s} rr={tl['rr']}  swarm={mf['consensus_pct']:5.1f}%  "
              f"cone B/B/B={cn.get('bull')}/{cn.get('base')}/{cn.get('bear')}  trend={r['kronos']['trend']}")
    print(f"\nBACKTEST (walk-forward, {bt['horizon_bars']}-bar horizon): "
          f"hit_rate={bt['universe_hit_rate']} over {bt['total_calls']} calls")

if __name__ == "__main__":
    main()
