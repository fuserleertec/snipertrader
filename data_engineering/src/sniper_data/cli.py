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
    parser = argparse.ArgumentParser(prog="sniper-data", description="Phase 1 market-data + pattern pipeline")
    parser.add_argument("command", choices=["pipeline", "api", "evict", "demo", "patterns"])
    parser.add_argument("--inmemory", action="store_true", help="Use in-process bus/store (no Docker).")
    parser.add_argument("--duration", type=float, default=None, help="Seconds to run the demo/pipeline.")
    parser.add_argument(
        "--replay",
        action="store_true",
        help="(patterns) Replay ICT fixtures instead of the live mock feed.",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    from sniper_data.config import get_settings

    settings = get_settings()
    _setup_logging(settings.log_level)

    if args.command == "patterns" and args.replay:
        from sniper_data.pipeline import run_pattern_replay

        result = asyncio.run(run_pattern_replay())
        print(json.dumps(result, indent=2, default=str))
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
