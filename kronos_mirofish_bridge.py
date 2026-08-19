#!/usr/bin/env python3
"""
kronos_mirofish_bridge.py
=========================

LOCAL REFERENCE BRIDGE — Kronos Foundation Model  x  MiroFish Swarm Simulator.

HOW TO READ THIS FILE
---------------------
This is a *reference implementation* of the same simulation pipeline that runs
in the browser (kronos_foundation.html) and in the Node backend (api/_core.js).
It is intentionally dependency-free (standard library only) so it can run
anywhere Python 3.8+ runs — a laptop, a cron job, a notebook.

It is NOT a live trading system and NOT a trained model. Kronos forecasting
and the MiroFish agent swarm are transparent Monte-Carlo simulations. The
output JSON is *identical in shape* to what the frontend expects, so you can:

  1. Use it as a standalone CLI / batch generator of forecast payloads.
  2. Run it as a tiny local HTTP server that mimics the production endpoint
     POST /api/kronos/forecast  (with mode=full) so the frontend can talk to
     a Python process if you ever deploy a Python runtime instead of Node.

WHY PYTHON ON A NODE SITE?
--------------------------
The live snipertrader.ai site deploys Node/Vercel serverless (api/_core.js).
Python cannot be deployed there without adding a Python runtime + build step.
This script therefore serves as:
  * the canonical *spec* of the simulation math (portable, readable), and
  * a drop-in local server for development / research,
NOT as the production backend. The production backend is api/_core.js, which
mirrors this exact math.

Run:
    python3 kronos_mirofish_bridge.py --symbol BTCUSDT --bars 80 --horizon 24
    python3 kronos_mirofish_bridge.py --serve 0.0.0.0:8788     # emulate endpoint
    curl -s -X POST localhost:8788/api/kronos/forecast \
        -H 'Content-Type: application/json' \
        -d '{"mode":"full","config":{"bars":80,"horizon":24,"paths":24,"seed":2654435761}}'
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional

# ----------------------------------------------------------------------------
# RNG + STATS  (byte-for-byte parity target with the JS mulberry32 / gauss)
# ----------------------------------------------------------------------------
MASK32 = 0xFFFFFFFF


def mulberry32(a: int):
    """Deterministic PRNG matching the JS mulberry32 used in the frontend."""
    a = a & MASK32

    def rng() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & MASK32
        t = a
        t = (t ^ (t >> 15)) & MASK32
        t = t + (t << 1) & MASK32  # imul(t, 1|a) where a|0 already; simplified via imul below
        # The JS step is: t = t + Math.imul(t ^ (t >>> 7), 61 | t) ^ t
        # Reproduce imul exactly:
        x = (t ^ (t >> 7)) & MASK32
        y = (61 | t) & MASK32
        t = (t + _imul(x, y)) & MASK32
        t = (t ^ (t >> 14)) & MASK32
        return (t & MASK32) / 4294967296.0

    return rng


def _imul(a: int, b: int) -> int:
    """Emulate JavaScript Math.imul (32-bit signed multiply)."""
    a &= MASK32
    b &= MASK32
    result = (a * b) & MASK32
    if result >= 0x80000000:
        result -= 0x100000000
    return result


def gauss(rng) -> float:
    """Box-Muller, matching JS gauss() (cos branch)."""
    u = 0.0
    while u == 0.0:
        u = rng()
    v = 0.0
    while v == 0.0:
        v = rng()
    return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def quantile(sorted_arr: List[float], q: float) -> float:
    idx = min(len(sorted_arr) - 1, max(0, int(q * len(sorted_arr))))
    return sorted_arr[idx]


# ----------------------------------------------------------------------------
# KRONOS — synthetic OHLCV history + autoregressive path sampling
# ----------------------------------------------------------------------------
MAX_CTX = 512
TOK_PER_BAR = 3.0
MAX_BARS = int(MAX_CTX / TOK_PER_BAR)  # 170


def gen_history(n: int, rng) -> List[Dict[str, float]]:
    price = 100.0 + rng() * 50.0
    vbase = 1200.0 + rng() * 5000.0
    bars = []
    for _ in range(n):
        o = price
        step = (rng() - 0.5) * 0.012 + 0.0004
        c = o * (1 + step + gauss(rng) * 0.011)
        h = max(o, c) * (1 + abs(gauss(rng)) * 0.009)
        l = min(o, c) * (1 - abs(gauss(rng)) * 0.009)
        v = round(vbase * (0.7 + 0.6 * rng()))
        bars.append({"o": o, "h": h, "l": l, "c": c, "v": v})
        price = c
    return bars


def eff_vol(config: Dict[str, float]) -> float:
    vol = config.get("vol", 0.018)
    inj = config.get("volInject", 1.0)
    shock = config.get("newsShock", 0.0)
    return vol * inj * (1.0 + shock / 100.0 * 0.8)


def gen_paths(last_close: float, rng, config: Dict[str, Any]) -> List[List[float]]:
    paths = []
    v = eff_vol(config)
    for _ in range(int(config["paths"])):
        price = last_close
        path = [price]
        for _ in range(int(config["horizon"])):
            step = config["drift"] + gauss(rng) * v * config["temp"]
            price = price * (1 + step)
            path.append(price)
        paths.append(path)
    return paths


def compute_bands(paths: List[List[float]]) -> Dict[str, List[float]]:
    H = len(paths[0]) - 1
    out = {"p5": [], "p25": [], "p50": [], "p75": [], "p95": [], "spread": []}
    for t in range(1, H + 1):
        col = sorted(p[t] for p in paths)
        out["p5"].append(quantile(col, 0.05))
        out["p25"].append(quantile(col, 0.25))
        out["p50"].append(quantile(col, 0.5))
        out["p75"].append(quantile(col, 0.75))
        out["p95"].append(quantile(col, 0.95))
        out["spread"].append((col[-1] - col[0]) / col[0])
    return out


def compute_stats(last_close: float, paths: List[List[float]], bands) -> Dict[str, float]:
    end = len(bands["p50"]) - 1
    ret = (bands["p50"][end] / last_close - 1) * 100
    up = sum(1 for p in paths if p[-1] > last_close) / len(paths) * 100
    var5 = (bands["p5"][end] / last_close - 1) * 100
    mean_spread = sum(bands["spread"]) / len(bands["spread"])
    ent = math.log(1 + mean_spread * 100 * len(paths)) / math.log(1 + 100)
    return {"ret": round(ret, 2), "up": round(up, 1), "var5": round(var5, 2), "ent": round(ent, 3)}


# ----------------------------------------------------------------------------
# MIROFISH — agent swarm (SIMULATION)
# ----------------------------------------------------------------------------
SWARM_ARCHETYPES = [
    {"id": "MM",  "name": "Market Makers",     "weight": 0.30, "base": 0.50, "color": "cyan",    "volatility": 0.6},
    {"id": "SM",  "name": "Smart Money / ICT", "weight": 0.30, "base": 0.58, "color": "emerald", "volatility": 0.4},
    {"id": "RET", "name": "Retail Momentum",   "weight": 0.20, "base": 0.46, "color": "gold",    "volatility": 1.2},
    {"id": "QF",  "name": "Quant Funds",       "weight": 0.20, "base": 0.52, "color": "red",     "volatility": 0.8},
]


def compute_swarm(config: Dict[str, Any]) -> Dict[str, Any]:
    rng = mulberry32((int(config.get("seed", 0x9E3779B1)) & MASK32) ^ 0x9E37)
    swarm_bias = float(config.get("swarmBias", 0.0))
    news_shock = float(config.get("newsShock", 0.0))
    agents = []
    for a in SWARM_ARCHETYPES:
        noise = (rng() - 0.5) * 0.12 * (1 + news_shock / 120.0)
        long_bias = clamp(a["base"] + swarm_bias * 0.45 + noise, 0.02, 0.98)
        activity = clamp(0.35 + 0.4 * abs(swarm_bias) + news_shock / 200.0 + rng() * 0.2, 0, 1)
        agents.append({
            "id": a["id"], "name": a["name"], "weight": a["weight"], "color": a["color"],
            "longBias": round(long_bias, 3), "shortBias": round(1 - long_bias, 3),
            "activity": round(activity, 3), "vol": a["volatility"],
        })
    consensus_up = sum(a["weight"] * a["longBias"] for a in agents)
    return {
        "agents": agents,
        "consensusUp": round(consensus_up, 3),
        "netBias": round(consensus_up - 0.5, 3),
        "aggAct": round(sum(a["weight"] * a["activity"] for a in agents), 3),
    }


def build_confluence(bands: Dict[str, List[float]], swarm: Dict[str, Any]) -> Dict[str, List[float]]:
    F = len(bands["p50"])
    bend = swarm["netBias"] * 2 * 0.10
    tail_amp = 0.05 + float(swarm.get("newsShock", 0)) / 100.0 * 0.30
    primary, secondary, tail_risk = [], [], []
    for j in range(F):
        t = (j + 1) / F
        base = bands["p50"][j]
        primary.append(round(base * (1 + bend * t), 2))
        secondary.append(round(base * (1 - bend * 0.6 * t), 2))
        direction = -1 if swarm["netBias"] >= 0 else 1
        tail_risk.append(round(base * (1 + direction * tail_amp * t), 2))
    return {"primary": primary, "secondary": secondary, "tailRisk": tail_risk}


def detect_ict(bars: List[Dict[str, float]]) -> Dict[str, List[Any]]:
    n = len(bars)
    obs, fvgs, liq = [], [], []
    for i in range(2, n - 3):
        up = bars[i + 1]["c"] > bars[i + 1]["o"] and bars[i + 2]["c"] > bars[i + 2]["o"]
        down = bars[i + 1]["c"] < bars[i + 1]["o"] and bars[i + 2]["c"] < bars[i + 2]["o"]
        if up and bars[i]["c"] < bars[i]["o"]:
            obs.append({"type": "bull", "price": bars[i]["l"], "top": bars[i]["h"], "bot": bars[i]["l"], "idx": i})
        if down and bars[i]["c"] > bars[i]["o"]:
            obs.append({"type": "bear", "price": bars[i]["h"], "top": bars[i]["h"], "bot": bars[i]["l"], "idx": i})
    for i in range(n - 2):
        gap_bull = bars[i + 2]["l"] - bars[i]["h"]
        if gap_bull > abs(bars[i]["c"]) * 0.0015:
            fvgs.append({"type": "bull", "top": bars[i + 2]["l"], "bot": bars[i]["h"], "idx": i})
        gap_bear = bars[i]["l"] - bars[i + 2]["h"]
        if gap_bear > abs(bars[i]["c"]) * 0.0015:
            fvgs.append({"type": "bear", "top": bars[i]["l"], "bot": bars[i + 2]["h"], "idx": i})
    for i in range(2, n - 2):
        if bars[i]["h"] > bars[i - 1]["h"] and bars[i]["h"] > bars[i - 2]["h"] and bars[i]["h"] > bars[i + 1]["h"]:
            liq.append({"type": "sell", "price": bars[i]["h"], "idx": i})
        if bars[i]["l"] < bars[i - 1]["l"] and bars[i]["l"] < bars[i - 2]["l"] and bars[i]["l"] < bars[i + 1]["l"]:
            liq.append({"type": "buy", "price": bars[i]["l"], "idx": i})
    return {"obs": obs[-4:], "fvgs": fvgs[-4:], "liq": liq[-4:]}


# ----------------------------------------------------------------------------
# ORCHESTRATOR — merges everything into the frontend payload
# ----------------------------------------------------------------------------
def run_model_full(history: Optional[List[Dict[str, float]]], config: Dict[str, Any],
                   requested_bars: int) -> Dict[str, Any]:
    seed = int(config.get("seed", 0x9E3779B1)) & MASK32
    rng = mulberry32(seed)
    synthetic = not (history and len(history))
    bars = gen_history(int(config["bars"]), rng) if synthetic else history
    truncated = bool(synthetic and requested_bars > MAX_BARS)
    if truncated:
        bars = bars[-MAX_BARS:]
    last_close = bars[-1]["c"]
    assert bars is not None  # guaranteed list after the synthetic/history branch
    paths = gen_paths(last_close, rng, config)
    bands = compute_bands(paths)
    stats = compute_stats(last_close, paths, bands)
    swarm = compute_swarm(config)
    confluence = build_confluence(bands, swarm)
    ict = detect_ict(bars)
    return {
        "history": bars,
        "paths": paths,
        "bands": bands,
        "stats": stats,
        "mirofish": swarm,
        "confluence": confluence,
        "ict": ict,
        "meta": {"backend": "kronos-mirofish-bridge", "max_context": MAX_CTX, "truncated": truncated},
    }


def build_config_from_args(args) -> Dict[str, Any]:
    return {
        "bars": args.bars, "horizon": args.horizon, "paths": args.paths,
        "temp": args.temp, "vol": args.vol / 100.0, "drift": args.drift / 100.0,
        "seed": args.seed, "volInject": args.vol_inject,
        "swarmBias": args.swarm_bias, "newsshock": args.news_shock,
    }


# ----------------------------------------------------------------------------
# OPTIONAL: emulate the production endpoint locally (POST /api/kronos/forecast)
# ----------------------------------------------------------------------------
class BridgeHandler(BaseHTTPRequestHandler):
    def _respond(self, code: int, payload: Dict[str, Any]):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path.rstrip("/") not in ("/api/kronos/forecast", "/api/kronos/forecast/"):
            self._respond(404, {"error": "not found — POST /api/kronos/forecast"})
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._respond(400, {"error": "invalid JSON"})
            return
        cfg = payload.get("config", {}) or {}
        num = lambda v, d: float(v) if isinstance(v, (int, float)) and math.isfinite(v) else d
        requested = max(1, int(num(cfg.get("bars", 80), 80)))
        config = {
            "bars": max(8, requested),
            "horizon": max(4, min(60, int(num(cfg.get("horizon", 24), 24)))),
            "paths": max(1, min(128, int(num(cfg.get("paths", 16), 16)))),
            "temp": max(0.1, min(2.5, num(cfg.get("temp", 1.0), 1.0))),
            "vol": max(0.003, min(0.06, num(cfg.get("vol", 0.018), 0.018))),
            "drift": max(-0.005, min(0.005, num(cfg.get("drift", 0.0002), 0.0002))),
            "seed": int(num(cfg.get("seed", 0x9E3779B1), 0x9E3779B1)) & MASK32,
            "volInject": max(0.5, min(3, num(cfg.get("volInject", 1), 1))),
            "swarmBias": max(-1, min(1, num(cfg.get("swarmBias", 0), 0))),
            "newsShock": max(0, min(100, num(cfg.get("newsShock", 0), 0))),
        }
        history = payload.get("history") if isinstance(payload.get("history"), list) else None
        try:
            out = run_model_full(history, config, requested)
            self._respond(200, out)
        except Exception as e:  # noqa: BLE001
            self._respond(500, {"error": str(e)})

    def log_message(self, format, *args):  # silence default stderr logging
        pass


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Kronos x MiroFish simulation bridge.")
    p.add_argument("--symbol", default="BTCUSDT", help="label for the run (cosmetic)")
    p.add_argument("--bars", type=int, default=80)
    p.add_argument("--horizon", type=int, default=24)
    p.add_argument("--paths", type=int, default=24)
    p.add_argument("--temp", type=float, default=1.0)
    p.add_argument("--vol", type=float, default=1.8, help="Kronos vol sigma in percent")
    p.add_argument("--drift", type=float, default=0.02, help="drift bias in percent")
    p.add_argument("--seed", type=lambda x: int(x) & MASK32, default=0x9E3779B1)
    p.add_argument("--vol-inject", type=float, default=1.0)
    p.add_argument("--swarm-bias", type=float, default=0.0)
    p.add_argument("--news-shock", type=float, default=0.0)
    p.add_argument("--serve", default=None, help="host:port to emulate POST /api/kronos/forecast")
    p.add_argument("--out", default=None, help="write JSON payload to this path instead of stdout")
    args = p.parse_args(argv)

    if args.serve:
        host, _, port = args.serve.partition(":")
        HTTPServer((host or "0.0.0.0", int(port or 8788)), BridgeHandler).serve_forever()
        return 0

    config = {
        "bars": args.bars, "horizon": args.horizon, "paths": args.paths,
        "temp": args.temp, "vol": args.vol / 100.0, "drift": args.drift / 100.0,
        "seed": args.seed, "volInject": args.vol_inject,
        "swarmBias": args.swarm_bias, "newsShock": args.news_shock,
    }
    result = run_model_full(None, config, args.bars)
    result["symbol"] = args.symbol
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote payload for {args.symbol} -> {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
