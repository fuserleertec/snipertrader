from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _enable_inmemory() -> None:
    import os

    from sniper_quant.config import get_settings

    os.environ["USE_INMEMORY"] = "1"
    get_settings.cache_clear()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sniper-quant",
        description="Phase 2 quant: risk pre-filter, setup_signals gate, backtest, lifecycle",
    )
    parser.add_argument(
        "command",
        choices=["api", "demo", "backtest", "consume", "monitor"],
    )
    parser.add_argument("--inmemory", action="store_true", help="Skip Timescale / Kafka.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--setups",
        default="1,2,3",
        help="Backtest setup ids or names, e.g. 1,2,3 or sweep_reclaim,fvg_entry,po3_judas",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Write walk-forward markdown (default: quant/reports/setups_1_3_walkforward.md)",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument(
        "--grid-mode",
        default="full",
        choices=["baseline", "core", "full"],
        help="Walk-forward grid: baseline=defaults only, core=reduced, full=locked ML cartesian",
    )
    parser.add_argument(
        "--symbols",
        default="BTCUSDT,ETHUSDT,AAPL,ES",
        help="Monitor: comma-separated symbols to scan for TP/SL",
    )
    parser.add_argument("--interval", type=float, default=5.0, help="Monitor poll seconds")
    args = parser.parse_args(argv)

    from sniper_quant.config import get_settings

    if args.inmemory:
        _enable_inmemory()

    settings = get_settings()
    _setup_logging(settings.log_level)

    if args.command == "api":
        import uvicorn

        uvicorn.run(
            "sniper_quant.api:app",
            host=args.host or settings.api_host,
            port=args.port or settings.api_port,
            reload=False,
        )
        return 0

    if args.command == "demo":
        from sniper_quant.backtest.demo import run_inmemory_demo

        result = run_inmemory_demo(settings.default_equity)
        print(json.dumps(result.metrics.model_dump(), indent=2))
        return 0

    if args.command == "backtest":
        return _run_backtest(args, settings)

    if args.command == "consume":
        return asyncio.run(_run_consume(args, settings))

    if args.command == "monitor":
        return asyncio.run(_run_monitor(args, settings))

    return 1


def _run_backtest(args, settings) -> int:
    from sniper_quant.backtest.detectors import parse_setup_ids
    from sniper_quant.backtest.report import render_walkforward_markdown, write_walkforward_report
    from sniper_quant.backtest.synthetic_setups import synthetic_setup_tape
    from sniper_quant.backtest.walkforward import walk_forward_setups

    setup_ids = parse_setup_ids(args.setups)
    source = "in-memory synthetic tape"
    bars = synthetic_setup_tape(args.symbol, timeframe=args.timeframe)
    if not args.inmemory:
        try:
            bars_db = asyncio.run(_load_ohlcv(settings.database_url, args.symbol, args.timeframe))
            if bars_db:
                bars = bars_db
                source = f"Timescale ohlcv_bars ({settings.database_url.split('@')[-1]})"
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("Timescale load failed (%s); using synthetic", exc)

    results = walk_forward_setups(
        bars,
        setup_ids,
        n_folds=args.folds,
        equity=settings.default_equity,
        mode=args.grid_mode,
    )
    if args.report:
        report_path = Path(args.report)
    elif set(setup_ids) <= {4, 5, 6}:
        report_path = Path("reports/setups_4_6_walkforward.md")
    else:
        report_path = Path("reports/setups_1_3_walkforward.md")
    if not report_path.is_absolute():
        report_path = Path(__file__).resolve().parents[2] / report_path
    md = render_walkforward_markdown(
        results,
        symbol=args.symbol,
        timeframe=args.timeframe,
        source=source,
        n_bars=len(bars),
        n_folds=args.folds,
        mode=args.grid_mode,
    )
    write_walkforward_report(report_path, md)
    payload = {
        "source": source,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "n_bars": len(bars),
        "n_folds": args.folds,
        "grid_mode": args.grid_mode,
        "report": str(report_path),
        "setups": {
            row.setup_type: {
                "oos": row.oos.model_dump(),
                "baseline_full": row.baseline_full.model_dump(),
                "baseline_oos": row.baseline_oos.model_dump(),
                "recommended": row.recommended,
                "grid_size": row.grid_size,
            }
            for row in results
        },
    }
    print(json.dumps(payload, indent=2))
    return 0


async def _load_ohlcv(dsn: str, symbol: str, timeframe: str):
    from sniper_quant.store.ohlcv import TimescaleOHLCVLoader

    loader = TimescaleOHLCVLoader(dsn)
    try:
        return await loader.fetch(symbol, timeframe, limit=50_000)
    finally:
        await loader.close()


async def _run_consume(args, settings) -> int:
    from sniper_quant.bus import InMemoryBus, SETUP_SIGNALS_TOPIC
    from sniper_quant.live import SignalHub
    from sniper_quant.store.signals import InMemorySignalStore, TimescaleSignalStore
    from sniper_quant.validate_service import (
        SignalValidationService,
        run_inmemory_consumer,
        run_kafka_consumer,
    )

    store = InMemorySignalStore() if settings.use_inmemory else TimescaleSignalStore(settings.database_url)
    service = SignalValidationService(store, SignalHub(), min_rr=settings.min_rr)
    if settings.use_inmemory:
        bus = InMemoryBus()
        await run_inmemory_consumer(bus, service)
        logging.getLogger(__name__).info(
            "in-memory consume attached to %s — publish via tests or POST /v1/signals/ingest",
            SETUP_SIGNALS_TOPIC,
        )
        # Park the process so compose/dev can keep the consumer "up".
        while True:
            await asyncio.sleep(3600)
    await run_kafka_consumer(service, settings)
    return 0


async def _run_monitor(args, settings) -> int:
    from sniper_quant.lifecycle import LifecycleMonitor, run_monitor_loop
    from sniper_quant.live import SignalHub
    from sniper_quant.store.ohlcv import InMemoryOHLCVLoader, TimescaleOHLCVLoader
    from sniper_quant.store.signals import InMemorySignalStore, TimescaleSignalStore

    if settings.use_inmemory:
        store = InMemorySignalStore()
        ohlcv = InMemoryOHLCVLoader()
    else:
        store = TimescaleSignalStore(settings.database_url)
        ohlcv = TimescaleOHLCVLoader(settings.database_url)
    monitor = LifecycleMonitor(store, SignalHub(), ohlcv)
    symbols = [s.strip().upper().replace("-", "") for s in args.symbols.split(",") if s.strip()]
    await run_monitor_loop(
        monitor,
        symbols=symbols,
        timeframe=args.timeframe,
        interval_s=args.interval,
        settings=settings,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
