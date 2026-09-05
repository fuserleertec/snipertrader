"""ACTIVE → TP_HIT / SL_HIT monitor. Records outcome and R multiple."""

from __future__ import annotations

import asyncio
import logging

from sniper_quant.config import Settings, get_settings
from sniper_quant.exits import bar_exit, outcome_from_status, r_multiple_achieved
from sniper_quant.live import SignalHub
from sniper_quant.models import OHLCVBar, SignalStatus, SignalView, StoredSignal
from sniper_quant.store.ohlcv import OHLCVLoader
from sniper_quant.store.signals import SignalStore

log = logging.getLogger(__name__)


def resolve_close_patch(
    row: StoredSignal,
    status: SignalStatus,
    *,
    exit_price: float | None = None,
    realized_r: float | None = None,
    closed_ts_ms: int | None = None,
    outcome: str | None = None,
) -> dict:
    """Persist Frontend close fields. ``realized_r`` is null unless TP/SL."""
    if status is SignalStatus.ACTIVE:
        return {
            "closed_ts_ms": None,
            "exit_px": None,
            "r_multiple": None,
            "outcome": None,
        }
    if status is SignalStatus.CANCELLED:
        return {
            "closed_ts_ms": closed_ts_ms,
            "exit_px": exit_price,
            "r_multiple": None,
            "outcome": outcome or "cancelled",
        }
    px = exit_price
    if px is None:
        if status is SignalStatus.TP_HIT:
            px = row.target
        elif status is SignalStatus.SL_HIT:
            px = row.stop
    r_mult = realized_r
    if r_mult is None and px is not None and row.entry is not None and row.stop is not None:
        r_mult = r_multiple_achieved(side=row.side, entry=row.entry, stop=row.stop, exit_px=px)
    return {
        "closed_ts_ms": closed_ts_ms,
        "exit_px": px,
        "r_multiple": r_mult,
        "outcome": outcome or outcome_from_status(status),
    }


def evaluate_signal_on_bar(signal: StoredSignal, bar: OHLCVBar) -> dict | None:
    """If this bar tags TP or SL, return the status patch. Same-bar SL wins."""
    if signal.status is not SignalStatus.ACTIVE:
        return None
    if signal.symbol != bar.symbol:
        return None
    if signal.entry is None or signal.stop is None or signal.target is None:
        return None
    exit_px, status = bar_exit(side=signal.side, stop=signal.stop, target=signal.target, bar=bar)
    if exit_px is None or status is None:
        return None
    r_mult = r_multiple_achieved(
        side=signal.side, entry=signal.entry, stop=signal.stop, exit_px=exit_px
    )
    return {
        "status": status,
        "closed_ts_ms": bar.close_ts_ms,
        "exit_px": exit_px,
        "r_multiple": r_mult,
        "outcome": outcome_from_status(status),
    }


class LifecycleMonitor:
    def __init__(
        self,
        store: SignalStore,
        hub: SignalHub | None = None,
        ohlcv: OHLCVLoader | None = None,
    ) -> None:
        self.store = store
        self.hub = hub or SignalHub()
        self.ohlcv = ohlcv
        self._seen_bars: set[tuple[str, int]] = set()

    async def apply_bar(self, bar: OHLCVBar) -> list[StoredSignal]:
        """Evaluate all ACTIVE signals against one bar. Broadcasts ``signal.status``."""
        updated: list[StoredSignal] = []
        for signal in await self.store.active():
            patch = evaluate_signal_on_bar(signal, bar)
            if patch is None:
                continue
            row = await self.store.update_status(
                signal.id,
                patch["status"],
                closed_ts_ms=patch["closed_ts_ms"],
                exit_px=patch["exit_px"],
                r_multiple=patch["r_multiple"],
                outcome=patch["outcome"],
            )
            if row is None:
                continue
            updated.append(row)
            await self.hub.publish("signal.status", SignalView.from_stored(row))
            log.info(
                "lifecycle %s %s %s r=%.3f",
                row.id,
                row.status.value,
                row.symbol,
                row.r_multiple or 0.0,
            )
        return updated

    async def poll_once(self, symbols: list[str], timeframe: str = "1m") -> int:
        """Apply unseen bars from the OHLCV loader (Timescale or in-memory)."""
        if self.ohlcv is None:
            return 0
        n = 0
        for symbol in symbols:
            bars = await self.ohlcv.fetch(symbol, timeframe, limit=500)
            for bar in bars:
                key = (bar.symbol, bar.open_ts_ms)
                if key in self._seen_bars:
                    continue
                self._seen_bars.add(key)
                closed = await self.apply_bar(bar)
                n += len(closed)
        return n


async def run_monitor_loop(
    monitor: LifecycleMonitor,
    *,
    symbols: list[str],
    timeframe: str = "1m",
    interval_s: float = 5.0,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    log.info("lifecycle monitor symbols=%s tf=%s", symbols, timeframe)
    while True:
        try:
            closed = await monitor.poll_once(symbols, timeframe)
            if closed:
                log.info("lifecycle closed %s signal(s)", closed)
        except Exception:  # noqa: BLE001 — keep the loop alive
            log.exception("lifecycle poll failed")
        await asyncio.sleep(interval_s)
