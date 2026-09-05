"""Stub economic-calendar for Setup 4 ``news_skip_minutes`` and Setup 6 anchors.

Not a live feed. Fixed timestamps so validate / replay can exercise
``news_window`` and S6 ``earnings`` / ``news`` AVWAP anchors without an
external calendar.
"""

from __future__ import annotations

from dataclasses import dataclass

# 2024-06-03 12:00 UTC — sits in the London session of the synthetic tape
# start day, away from the patterned S4 fade (later London).
STUB_NEWS_TS_MS: int = 1_717_416_000_000

# 2024-06-03 13:30 UTC — NY AM open on the synthetic tape (S6 earnings anchor).
STUB_EARNINGS_TS_MS: int = 1_717_421_400_000

# Isolated stamp for unit tests (not on the synthetic tape clock).
TEST_NEWS_TS_MS: int = 1_800_000_000_000


@dataclass(frozen=True)
class NewsEvent:
    ts_ms: int
    symbol: str | None = None
    label: str = "stub_cpi"
    kind: str = "news"  # news | earnings


STUB_CALENDAR: tuple[NewsEvent, ...] = (
    NewsEvent(ts_ms=STUB_NEWS_TS_MS, symbol=None, label="stub_fomc", kind="news"),
    NewsEvent(ts_ms=TEST_NEWS_TS_MS, symbol=None, label="stub_cpi", kind="news"),
    NewsEvent(ts_ms=STUB_EARNINGS_TS_MS, symbol=None, label="stub_earnings", kind="earnings"),
)


def in_news_window(
    ts_ms: int,
    *,
    symbol: str | None = None,
    skip_minutes: int = 15,
    calendar: tuple[NewsEvent, ...] = STUB_CALENDAR,
) -> NewsEvent | None:
    """Return the first stub event within ±skip_minutes of ``ts_ms``."""
    window = max(int(skip_minutes), 0) * 60_000
    if window <= 0:
        return None
    want = (symbol or "").upper().replace("-", "") or None
    for event in calendar:
        if event.symbol and want and event.symbol != want:
            continue
        if abs(int(ts_ms) - event.ts_ms) <= window:
            return event
    return None


def calendar_anchor_events(
    ts_ms: int,
    *,
    kinds: tuple[str, ...] = ("news", "earnings"),
    calendar: tuple[NewsEvent, ...] = STUB_CALENDAR,
) -> list[NewsEvent]:
    """Stub events strictly before ``ts_ms`` — S6 AVWAP anchors, not a skip gate."""
    want = set(kinds)
    return [event for event in calendar if event.kind in want and event.ts_ms < int(ts_ms)]
