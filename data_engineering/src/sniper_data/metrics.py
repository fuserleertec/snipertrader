"""Prometheus metrics for Phase 2 services.

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

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest, start_http_server

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
SETUP_DETECTION_SECONDS = Histogram(
    "sniper_setup_detection_latency_seconds",
    "Wall time to evaluate setups 1–3 for one event batch",
    ["setup"],
)
SETUP_CANDIDATES = Counter(
    "sniper_setup_candidates_total",
    "Raw (pre-risk) setup candidates",
    ["setup_type", "side"],
)
SETUP_APPROVED = Counter(
    "sniper_setup_approved_total",
    "Candidates published after risk approved:true",
    ["setup_type"],
)
SETUP_REJECTED = Counter(
    "sniper_setup_rejected_total",
    "Candidates discarded after risk approved:false (false-positive proxy)",
    ["setup_type", "reason"],
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


def record_setup_latency(setup: str, elapsed_s: float) -> None:
    SETUP_DETECTION_SECONDS.labels(setup).observe(elapsed_s)


def record_setup_candidate(setup_type: str, side: str) -> None:
    SETUP_CANDIDATES.labels(setup_type, side).inc()


def record_setup_approved(setup_type: str) -> None:
    SETUP_APPROVED.labels(setup_type).inc()


def record_setup_rejected(setup_type: str, reason: str) -> None:
    label = (reason or "rejected")[:64]
    SETUP_REJECTED.labels(setup_type, label).inc()
