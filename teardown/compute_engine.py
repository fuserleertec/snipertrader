#!/usr/bin/env python3
"""
Real signal engine for the SniperTrader terminal redesign.

Every number here is a deterministic function of real OHLCV (Yahoo, key-less).
No Monte-Carlo-over-nothing, no random swarm votes.

Three engines:
  1. KRONOS  — structural detection from the actual k-lines:
     anchored VWAP, Fair Value Gaps, order blocks, liquidity sweeps,
     Market Structure Shift, trend structure.
  2. MIROFISH — an ensemble of 7 de-correlated deterministic technical models,
     each casting a traceable Bull/Neutral/Bear vote with a confidence equal to
     its z-scored signal strength (no hand-tuned divisors).  The "swarm" is the
     honest aggregate of those real votes (NOT random).
  3. CONE    — volatility-anchored probability, CONDITIONAL on the signal: the
     historical distribution of forward returns when the ensemble made the SAME
     call (bull/bear/neutral) -> P(bull/base/bear). Not a simulated Monte-Carlo.

Outputs results.json consumed by the HTML prototype.
"""
import json
import math
from bisect import bisect_right

ATR_N = 14
VWAP_N = 20
PIVOT_K = 3
FWD_BARS = 5
MOM_WINDOW = 120   # cross-sectional momentum lookback (daily bars ≈ 6 months)
MOM_SKIP = 20      # skip the most recent month (Jegadeesh-Titman momentum convention)
MIN_OBS = 30       # minimum conditional observations before we trust a signal-conditioned bucket

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
# Cross-sectional momentum — relative strength vs the universe
# --------------------------------------------------------------------------- #
def _median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def cross_sectional(raw, window=20, skip=0):
    """Precompute point-in-time cross-sectional momentum statistics.

    For each symbol, the rate-of-change from `i-window` to `i-skip` at every bar
    (i >= window), keyed by that bar's timestamp.  `skip` = most recent bars to
    exclude (momentum-factor convention: skip the last month to avoid short-term
    reversal; default 0 = plain ROC).  For every unique timestamp across the
    whole universe, the cross-sectional median + MAD of the LATEST known signal
    per symbol (no lookahead).  Returns:
      roc_series: {sym: [(t, signal), ...]}
      stats:      {t: (median, mad)}
    """
    roc_series = {}
    all_t = set()
    for sym, rec in raw.items():
        bars = rec["bars"]
        closes = [b["c"] for b in bars]
        ts = [b["t"] for b in bars]
        ser = []
        for i in range(window, len(bars)):
            ser.append((ts[i], closes[i - skip] / closes[i - window] - 1.0))
            all_t.add(ts[i])
        roc_series[sym] = ser
    times = sorted(all_t)
    t_lists = {sym: [x[0] for x in ser] for sym, ser in roc_series.items()}
    r_lists = {sym: [x[1] for x in ser] for sym, ser in roc_series.items()}
    stats = {}
    for t in times:
        rocs = []
        for sym in roc_series:
            i = bisect_right(t_lists[sym], t) - 1
            if i >= 0:
                rocs.append(r_lists[sym][i])
        med = _median(rocs)
        stats[t] = (med, _median([abs(r - med) for r in rocs]))
    return roc_series, stats

# --------------------------------------------------------------------------- #
# KRONOS — structural detection
# --------------------------------------------------------------------------- #
def structure(bars):
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
    # Nearest structural levels (nearest swing low below / high above price).
    # null (NOT a 20-bar fallback) when price is at/through the extreme — an
    # honest "no level" instead of a fabricated one.
    piv_lows = sorted(p[2] for p in piv_l)
    piv_highs = sorted(p[2] for p in piv_h)
    below = [x for x in piv_lows if x < c]
    above = [x for x in piv_highs if x > c]
    support = max(below) if below else None
    resistance = min(above) if above else None

    return {
        "close": c,
        "vwap": round(vwap, 4) if vwap else None,
        "vwap_pct": round((c / vwap - 1) * 100, 2) if vwap else None,
        "trend": trend,
        "mss": mss,
        "fvg": fvg,
        "order_block": ob,
        "sweep": sweep,
        "support": round(support, 4) if support is not None else None,
        "resistance": round(resistance, 4) if resistance is not None else None,
    }

# --------------------------------------------------------------------------- #
# MIROFISH — 8 deterministic agents (real votes, traceable)
# --------------------------------------------------------------------------- #
def _zlast(vals):
    """Population z-score of the LAST value vs the series (0 if too short/flat)."""
    if not vals or len(vals) < 8:
        return 0.0
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))
    return (vals[-1] - m) / sd if sd > 1e-12 else 0.0


def ensemble(bars, k, u=None):
    """7 de-correlated agents, each casting one Bull/Neutral/Bear vote with a
    confidence = clamp(|signal strength|, 0, 1).  Strengths are z-scored against
    the symbol's own history or the cross-section (no hand-tuned divisors), so
    the votes are comparable and the ensemble is no longer four echo copies of
    one trend read.  Trend, Rel Momentum (cross-sectional relative strength),
    Mean Rev, Vol Regime, Volume, Key Level (ATR-distance), Structure (MSS+sweep).

    `u` = optional cross-sectional context {"cs_median": float, "cs_mad": float}
    for the Rel Momentum agent (point-in-time, supplied by the caller)."""
    closes = [b["c"] for b in bars]
    n = len(closes)
    c = closes[-1]
    A = []

    def push(name, strength, why):
        sig = "bull" if strength > 0.4 else ("bear" if strength < -0.4 else "neutral")
        conf = round(max(0.0, min(1.0, abs(strength))), 3)
        A.append({"name": name, "signal": sig, "confidence": conf, "why": why})

    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    e12, e26 = ema12[-1], ema26[-1]
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200) if n >= 200 else sma(closes, n)
    atr = atr_series(bars)
    atr_now = atr[-1] if atr else None
    atr_vals = [a for a in atr if a is not None] if atr else []
    rsi = rsi_series(bars)
    rsi_now = rsi[-1] if rsi else None
    obv = obv_series(bars)
    obv_slope = (obv[-1] - obv[-10]) / (obv[-10] or 1) if len(obv) >= 10 else 0.0

    # 1) Trend — EMA12/26 + SMA50/200 stack (the single trend read)
    stack = 0
    if sma50 and sma200:
        if c > sma50 and sma50 > sma200:
            stack = 1
        elif c < sma50 and sma50 < sma200:
            stack = -1
    t_dir = (1 if e12 > e26 else -1) + stack          # int in [-2, 2]
    push("Trend", t_dir,
         f"EMA12/26 {'above' if e12 > e26 else 'below'}"
         + (f", SMA50 {'>' if sma50 > sma200 else '<'} SMA200" if (sma50 and sma200) else ""))

    # 2) Rel Momentum — cross-sectional relative strength (vs the universe).
    #    120d lookback, skip 20d (~1mo) — the Jegadeesh-Titman momentum convention,
    #    which the factor backtest showed is where edge (if any) lives.
    if n >= MOM_WINDOW + 1:
        mom = closes[-1 - MOM_SKIP] / closes[-1 - MOM_WINDOW] - 1.0
        if u and u.get("cs_mad") is not None:
            denom = 1.4826 * u["cs_mad"]
            rel = (mom - u["cs_median"]) / denom if denom > 1e-12 else 0.0
            push("Rel Momentum", rel, f"{MOM_WINDOW}d momentum (skip {MOM_SKIP}d) {mom * 100:+.1f}% vs universe z {rel:+.1f}")
        else:
            moms = [closes[i - MOM_SKIP] / closes[i - MOM_WINDOW] - 1 for i in range(MOM_WINDOW, n)]
            z = _zlast(moms)
            push("Rel Momentum", z, f"{MOM_WINDOW}d momentum z {z:+.1f}")
    else:
        push("Rel Momentum", 0.0, "insufficient bars")

    # 3) Mean Rev — Bollinger z (contrarian)
    bbz = _zlast(closes[-20:]) if n >= 20 else 0.0
    push("Mean Rev", -bbz, f"BB z {bbz:+.1f}" + (f", RSI {rsi_now:.0f}" if rsi_now is not None else ""))

    # 4) Vol Regime — ATR percentile (low-vol continuation tilt, high-vol caution)
    if atr_now is not None and atr_vals:
        pct = sum(1 for v in atr_vals if v <= atr_now) / len(atr_vals)
        push("Vol Regime", (0.5 - pct) * 2.0, f"ATR {pct * 100:.0f}th pct")
    else:
        push("Vol Regime", 0.0, "no ATR")

    # 5) Volume — OBV 10-bar slope, z-scored
    if len(obv) >= 18:
        slopes = [(obv[i] - obv[i - 10]) / (obv[i - 10] or 1) for i in range(10, len(obv))]
        push("Volume", _zlast(slopes), f"OBV 10-bar slope {obv_slope:+.3f}")
    else:
        push("Volume", 0.0, "insufficient bars")

    # 6) Key Level — ATR-distance to nearest support/resistance (one-sided OK)
    if atr_now and atr_now > 0 and (k["support"] is not None or k["resistance"] is not None):
        d_sup = (c - k["support"]) / atr_now if k["support"] is not None else float("inf")
        d_res = (k["resistance"] - c) / atr_now if k["resistance"] is not None else float("inf")
        near = min(d_sup, d_res)
        kl = 0.0
        if near <= 2.0:
            kl = (1.0 - near / 2.0) * (1 if d_sup < d_res else -1)
        push("Key Level", kl, f"{near:.1f} ATR to S/R")
    else:
        push("Key Level", 0.0, "no level")

    # 7) Structure — MSS + sweep (break/run, NOT trend which is agent #1)
    st = 0.0
    if k["mss"] == "bullish":
        st += 1.0
    elif k["mss"] == "bearish":
        st -= 1.0
    if k["sweep"] and k["sweep"]["dir"] == "bull":
        st += 0.5
    elif k["sweep"] and k["sweep"]["dir"] == "bear":
        st -= 0.5
    push("Structure", st, f"break={k['mss']} sweep={k['sweep']['dir'] if k['sweep'] else '—'}")

    # Consensus: confidence-weighted, with a uniform prior so a finite ensemble
    # never reads a fake 0% or 100%.  (NEU casts no directional vote.)
    bull = sum(a["confidence"] for a in A if a["signal"] == "bull")
    bear = sum(a["confidence"] for a in A if a["signal"] == "bear")
    n_bull = sum(1 for a in A if a["signal"] == "bull" and a["confidence"] > 0.05)
    n_bear = sum(1 for a in A if a["signal"] == "bear" and a["confidence"] > 0.05)
    n_neu = len(A) - n_bull - n_bear
    consensus = round((bull + 0.5) / (bull + bear + 1.0), 3)
    return {"agents": A, "bull": round(bull, 3), "bear": round(bear, 3),
            "n_bull": n_bull, "n_bear": n_bear, "n_neu": n_neu,
            "consensus": consensus, "consensus_pct": round(consensus * 100, 1)}

# --------------------------------------------------------------------------- #
# CONE — volatility-anchored probability (empirical, not simulated)
# --------------------------------------------------------------------------- #
def _bucket_key(cons):
    """The directional call the terminal makes — the SAME conditioning the
    backtest uses, so the cone and the backtest tell one story."""
    return "bull" if cons >= 0.60 else ("bear" if cons <= 0.40 else "neutral")


def _condense(rs):
    """Summarize a bucket of forward returns into {n, bull, base, bear, sigma}.
    bull/base/bear use the bucket's own half-sigma threshold (a 'notable move')."""
    n = len(rs)
    if n == 0:
        return {"n": 0, "bull": None, "base": None, "bear": None, "sigma": None}
    mu = sum(rs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in rs) / n)
    bull = sum(1 for x in rs if x > 0.5 * sd) / n
    bear = sum(1 for x in rs if x < -0.5 * sd) / n
    base = 1.0 - bull - bear
    return {"n": n, "bull": round(bull * 100, 1), "base": round(base * 100, 1),
            "bear": round(bear * 100, 1), "sigma": round(sd * 100, 2)}


def cone(bars, bucket, per_sym=None, pooled=None):
    """Volatility-anchored probability cone, CONDITIONAL on the signal.

    Replaces the unconditional base rate ('did price rise over 5 bars?') with the
    decision-relevant question: 'when the ensemble made THIS SAME call historically,
    what happened?'.  Resolution order: this symbol's own bucket -> the universe-wide
    bucket -> the symbol's unconditional base rate (all point-in-time, no lookahead).
    `per_sym`/`pooled` are the condensed {n,bull,base,bear,sigma} maps from
    _walk_forward.  The +/-1 sigma price band stays name-specific (the symbol's own
    5-bar volatility) so the cone price still tracks the name.
    """
    c = bars[-1]["c"]
    atr = atr_series(bars)
    atr_now = atr[-1] if atr else None
    if atr_now is None:
        return None
    fr_all = fwd_returns(bars, FWD_BARS)
    if not fr_all:
        return None
    mu_all = sum(fr_all) / len(fr_all)
    sd_all = math.sqrt(sum((x - mu_all) ** 2 for x in fr_all) / len(fr_all))

    stats, scope = None, "unconditional"
    if per_sym is not None and per_sym.get(bucket) and per_sym[bucket]["n"] >= MIN_OBS:
        stats, scope = per_sym[bucket], "symbol"
    elif pooled is not None and pooled.get(bucket) and pooled[bucket]["n"] >= MIN_OBS:
        stats, scope = pooled[bucket], "universe"

    if stats is None:
        bull = sum(1 for x in fr_all if x > 0.5 * sd_all) / len(fr_all)
        bear = sum(1 for x in fr_all if x < -0.5 * sd_all) / len(fr_all)
        base = 1.0 - bull - bear
        n = len(fr_all)
        bull, base, bear = round(bull * 100, 1), round(base * 100, 1), round(bear * 100, 1)
    else:
        bull, base, bear = stats["bull"], stats["base"], stats["bear"]
        n = stats["n"]

    up = c * (1 + sd_all)          # 1-sigma up cone (name-specific volatility)
    dn = c * (1 - sd_all)          # 1-sigma down cone
    atr_pct = atr_now / c * 100
    return {
        "sigma_5d": round(sd_all * 100, 2),
        "bull": bull,
        "base": base,
        "bear": bear,
        "up": round(up, 4),
        "down": round(dn, 4),
        "atr": round(atr_now, 4),
        "atr_pct": round(atr_pct, 2),
        "horizon_bars": FWD_BARS,
        "n": n,
        "scope": scope,
        "bucket": bucket,
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
def conviction(cone, trade):
    """Conviction = the empirical conditional EDGE of this setup (0-100, 50 = no edge).

    Not trend strength.  It answers 'how often did this same call historically resolve
    in the called direction vs against', from the signal-conditioned cone: p_win =
    P(notable move in the called direction), p_loss = P(notable move against), and
    conviction = 50 + (p_win - p_loss)/2.  HOLD (no directional call) -> 50.  Half-up
    to match JS Math.round."""
    d = trade["direction"]
    if d == "HOLD" or cone is None:
        return 50
    if d == "LONG":
        p_win, p_loss = cone["bull"], cone["bear"]
    else:  # SHORT
        p_win, p_loss = cone["bear"], cone["bull"]
    return int(50 + (p_win - p_loss) / 2.0 + 0.5)

def analyze(raw, cond=None):
    roc_series, _ = cross_sectional(raw, window=MOM_WINDOW, skip=MOM_SKIP)
    latest_rocs = [ser[-1][1] for ser in roc_series.values() if ser]
    med = _median(latest_rocs)
    mad = _median([abs(r - med) for r in latest_rocs])
    u = {"cs_median": med, "cs_mad": mad}
    if cond is None:
        cond = _walk_forward(raw)["cond"]
    per_sym = cond["per_symbol"]
    pooled = cond["pooled"]
    results = []
    for key, rec in raw.items():
        bars = rec["bars"]
        if not bars or len(bars) < 60:
            continue
        k = structure(bars)
        mf = ensemble(bars, k, u)
        cn = cone(bars, _bucket_key(mf["consensus"]), per_sym.get(key), pooled)
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
            "structure": k,
            "ensemble": mf,
            "cone": cn,
            "trade": tl,
            "conviction": conviction(cn, tl),
            "n_bars": len(bars),
        })
    # rank by conviction desc, but HOLD/direction-invalid names sink
    # rank: tradeable setups first (conviction desc), then no-trade names (conviction desc)
    results.sort(key=lambda r: (0 if r["trade"]["direction"] != "HOLD" else 1, -r["conviction"]))
    return results

def _walk_forward(raw):
    """Single walk-forward pass: at each bar (>=60 history), score the ensemble
    (point-in-time cross-section, no lookahead), then record the forward FWD_BARS
    return.  Returns BOTH the naive hit-rate backtest AND the signal-conditioned
    forward-return buckets for the probability cone — one pass, so the two always agree.
    """
    roc_series, stats = cross_sectional(raw, window=MOM_WINDOW, skip=MOM_SKIP)
    hits = calls = 0
    per_symbol = {}
    buckets_per_sym = {}
    pooled = {"bull": [], "bear": [], "neutral": []}
    for key, rec in raw.items():
        bars = rec["bars"]
        closes = [b["c"] for b in bars]
        sh = sc = 0
        buckets = {"bull": [], "bear": [], "neutral": []}
        for i in range(60, len(bars) - FWD_BARS):
            window = bars[: i + 1]
            med, mad = stats.get(bars[i]["t"], (0.0, 0.0))
            k = structure(window)
            mf = ensemble(window, k, {"cs_median": med, "cs_mad": mad})
            cons = mf["consensus"]
            fwd = closes[i + FWD_BARS] / closes[i] - 1.0
            b = _bucket_key(cons)
            buckets[b].append(fwd)
            pooled[b].append(fwd)
            if 0.40 < cons < 0.60:
                continue                       # no directional call
            call = "bull" if cons >= 0.60 else "bear"
            hit = (call == "bull" and fwd > 0) or (call == "bear" and fwd < 0)
            sc += 1
            sh += 1 if hit else 0
        per_symbol[key] = {"calls": sc, "hits": sh, "hit_rate": round(sh / sc, 3) if sc else None}
        buckets_per_sym[key] = {b: _condense(v) for b, v in buckets.items()}
        hits += sh
        calls += sc
    return {
        "hit": {
            "universe_hit_rate": round(hits / calls, 3) if calls else None,
            "total_calls": calls,
            "per_symbol": per_symbol,
            "horizon_bars": FWD_BARS,
        },
        "cond": {
            "per_symbol": buckets_per_sym,
            "pooled": {b: _condense(v) for b, v in pooled.items()},
        },
    }


def backtest(raw):
    """Naive walk-forward hit-rate backtest (kept for make_backtest_summary)."""
    return _walk_forward(raw)["hit"]

def main():
    with open("/Users/snipertrader/snipertrader/teardown/raw_ohlcv.json") as f:
        raw = json.load(f)
    wf = _walk_forward(raw)
    results = analyze(raw, cond=wf["cond"])
    bt = wf["hit"]
    with open("/Users/snipertrader/snipertrader/teardown/results.json", "w") as f:
        json.dump({"results": results, "backtest": bt, "conditional": wf["cond"],
                   "as_of": "see raw_ohlcv meta.regularMarketTime"}, f, indent=2)
    # print a compact audit
    for r in results:
        mf = r["ensemble"]
        tl = r["trade"]
        cn = r["cone"] or {}
        print(f"{r['symbol']:10s} {r['last']:>12.4f} {r['chg_pct']:+6.2f}%  conv={r['conviction']:3d}  "
              f"{tl['direction']:5s} rr={tl['rr']}  cons={mf['consensus_pct']:5.1f}%  "
              f"cone B/B/B={cn.get('bull')}/{cn.get('base')}/{cn.get('bear')}  trend={r['structure']['trend']}")
    print(f"\nBACKTEST (walk-forward, {bt['horizon_bars']}-bar horizon): "
          f"hit_rate={bt['universe_hit_rate']} over {bt['total_calls']} calls")

if __name__ == "__main__":
    main()
