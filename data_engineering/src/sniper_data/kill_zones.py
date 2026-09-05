"""Kill-zone timer (Phase 2).

Publishes start/end events to Kafka ``kill_zone_events``.
Redis lookup (documented convention):

* ``kill_zone:{symbol}`` — current (or last) zone for that symbol; exact
  ``KillZoneEvent`` JSON (``active`` true while inside the primary window).
* ``kill_zone:active:{asset_class}`` — class-level view: ``kill_zone``,
  ``start_time``, ``end_time``, ``active``, ``asset_class`` (no ``symbol``).

Windows reuse Phase 1 session definitions (crypto UTC kill zones; equities
RTH/ETH; futures RTH/Globex).
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass

from sniper_data.bus.kafka import EventBus, InMemoryBus, KafkaBus, wait_for_kafka
from sniper_data.bus.redis_store import InMemoryStateStore, RedisStateStore, StateStore
from sniper_data.config import Settings, get_settings
from sniper_data.models import AssetClass, KillZoneEvent
from sniper_data.sessions import SessionWindow, dt_from_ms, primary_session, sessions_at
from sniper_data.symbols import infer_asset_class, normalize_symbol

log = logging.getLogger(__name__)

KILL_ZONE_TOPIC = "kill_zone_events"


def redis_kill_zone_key(symbol: str) -> str:
    return f"kill_zone:{symbol}"


def redis_kill_zone_active_key(asset_class: str | AssetClass) -> str:
    name = asset_class.value if isinstance(asset_class, AssetClass) else asset_class
    return f"kill_zone:active:{name}"


def redis_kill_zone_channel(symbol: str) -> str:
    return f"kill_zone:{symbol}"


def windows_for(symbol: str, ts_ms: int, asset_class: AssetClass | str | None = None) -> list[SessionWindow]:
    klass = infer_asset_class(normalize_symbol(symbol), asset_class)
    return sessions_at(klass, dt_from_ms(ts_ms))


def primary_window(symbol: str, ts_ms: int, asset_class: AssetClass | str | None = None) -> SessionWindow | None:
    klass = infer_asset_class(normalize_symbol(symbol), asset_class)
    return primary_session(klass, dt_from_ms(ts_ms))


def event_for(
    symbol: str,
    window: SessionWindow,
    *,
    active: bool,
    asset_class: AssetClass,
) -> KillZoneEvent:
    return KillZoneEvent(
        symbol=normalize_symbol(symbol),
        kill_zone=window.session_type,
        start_time=window.start_ms,
        end_time=window.end_ms,
        active=active,
        asset_class=asset_class,
    )


def _fingerprint(ev: KillZoneEvent) -> tuple:
    return (ev.symbol, ev.kill_zone.value, ev.start_time, ev.end_time, ev.active)


def _class_view(ev: KillZoneEvent) -> dict:
    return {
        "kill_zone": ev.kill_zone.value,
        "start_time": ev.start_time,
        "end_time": ev.end_time,
        "active": ev.active,
        "asset_class": ev.asset_class.value,
    }


@dataclass
class KillZoneTransition:
    event: KillZoneEvent
    reason: str  # "start" | "end"


class KillZoneScheduler:
    """Compare current windows to the last published set; emit start/end."""

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = [normalize_symbol(s) for s in symbols]
        # (symbol, session_type) → last window start_ms while that zone was active
        self._active: dict[tuple[str, str], int] = {}
        self._last_event: dict[str, KillZoneEvent] = {}

    def transitions(self, now_ms: int | None = None) -> list[KillZoneTransition]:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        out: list[KillZoneTransition] = []
        for symbol in self.symbols:
            klass = infer_asset_class(symbol)
            windows = sessions_at(klass, dt_from_ms(now_ms))
            live = {w.session_type.value: w for w in windows}
            seen = {k[1] for k in self._active if k[0] == symbol}

            for name, window in live.items():
                key = (symbol, name)
                prev_start = self._active.get(key)
                if prev_start != window.start_ms:
                    ev = event_for(symbol, window, active=True, asset_class=klass)
                    out.append(KillZoneTransition(event=ev, reason="start"))
                    self._active[key] = window.start_ms
                    self._last_event[symbol] = ev

            for name in list(seen):
                if name in live:
                    continue
                start_ms = self._active.pop((symbol, name))
                ended = _ended_window(klass, name, start_ms)
                if ended is None:
                    continue
                ev = event_for(symbol, ended, active=False, asset_class=klass)
                out.append(KillZoneTransition(event=ev, reason="end"))
                self._last_event[symbol] = ev
        return out

    def current_books(self, now_ms: int | None = None) -> list[KillZoneEvent]:
        """Primary-zone Redis payloads (RTH over ETH; inactive last-zone otherwise)."""
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        books: list[KillZoneEvent] = []
        for symbol in self.symbols:
            klass = infer_asset_class(symbol)
            window = primary_session(klass, dt_from_ms(now_ms))
            if window is not None:
                books.append(event_for(symbol, window, active=True, asset_class=klass))
                continue
            last = self._last_event.get(symbol)
            if last is not None:
                if last.active:
                    books.append(last.model_copy(update={"active": False}))
                else:
                    books.append(last)
        return books


def _ended_window(klass: AssetClass, session_type: str, start_ms: int) -> SessionWindow | None:
    """Find the window of ``session_type`` that began at ``start_ms``."""
    # Probe just after start — the window is still active then.
    for delta in (1, 1_000, 60_000):
        for w in sessions_at(klass, dt_from_ms(start_ms + delta)):
            if w.session_type.value == session_type and w.start_ms == start_ms:
                return w
    # Fallback: synthesize from known Phase 1 bounds using primary at start.
    w = primary_session(klass, dt_from_ms(start_ms + 1))
    if w is not None and w.session_type.value == session_type:
        return w
    for w in sessions_at(klass, dt_from_ms(start_ms + 1)):
        if w.session_type.value == session_type:
            return w
    return None


async def publish_transition(
    bus: EventBus,
    store: StateStore,
    transition: KillZoneTransition,
) -> None:
    ev = transition.event
    payload = ev.model_dump(mode="json")
    await bus.publish(KILL_ZONE_TOPIC, payload, key=ev.symbol)
    await store.publish(redis_kill_zone_channel(ev.symbol), payload)
    from sniper_data.metrics import record_kill_zone_transition

    record_kill_zone_transition(ev)


async def write_current_books(store: StateStore, books: list[KillZoneEvent]) -> None:
    """Write ``kill_zone:{symbol}`` + ``kill_zone:active:{asset_class}``."""
    for ev in books:
        payload = ev.model_dump(mode="json")
        await store.set(redis_kill_zone_key(ev.symbol), payload)
        await store.set(redis_kill_zone_active_key(ev.asset_class), _class_view(ev))


async def apply_killzone_tick(
    bus: EventBus,
    store: StateStore,
    scheduler: KillZoneScheduler,
    now_ms: int | None = None,
) -> list[KillZoneTransition]:
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    transitions = scheduler.transitions(now_ms)
    for tr in transitions:
        await publish_transition(bus, store, tr)
    await write_current_books(store, scheduler.current_books(now_ms))
    return transitions


async def run_killzone_loop(
    *,
    settings: Settings | None = None,
    bus: EventBus | None = None,
    store: StateStore | None = None,
    inmemory: bool | None = None,
    duration_s: float | None = None,
    poll_s: float | None = None,
) -> KillZoneScheduler:
    settings = settings or get_settings()
    use_mem = settings.use_inmemory if inmemory is None else inmemory
    bus = bus or (InMemoryBus() if use_mem else KafkaBus(settings.kafka_bootstrap, client_id="sniper-killzone"))
    store = store or (InMemoryStateStore() if use_mem else RedisStateStore(settings.redis_url))
    scheduler = KillZoneScheduler(settings.symbols)
    interval = settings.killzone_poll_s if poll_s is None else poll_s

    if isinstance(bus, KafkaBus):
        await wait_for_kafka(settings.kafka_bootstrap)
    await bus.start()

    from sniper_data.metrics import start_metrics_server

    start_metrics_server(settings.metrics_port)

    stop = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    started = loop.time()
    try:
        while not stop.is_set():
            try:
                transitions = await apply_killzone_tick(bus, store, scheduler)
                for tr in transitions:
                    log.info(
                        "kill_zone %s %s %s active=%s",
                        tr.reason,
                        tr.event.symbol,
                        tr.event.kill_zone.value,
                        tr.event.active,
                    )
            except Exception:  # noqa: BLE001
                log.exception("kill zone tick failed")
            if duration_s is not None and (loop.time() - started) >= duration_s:
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    finally:
        await bus.stop()
        await store.close()
    return scheduler
