"""Pluggable news / economic-calendar filter for Setup 4.

No calendar feed ships in this repo. ``AllowAllNewsFilter`` is the default
stub: it **always allows** (never skips). Wire a real feed by implementing
``NewsFilter.should_skip`` or by constructing ``SkipWindowNewsFilter`` with
known event timestamps.

Skip-window interface
---------------------
``should_skip(symbol, ts_ms, *, window_ms) -> bool``

Return ``True`` to **drop** the candidate (major news within ``window_ms``
of ``ts_ms``). Default window is ``SETUP4_NEWS_WINDOW_SEC`` (900s / 15m).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol


class NewsFilter(Protocol):
    def should_skip(self, symbol: str, ts_ms: int, *, window_ms: int) -> bool: ...


class AllowAllNewsFilter:
    """Default stub when no news/calendar feed is configured. Always allow."""

    def should_skip(self, symbol: str, ts_ms: int, *, window_ms: int) -> bool:
        return False


class SkipWindowNewsFilter:
    """Optional skip-window: drop if ``ts_ms`` is within ``window_ms`` of an event.

    ``events`` maps symbol (or ``"*"`` for all symbols) → UTC event timestamps (ms).
    """

    def __init__(self, events: Mapping[str, Iterable[int]] | None = None) -> None:
        self.events: dict[str, tuple[int, ...]] = {
            str(sym).upper(): tuple(int(t) for t in times) for sym, times in (events or {}).items()
        }

    def should_skip(self, symbol: str, ts_ms: int, *, window_ms: int) -> bool:
        keys = (symbol.upper(), "*")
        for key in keys:
            for event_ts in self.events.get(key, ()):
                if abs(int(ts_ms) - event_ts) <= window_ms:
                    return True
        return False
