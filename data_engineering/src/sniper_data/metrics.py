"""Prometheus metrics for Phase 2 + Phase 3 services.

Scrape endpoints
----------------
* API process: ``GET http://localhost:8000/metrics``
* Pipeline process (when ``METRICS_PORT`` is set): ``http://localhost:9101/metrics``
* Kill-zone scheduler (when ``METRICS_PORT`` is set): ``http://localhost:9102/metrics``
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)

from sniper_data.models import AssetClass, KillZoneEvent

log = logging.getLogger(__name__)

TICKS_TOTAL = Counter(
    "sniper_ticks_processed_total",
    "Ticks handled by the pipeline",
    ["asset_class"],
)
AVWAP_UPDATES = Counter(
    "sniper_avwap_updates_total",
    "Anchored VWAP snapshots written to Redis",
    ["asset_class"],
)
AVWAP_SECONDS = Histogram(
    "sniper_avwap_compute_seconds",
    "Wall time to update all anchors for one tick",
)
VOLUME_PROFILE_UPDATES = Counter(
    "sniper_volume_profile_updates_total",
    "Volume-profile snapshots written to Redis",
    ["session_type"],
)
VOLUME_PROFILE_SECONDS = Histogram(
    "sniper_volume_profile_compute_seconds",
    "Wall time to update volume profiles for one tick",
)
KILL_ZONE_TRANSITIONS = Counter(
    "sniper_kill_zone_transitions_total",
    "Kill-zone start/end events published",
    ["asset_class", "kill_zone", "active"],
)
HTTP_SECONDS = Histogram(
    "sniper_http_request_duration_seconds",
    "API HTTP request latency",
    ["method", "route"],
)

# ── Phase 3: scale / latency / quality ──────────────────────────────────────

VWAP_SECONDS = Histogram(
    "sniper_vwap_compute_seconds",
    "Wall time to update session/weekly/rolling VWAP for one tick (incremental W/S/Q)",
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
TICK_TO_VWAP_SECONDS = Histogram(
    "sniper_tick_to_vwap_seconds",
    "End-to-end: handle_tick start → Redis VWAP write (SLO p99 < 500ms)",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)
WS_CONNECTIONS = Gauge(
    "sniper_ws_connections",
    "Open WebSocket connections",
    ["route"],
)
WS_MESSAGES = Counter(
    "sniper_ws_messages_total",
    "WebSocket frames sent",
    ["route"],
)
WS_DROPPED = Counter(
    "sniper_ws_dropped_total",
    "WebSocket frames dropped under backpressure",
    ["route"],
)
WS_PUBLISH_SECONDS = Histogram(
    "sniper_ws_publish_seconds",
    "Time from Redis pub/sub receive to WS send",
    ["route"],
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)
REDIS_ERRORS = Counter(
    "sniper_redis_errors_total",
    "Redis operation failures (before successful retry)",
    ["op"],
)
KAFKA_ERRORS = Counter(
    "sniper_kafka_errors_total",
    "Kafka produce/consume failures (before successful retry)",
    ["op"],
)
KAFKA_LAG = Gauge(
    "sniper_kafka_consumer_lag",
    "Kafka consumer lag in messages",
    ["topic", "group"],
)
REDIS_MEMORY_BYTES = Gauge(
    "sniper_redis_memory_bytes",
    "Redis used_memory from INFO memory",
)
MISSING_TICKS = Counter(
    "sniper_missing_ticks_total",
    "Detected timestamp gaps in the inbound tick stream",
    ["symbol"],
)
OUTLIER_TICKS = Counter(
    "sniper_outlier_ticks_total",
    "Ticks rejected or flagged as price outliers",
    ["symbol"],
)
PUBLISH_SECONDS = Histogram(
    "sniper_bus_publish_seconds",
    "Kafka / in-memory bus publish latency",
    ["topic"],
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

_metrics_started = False


def start_metrics_server(port: int) -> None:
    global _metrics_started
    if not port or _metrics_started:
        return
    start_http_server(int(port))
    _metrics_started = True
    log.info("prometheus scrape listening on :%s/metrics", port)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def record_tick(asset_class: AssetClass | str) -> None:
    name = asset_class.value if isinstance(asset_class, AssetClass) else str(asset_class)
    TICKS_TOTAL.labels(name).inc()


def timed(histogram: Histogram) -> Callable:
    def deco(fn: Callable) -> Callable:
        def wrapped(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                histogram.observe(time.perf_counter() - start)

        return wrapped

    return deco


def record_avwap(n: int, asset_class: AssetClass | str, elapsed_s: float) -> None:
    name = asset_class.value if isinstance(asset_class, AssetClass) else str(asset_class)
    if n:
        AVWAP_UPDATES.labels(name).inc(n)
    AVWAP_SECONDS.observe(elapsed_s)


def record_volume_profile(session_types: list[str], elapsed_s: float) -> None:
    for st in session_types:
        VOLUME_PROFILE_UPDATES.labels(st).inc()
    VOLUME_PROFILE_SECONDS.observe(elapsed_s)


def record_kill_zone_transition(event: KillZoneEvent) -> None:
    KILL_ZONE_TRANSITIONS.labels(
        event.asset_class.value,
        event.kill_zone.value,
        "true" if event.active else "false",
    ).inc()


def record_http(method: str, route: str, elapsed_s: float) -> None:
    HTTP_SECONDS.labels(method, route).observe(elapsed_s)


def record_vwap_calc(elapsed_s: float) -> None:
    VWAP_SECONDS.observe(elapsed_s)


def record_tick_to_vwap(elapsed_s: float) -> None:
    TICK_TO_VWAP_SECONDS.observe(elapsed_s)


def record_ws_connect(route: str) -> None:
    WS_CONNECTIONS.labels(route).inc()


def record_ws_disconnect(route: str) -> None:
    WS_CONNECTIONS.labels(route).dec()


def record_ws_message(route: str, elapsed_s: float | None = None) -> None:
    WS_MESSAGES.labels(route).inc()
    if elapsed_s is not None:
        WS_PUBLISH_SECONDS.labels(route).observe(elapsed_s)


def record_ws_drop(route: str) -> None:
    WS_DROPPED.labels(route).inc()


def record_redis_error(op: str) -> None:
    REDIS_ERRORS.labels(op).inc()


def record_kafka_error(op: str) -> None:
    KAFKA_ERRORS.labels(op).inc()


def set_kafka_lag(topic: str, group: str, lag: float) -> None:
    KAFKA_LAG.labels(topic, group).set(lag)


def set_redis_memory_bytes(n: float) -> None:
    REDIS_MEMORY_BYTES.set(n)


def record_missing_tick(symbol: str) -> None:
    MISSING_TICKS.labels(symbol).inc()


def record_outlier_tick(symbol: str) -> None:
    OUTLIER_TICKS.labels(symbol).inc()


def record_publish(topic: str, elapsed_s: float) -> None:
    PUBLISH_SECONDS.labels(topic).observe(elapsed_s)
