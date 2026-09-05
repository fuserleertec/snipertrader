from __future__ import annotations

import argparse
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
        prog="sniper-quant",
        description="Phase 1 quant: risk pre-filter, backtester, signal lifecycle",
    )
    parser.add_argument("command", choices=["api", "demo", "backtest"])
    parser.add_argument("--inmemory", action="store_true", help="Skip Timescale; use in-process stores.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    from sniper_quant.config import get_settings

    if args.inmemory:
        import os

        os.environ["USE_INMEMORY"] = "1"
        get_settings.cache_clear()

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

    if args.command in {"demo", "backtest"}:
        from sniper_quant.backtest.demo import run_inmemory_demo

        result = run_inmemory_demo(settings.default_equity)
        print(json.dumps(result.metrics.model_dump(), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
