from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sniper-data",
        description="Phase 1–3 market-data pipeline (paper; live_trading=false)",
    )
    parser.add_argument(
        "command",
        choices=[
            "pipeline",
            "api",
            "evict",
            "demo",
            "killzones",
            "bench",
            "load",
            "drill",
            "snapshot",
            "patterns",
            "setups",
        ],
    )
    parser.add_argument("--symbols", default=None, help="Comma symbols for bench (default BTCUSDT).")
    parser.add_argument("--n", type=int, default=400, help="Tick count for bench.")
    parser.add_argument("--inmemory", action="store_true", help="Use in-process bus/store (no Docker).")
    parser.add_argument("--duration", type=float, default=None, help="Seconds to run the demo/pipeline.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--every",
        type=float,
        default=None,
        help="Snapshot cadence seconds (default 900). Used by `snapshot`.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single dashboard snapshot cycle and exit.",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="(patterns|setups) Replay fixtures in-process (no brokers).",
    )
    parser.add_argument(
        "--e2e-report",
        action="store_true",
        help="(setups) Phase 3 PM integration report (setups 1–6, in-memory).",
    )
    parser.add_argument(
        "--e2e-out",
        default=None,
        help="Write the Phase 3 E2E report JSON to this path.",
    )
    parser.add_argument(
        "--universe",
        default=None,
        help="Comma-separated paper override. Default is GET /v1/universe/top.",
    )
    parser.add_argument(
        "--refresh-minutes",
        type=int,
        default=None,
        help="Multi-symbol scan cadence (default 15). Paper only.",
    )
    parser.add_argument(
        "--paper-scan",
        action="store_true",
        help="(setups) Multi-symbol paper scan across the DE universe (in-memory).",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="(setups --paper-scan) Number of refresh cycles (default 1).",
    )
    args = parser.parse_args(argv)

    from sniper_data.config import get_settings

    settings = get_settings()
    _setup_logging(settings.log_level)

    if args.command == "setups":
        from pathlib import Path

        from sniper_data.pipeline import run_setup_loop, run_setup_replay

        if args.e2e_report or args.e2e_out:
            from sniper_data.setup_detection.e2e import build_phase3_e2e_report, write_quant_replay_pack

            report = asyncio.run(build_phase3_e2e_report())
            text = json.dumps(report, indent=2, default=str)
            print(text)
            if args.e2e_out:
                dest = Path(args.e2e_out)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text)
                write_quant_replay_pack(report, dest.parent / "quant_replay")
            return 0 if report["summary"]["overall"] == "PASS" else 1
        if args.paper_scan or args.universe:
            from sniper_data.setup_detection.multi_scan import run_paper_multi_scan
            from sniper_data.universe import parse_symbol_csv

            override = parse_symbol_csv(args.universe) if args.universe else None
            result = asyncio.run(
                run_paper_multi_scan(
                    universe=override or None,
                    refresh_minutes=args.refresh_minutes if args.refresh_minutes is not None else 15,
                    cycles=args.cycles,
                    duration_s=args.duration,
                )
            )
            print(json.dumps(result, indent=2, default=str))
            return 0
        if args.replay or args.inmemory:
            result = asyncio.run(run_setup_replay())
            print(json.dumps(result, indent=2, default=str))
            return 0
        asyncio.run(run_setup_loop(inmemory=args.inmemory, duration_s=args.duration))
        return 0

    if args.command == "patterns" and args.replay:
        from sniper_data.pipeline import run_anchor_wiring_demo, run_pattern_replay

        result = asyncio.run(run_pattern_replay())
        wiring = asyncio.run(run_anchor_wiring_demo())
        print(json.dumps({"patterns": result, "anchor_wiring": wiring}, indent=2, default=str))
        return 0

    if args.command in {"pipeline", "demo", "patterns"}:
        from sniper_data.pipeline import run_pipeline

        asyncio.run(run_pipeline(inmemory=args.inmemory, duration_s=args.duration))
        return 0

    if args.command == "evict":
        from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore
        from sniper_data.zones import evict_expired_zones

        async def _once() -> None:
            store = InMemoryStateStore() if args.inmemory else RedisStateStore(settings.redis_url)
            try:
                stats = await evict_expired_zones(store)
                print(stats)
            finally:
                await store.close()

        asyncio.run(_once())
        return 0

    if args.command == "killzones":
        from sniper_data.kill_zones import run_killzone_loop

        asyncio.run(
            run_killzone_loop(inmemory=args.inmemory, duration_s=args.duration)
        )
        return 0

    if args.command == "bench":
        from sniper_data.latency import bench_tick_to_vwap

        symbols = [s.strip().upper() for s in (args.symbols or "BTCUSDT").split(",") if s.strip()]
        report = asyncio.run(bench_tick_to_vwap(n=args.n, symbols=symbols))
        print(report)
        return 0 if report["pass"] else 2

    if args.command == "load":
        from pathlib import Path

        from sniper_data.loadtest import bench_under_load, write_load_report

        symbols = [
            s.strip().upper()
            for s in (args.symbols or "BTCUSDT,ETHUSDT,AAPL,MSFT,NVDA,ES,NQ,CL").split(",")
            if s.strip()
        ]
        report = asyncio.run(bench_under_load(n=args.n if args.n != 400 else 3_000, symbols=symbols))
        dest = Path("docs/performance_under_load.md")
        write_load_report(report, dest)
        print(report)
        print(f"wrote {dest}")
        return 0 if report["pass"] else 2

    if args.command == "drill":
        from pathlib import Path

        from sniper_data.dr_drill import run_drill, write_drill_report

        obs = asyncio.run(run_drill())
        dest = Path("docs/dr-drill.md")
        write_drill_report(obs, dest)
        print({"pass": obs["pass"], "report": str(dest)})
        return 0 if obs["pass"] else 2

    if args.command == "snapshot":
        from sniper_data.dashboard import run_snapshot_loop

        interval = args.every if args.every is not None else settings.dashboard_snapshot_interval_s
        result = asyncio.run(
            run_snapshot_loop(
                inmemory=args.inmemory,
                interval_s=interval,
                duration_s=args.duration,
                once=args.once or args.duration is not None and args.duration <= 0,
            )
        )
        print(
            {
                "symbols": result.get("symbols"),
                "live_trading": False,
                "cadence_s": interval,
                "universe_active": "universe:active",
            }
        )
        return 0

    if args.command == "api":
        import uvicorn

        from sniper_data.api import create_app

        if args.inmemory:
            # Shared in-memory store is only useful for unit tests; still allowed.
            import os

            os.environ["USE_INMEMORY"] = "1"
            get_settings.cache_clear()

        uvicorn.run(
            "sniper_data.api:app",
            host=args.host or settings.api_host,
            port=args.port or settings.api_port,
            reload=False,
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
