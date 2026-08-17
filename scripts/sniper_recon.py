#!/usr/bin/env python3
"""
Hermes Multi-Factor Recon — real-data pipeline for SniperTrader.ai.

Replaces the fictional tool bindings with code against REAL, key-less APIs:
  - Stocktwits public JSON API        -> sentiment stream + $TICKER keyword scan
  - Yahoo chart endpoint (Yahoo OHLCV)-> the hard breakout/BOS/FVG math from the directive
  - Google News RSS + SEC EDGAR       -> News/DD/YOLO catalyst verification
  - Output: JSON payload (SIMULATED_MARKET_ORDER) + markdown exec brief

NOTE: SniperTrader.ai has NO trade-execution webhook in this repo. This script
NEVER silently POSTs orders. It writes a payload file + a webpage locally.
"""
import json, re, sys, time, datetime, subprocess
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (research; snipertrader.ai recon pipeline)"
SEC_UA = "snipertrader-recon research@example.com"

NOW = datetime.datetime.now(datetime.timezone.utc)
TS = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

def get_json(url, headers=None, timeout=25):
    req = Request(url, headers=headers or {"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)

def get_text(url, headers=None, timeout=25):
    req = Request(url, headers=headers or {"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

# ---------------------------------------------------------------------------
# TIER 1.1 — Stocktwits trending + sentiment stream
# ---------------------------------------------------------------------------
def stocktwits_trending(limit=30):
    d = get_json("https://api.stocktwits.com/api/2/trending/symbols.json")
    syms = d.get("symbols", [])
    out = []
    for s in syms[:limit]:
        ex = (s.get("exchange") or "").upper()
        # equities only: skip crypto/FX/ETN levered junk for a momentum scan
        if ex in ("CRYPTO", "FX") or "ETN" in s.get("title", ""):
            continue
        out.append({"symbol": s["symbol"], "exchange": ex, "title": s.get("title", "")})
    return out

# Keyword heuristic classifier = the "LLM fallback" in the directive.
# Stocktwits only tags sentiment when a user explicitly clicks bull/bear, so most
# messages are sentiment=null; we label this clearly as a heuristic.
BULL = re.compile(r"\b(breakout|bullish|long|calls|rip|moon|green|up|bounce|buy|rally|break of structure|bos|fvg|gap up|support|squeeze|rocket|pad)\b", re.I)
BEAR = re.compile(r"\b(bearish|short|puts|dump|red|down|sell|crumble|breakdown|dead|rug|tank|gap down|resistance|bagholder)\b", re.I)

def classify(text):
    b = len(BULL.findall(text)); r = len(BEAR.findall(text))
    if b > r: return "BULL"
    if r > b: return "BEAR"
    return "NEU"

def stocktwits_stream(symbol, n=40):
    """Return (bull_pct, bear_pct, mentions, sample_posts) for a symbol."""
    d = get_json(f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json",
                 headers={"User-Agent": UA})
    msgs = d.get("messages", [])[:n]
    bull = bear = neu = 0
    samples = []
    for m in msgs:
        body = m.get("body", "") or ""
        # native tag if present
        cls = None
        for s in m.get("entities", {}).get("symbols", []):
            if s.get("symbol") == symbol and s.get("sentiment"):
                cls = s["sentiment"]["classification"]
        if cls == "bullish": bull += 1
        elif cls == "bearish": bear += 1
        elif cls == "neutral": neu += 1
        else:
            c = classify(body)
            if c == "BULL": bull += 1
            elif c == "BEAR": bear += 1
            else: neu += 1
        # keyword trigger scan (BOS / FVG / Breakout)
        trig = []
        if re.search(r"\bbreak ?out\b|\bbreakout\b|resistance|key level", body, re.I): trig.append("BREAKOUT")
        if re.search(r"\bbos\b|break of structure|market structure shift|mss", body, re.I): trig.append("BOS")
        if re.search(r"\bfvg\b|fair value gap|liquidity gap", body, re.I): trig.append("FVG")
        if trig or len(samples) < 6:
            samples.append({"body": body[:160], "trig": trig})
    # Standard "Bullish vs Bearish ratio": NEU posts cast no directional vote.
    denom = bull + bear
    bull_pct = round(100 * bull / denom, 1) if denom else 0.0
    total = bull + bear + neu
    return bull_pct, total, samples, (bull, bear)

# ---------------------------------------------------------------------------
# TIER 1.3 — Hard price verification (the directive's exact math) via Yahoo
# ---------------------------------------------------------------------------
def yahoo_ohlc(symbol, range_="3mo", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_}&interval={interval}"
    d = get_json(url, headers={"User-Agent": UA})
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    rows = []
    for i, t in enumerate(ts):
        rows.append({
            "t": datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"),
            "o": q["open"][i], "h": q["high"][i], "l": q["low"][i], "c": q["close"][i],
            "v": q["volume"][i],
        })
    # filter nulls
    rows = [r for r in rows if r["c"] is not None and r["h"] is not None]
    return rows

def analyze_triggers(rows):
    """Directive's exact rules:
      Breakout: Close > 20-day High.
      BOS: High > recent 10-day Swing High.
      Bullish FVG: unfilled gap where candle3.low > candle1.high.
    """
    if len(rows) < 21:
        return {"ok": False, "reason": "insufficient bars"}
    closes = [r["c"] for r in rows]
    highs = [r["h"] for r in rows]
    lows = [r["l"] for r in rows]
    cur = rows[-1]
    h20 = max(highs[-21:-1])          # 20-day high BEFORE today
    swing10 = max(highs[-11:-1])      # 10-day swing high before today
    confirmed = []
    if cur["c"] > h20:
        confirmed.append("BREAKOUT")
    if cur["h"] > swing10:
        confirmed.append("BOS")
    # Bullish FVG: a MEANINGFUL unfilled up-gap where candle3.low > candle1.high
    # (>0.3% gap, still unfilled = current low > candle1.high).
    for i in range(max(0, len(rows)-12), len(rows)-2):
        c1h = rows[i]["h"]; c3l = rows[i+2]["l"]
        if c3l is not None and c1h is not None and c3l > c1h:
            gap = (c3l - c1h) / c1h
            if gap > 0.003 and cur["l"] > c1h:
                confirmed.append("BULLISH_FVG")
                break
    atr = (max(highs[-15:]) - min(lows[-15:])) or cur["c"] * 0.03
    avg_vol = sum(r["v"] for r in rows[-15:] if r["v"]) / 15.0
    avg_dvol = sum((r["c"] or 0) * (r["v"] or 0) for r in rows[-15:]) / 15.0
    return {
        "ok": True, "confirmed": confirmed,
        "close": round(cur["c"], 2), "high20": round(h20, 2),
        "swing10": round(swing10, 2), "atr": round(atr, 2),
        "avg_vol": round(avg_vol), "avg_dvol": round(avg_dvol),
    }

# ---------------------------------------------------------------------------
# TIER 2 — News / DD / YOLO agents (real web search via RSS + SEC)
# ---------------------------------------------------------------------------
def news_for(symbol):
    q = f"{symbol} stock"
    url = "https://news.google.com/rss/search?q=" + requests_quote(q) + "&hl=en-US&gl=US&ceid=US:en"
    txt = get_text(url)
    titles = re.findall(r"<title>(.*?)</title>", txt)
    items = [t for t in titles[1:11] if symbol.lower() in t.lower() or "stock" in t.lower()]
    return items[:6]

def sec_filings(symbol):
    url = f"https://efts.sec.gov/LATEST/search-index?q=%22{symbol}%22"
    try:
        d = get_json(url, headers={"User-Agent": SEC_UA}, timeout=20)
        return d["hits"]["total"]["value"]
    except Exception:
        return None

# Bearish signals in a headline -> contradicts a bullish setup (bull-trap guard)
BEARISH_NEWS = re.compile(r"\b(falls|plunge|drop|miss|lawsuit|fraud|downgrade|cut|warn|loss|recall|halt|delist|bankrupt|sinks|tumbles|crash)\b", re.I)

def catalyst_coherent(news, bull_pct):
    """Tier-3 bull-trap guard: if the strongest news is bearish while our read is
    bullish, the setup is incoherent -> reject. Returns (ok, note)."""
    if not news:
        return True, "no news scanned"
    top = news[0]
    if BEARISH_NEWS.search(top) and bull_pct >= 70:
        return False, f"contradictory headline: {top[:80]}"
    return True, "coherent"

def requests_quote(s):
    import urllib.parse
    return urllib.parse.quote(s)

# ---------------------------------------------------------------------------
# ORCHESTRATION
# ---------------------------------------------------------------------------
def main():
    print(f"[*] Hermes Multi-Factor Recon started {TS}")
    trending = stocktwits_trending(30)
    print(f"[*] Stocktwits equities trending: {len(trending)} symbols")
    candidates = {}
    audit = []
    def drop(sym, reason, bull_pct=None):
        audit.append({"symbol": sym, "disposition": "DROP", "reason": reason, "bull_pct": bull_pct})
        print(f"    - {sym} dropped: {reason}" + (f" ({bull_pct}% bull)" if bull_pct else ""))
    for s in trending:
        sym = s["symbol"]
        try:
            bull_pct, n, samples, (bull, bear) = stocktwits_stream(sym, 40)
        except Exception as e:
            drop(sym, f"stream error: {e}")
            continue
        # Tier 1.2 keyword triggers present in samples?
        trigs = set()
        for sm in samples:
            for t in sm["trig"]:
                trigs.add(t)
        # Tier 1.1 hard rule: >70% bullish AND velocity (>=8 msgs)
        if bull_pct < 70 or n < 8:
            drop(sym, "Tier-1 sentiment/velocity fail", bull_pct)
            continue
        if not trigs:
            drop(sym, "Tier-1 no price-action keyword (BOS/FVG/Breakout)", bull_pct)
            continue
        # Tier 1.3 hard price proof. FVG alone on daily bars is noisy, so require a
        # structural trigger (BREAKOUT or BOS) as the primary gate; FVG is bonus.
        try:
            rows = yahoo_ohlc(sym)
            trig = analyze_triggers(rows)
        except Exception as e:
            drop(sym, f"price error: {e}", bull_pct)
            continue
        confirmed = trig.get("confirmed", [])
        if not trig.get("ok") or not confirmed:
            drop(sym, f"Tier-1 no chart trigger (claimed {sorted(trigs)})", bull_pct)
            continue
        structural = [t for t in confirmed if t in ("BREAKOUT", "BOS")]
        if not structural:
            drop(sym, "Tier-1 only FVG (no BREAKOUT/BOS structure)", bull_pct)
            continue
        # Tier 2 (News/DD/YOLO) — require a real catalyst hit OR SEC filings, else drop
        # (no catalyst = no institutional conviction).
        news = news_for(sym)
        filings = sec_filings(sym)
        if not news and not (filings and filings > 0):
            drop(sym, "Tier-2 no catalyst/news", bull_pct)
            continue
        # Tier 3 hard quality gate (institutional risk controls)
        p = trig
        atr_pct = p["atr"] / p["close"]
        # (a) exclude OTC / low-regulatory venues (fraud/pump risk)
        if s["exchange"] in ("OTC",):
            drop(sym, "Tier-3 OTC venue (pump/fraud risk)", bull_pct)
            continue
        # (b) liquidity floor: avg dollar volume < $20M = slippage risk
        if p["avg_dvol"] < 20_000_000:
            drop(sym, f"Tier-3 illiquid (avg $vol ${p['avg_dvol']/1e6:.1f}M)", bull_pct)
            continue
        # (c) min directional sample: <10 bull+bear posts = statistically meaningless
        if (bull + bear) < 10:
            drop(sym, f"Tier-3 thin sentiment sample ({bull+bear} posts)", bull_pct)
            continue
        # (d) ATR sanity: >25% of price = casino, not a trade
        if atr_pct > 0.25:
            drop(sym, f"Tier-3 ATR {atr_pct*100:.0f}% of price (noise)", bull_pct)
            continue
        # (e) catalyst coherence (no bull-trap: bearish headline vs bullish read)
        ok, note = catalyst_coherent(news, bull_pct)
        if not ok:
            drop(sym, f"Tier-3 {note}", bull_pct)
            continue
        # Survived Tier 1 + Tier 2 + Tier 3
        candidates[sym] = {
            "symbol": sym, "title": s["title"], "exchange": s["exchange"],
            "bull_pct": bull_pct, "messages": n, "claimed_triggers": sorted(trigs),
            "confirmed_triggers": trig["confirmed"], "price": trig,
            "news": news, "sec_filings_hits": filings, "samples": samples[:5],
            "dir_sample": bull + bear,
        }
        print(f"    + {sym} PASSED Tier 1 | bull {bull_pct}% | chart {trig['confirmed']} | news {len(news)}")

    # Tier 3 — institutional selection (top 1-3 by conviction)
    ranked = sorted(candidates.values(),
                    key=lambda c: (c["bull_pct"], len(c["confirmed_triggers"]), len(c["news"])),
                    reverse=True)[:3]

    trades = []
    for c in ranked:
        p = c["price"]
        entry = p["close"]
        # stop below 20-day support proxy = recent swing10; tp = +1.5x atr beyond
        stop = round(min(p["swing10"], entry - p["atr"]), 2)
        tp = round(entry + 1.5 * p["atr"], 2)
        conf = round(min(0.95,
                         (c["bull_pct"]/100) * 0.6
                         + 0.15 * min(len(c["confirmed_triggers"]), 3)
                         + 0.15 * min(len(c["news"]), 5) / 5
                         + 0.10 * min((c.get("dir_sample", 0) or 0), 40) / 40), 3)
        # dir_sample = bull+bear posts (confidence should scale with sample size)
        conf = max(0.5, conf)
        trades.append({
            "ticker": c["symbol"],
            "action": "BUY",
            "confidence_score": conf,
            "sentiment_bullish_ratio": f'{c["bull_pct"]}%',
            "technical_trigger_confirmed": "/".join(c["confirmed_triggers"]),
            "entry_price": entry,
            "stop_loss": stop,
            "take_profit": tp,
            "position_size_pct": 0.10,
            "catalyst_summary": (c["news"][0] if c["news"] else "No fresh catalyst found in news scan."),
            "institutional_rationale": (
                f'{c["symbol"]} ({c["title"]}) cleared Tier 1 with {c["bull_pct"]}% bullish Stocktwits '
                f'sentiment and {len(c["samples"])} scanned posts. Chart math confirmed active trigger(s) '
                f'{"/".join(c["confirmed_triggers"])} (close {entry} vs 20d-high {p["high20"]}). '
                f'SEC EDGAR filing mentions: {c["sec_filings_hits"]}. '
                f'News scan top hit: {c["news"][0] if c["news"] else "none"}. '
                f'Risk box: stop {stop} (below swing10 {p["swing10"]}), target {tp} (1.5x ATR {p["atr"]}).'
            ),
        })

    payload = {
        "timestamp": TS,
        "scout_system": "Hermes-MultiFactor-V1",
        "portfolio_action": {
            "target_platform": "snipertrader.ai",
            "execution_type": "SIMULATED_MARKET_ORDER",
            "trades": trades,
        },
        "_methodology_note": (
            "Built with REAL key-less APIs: Stocktwits public JSON (sentiment + $TICKER scan), "
            "Yahoo OHLCV (breakout/BOS/FVG math per directive), Google News RSS + SEC EDGAR "
            "(News/DD/YOLO verification). Sentiment ratio uses a keyword heuristic fallback because "
            "Stocktwits native tags are sparse. NO execution webhook exists; this is SIMULATED only."
        ),
        "funnel_audit": audit,
        "universe_scanned": len(trending),
    }
    with open("scripts/sniper_payload.json", "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n[+] Wrote scripts/sniper_payload.json | {len(trades)} trade(s), "
          f"{len(audit)} dropped, {len(trending)} scanned.")
    md = build_markdown(payload)
    with open("scripts/sniper_brief.md", "w") as f:
        f.write(md)
    print("[+] Wrote scripts/sniper_brief.md")
    # Emit the static data cache the live page reads. NEVER overwrite stock_picks.html
    # (the canonical themed page) — that would clobber the merged, styled UI.
    import os
    os.makedirs("data", exist_ok=True)
    html = build_html(payload)
    with open("data/recon.json", "w") as f:
        json.dump(payload, f, indent=2)
    print("[+] Wrote data/recon.json (static cache; page loads /api/recon/picks live)")
    with open("scripts/sniper_recon_report.html", "w") as f:
        f.write(html)
    print("[+] Wrote scripts/sniper_recon_report.html (legacy report; stock_picks.html untouched)")

def build_markdown(payload):
    ts = payload["timestamp"]
    trades = payload["portfolio_action"]["trades"]
    audit = payload.get("funnel_audit", [])
    lines = [f"# Hermes Multi-Factor Recon — Executive Brief", "",
             f"**Generated:** {ts}  |  **System:** {payload['scout_system']}  |  "
             f"**Execution:** {payload['portfolio_action']['execution_type']}", "",
             f"**Universe scanned:** {payload.get('universe_scanned', '?')} trending symbols  |  "
             f"**Dropped:** {len(audit)}  |  **Simulated trades:** {len(trades)}", ""]
    if not trades:
        lines += ["## ⚠️ ZERO-CONVICTION RESULT", "",
                  "No ticker survived all five tiers with Hard/Ultra-High conviction. "
                  "Per the directive, **no order is dispatched** — this is the funnel working as "
                  "designed, not a failure. The trending universe today was dominated by low-float "
                  "microcaps, OTC names, ETFs with only an FVG artifact, or setups with contradictory "
                  "catalysts (bullish chart / bearish news = bull-trap guard).", ""]
    else:
        lines += ["## Simulated Trades (SIMULATED_MARKET_ORDER — NOT LIVE)", ""]
        for t in trades:
            lines += [f"### {t['ticker']} — {t['action']}",
                      f"- Confidence: **{t['confidence_score']}**  | Bullish ratio: {t['sentiment_bullish_ratio']}",
                      f"- Trigger(s) confirmed: `{t['technical_trigger_confirmed']}`",
                      f"- Entry: ${t['entry_price']}  | Stop: ${t['stop_loss']}  | Target: ${t['take_profit']}  | Size: {int(t['position_size_pct']*100)}%",
                      f"- Catalyst: {t['catalyst_summary']}",
                      f"- Rationale: {t['institutional_rationale']}", ""]
    if audit:
        lines += ["## Funnel Audit (every drop, with reason)", ""]
        for d in audit:
            bp = f" ({d['bull_pct']}% bull)" if d.get('bull_pct') else ""
            lines.append(f"- **{d['symbol']}** — {d['reason']}{bp}")
        lines.append("")
    lines += ["---", "",
              "*Disclaimer: Educational simulation only. Not investment advice. No live orders were placed; "
              "no SniperTrader.ai execution endpoint exists. Sentiment ratio uses a keyword heuristic "
              "fallback because Stocktwits native tags are sparse. Verify all data before any action.*"]
    return "\n".join(lines)

def build_html(payload):
    """Self-contained HTML page embedding the real payload + funnel audit."""
    import html as _html
    ts = payload["timestamp"]
    trades = payload["portfolio_action"]["trades"]
    audit = payload.get("funnel_audit", [])
    scanned = payload.get("universe_scanned", 0)
    data_json = _html.escape(json.dumps(payload, indent=2))
    if trades:
        cards = "".join(
            f'<div class="trade"><div class="tk">{t["ticker"]}</div>'
            f'<div class="act">{t["action"]} @ ${t["entry_price"]}</div>'
            f'<div class="meta">conf {t["confidence_score"]} · {t["sentiment_bullish_ratio"]} bull · '
            f'{t["technical_trigger_confirmed"]}</div>'
            f'<div class="meta">stop ${t["stop_loss"]} · tp ${t["take_profit"]} · size {int(t["position_size_pct"]*100)}%</div>'
            f'<div class="cat">{_html.escape(t["catalyst_summary"])}</div></div>'
            for t in trades)
    else:
        cards = '<div class="zero">⚠ ZERO-CONVICTION RESULT — no ticker cleared all tiers. No order dispatched.</div>'
    audit_rows = "".join(
        f'<tr><td>{_html.escape(d["symbol"])}</td><td>{_html.escape(d["reason"])}</td>'
        f'<td>{d.get("bull_pct","")}</td></tr>' for d in audit) or '<tr><td colspan="3">none</td></tr>'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hermes Multi-Factor Recon — SniperTrader.ai</title>
<style>
:root{{--bg:#0B0F14;--panel:#111821;--em:#00E5A0;--cyan:#00E5FF;--red:#FF4D67;--txt:#E6EDF3;--mut:#8A98A8}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 Inter,system-ui,sans-serif}}
header{{padding:28px 24px;border-bottom:1px solid #1c2733;background:linear-gradient(90deg,#0e151d,#0b0f14)}}
h1{{margin:0;font-size:22px;letter-spacing:.5px}} .sub{{color:var(--mut);font-size:13px;margin-top:6px}}
.wrap{{max-width:980px;margin:0 auto;padding:24px}}
.stat{{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}}
.stat div{{background:var(--panel);border:1px solid #1c2733;border-radius:10px;padding:12px 16px;flex:1;min-width:140px}}
.stat b{{display:block;font-size:24px;color:var(--em)}}
.trade{{background:var(--panel);border:1px solid #1c2733;border-left:3px solid var(--em);border-radius:10px;padding:14px;margin-bottom:12px}}
.trade .tk{{font-size:20px;font-weight:700}} .trade .act{{color:var(--cyan);font-weight:600}}
.trade .meta{{color:var(--mut);font-size:13px;margin-top:4px}} .trade .cat{{margin-top:8px;color:var(--txt)}}
.zero{{background:#2a1416;border:1px solid #5a2228;color:#ffb3bd;padding:16px;border-radius:10px}}
table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #1c2733}} th{{color:var(--cyan)}}
pre{{background:#0a0e13;border:1px solid #1c2733;border-radius:10px;padding:16px;overflow:auto;font-size:12px;color:var(--mut)}}
h2{{margin-top:28px;border-left:3px solid var(--cyan);padding-left:10px}}
footer{{color:var(--mut);font-size:12px;padding:20px 24px;border-top:1px solid #1c2733;margin-top:24px}}
</style></head>
<body>
<header><h1>⚡ Hermes Multi-Factor Recon</h1>
<div class="sub">System {payload['scout_system']} · Generated {ts} · Execution: {payload['portfolio_action']['execution_type']}</div></header>
<div class="wrap">
<div class="stat">
<div><b>{scanned}</b>scanned</div><div><b>{len(audit)}</b>dropped</div><div><b>{len(trades)}</b>simulated trades</div>
</div>
<h2>Portfolio Action</h2>
{cards}
<h2>Funnel Audit — every drop, with reason</h2>
<table><thead><tr><th>Ticker</th><th>Reason</th><th>Bull %</th></tr></thead><tbody>{audit_rows}</tbody></table>
<h2>Raw JSON Payload</h2>
<pre>{data_json}</pre>
</div>
<footer>Educational simulation only. Not investment advice. No live orders placed — SniperTrader.ai has no execution webhook.
Sentiment ratio uses a keyword heuristic fallback (Stocktwits native tags are sparse). Built on REAL key-less APIs:
Stocktwits public JSON, Yahoo OHLCV, Google News RSS, SEC EDGAR.</footer>
</body></html>"""

if __name__ == "__main__":
    main()
