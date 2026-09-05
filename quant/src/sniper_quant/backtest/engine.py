"""Event-driven backtester. Setup-agnostic: any ``setup_type`` string is a signal."""

from __future__ import annotations

from dataclasses import dataclass

from sniper_quant.config import Settings, get_settings
from sniper_quant.backtest.metrics import compute_metrics
from sniper_quant.models import BacktestMetrics, OHLCVBar, Side, SignalStatus, TradeRecord
from sniper_quant.risk.sizing import fixed_fractional_size
from sniper_quant.usme import compute_usme_levels


@dataclass
class BacktestSignal:
    ts_ms: int
    symbol: str
    setup_type: str
    side: Side | str
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    atr: float | None = None
    invalidation: float | None = None
    signal_id: str | None = None


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    trades: list[TradeRecord]
    equity_curve: list[float]


@dataclass
class _Live:
    trade: TradeRecord
    remaining: float


class EventBacktester:
    """Replay bars + setup signals. Conservative: if SL and TP print on the same bar, SL wins."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(
        self,
        bars: list[OHLCVBar],
        signals: list[BacktestSignal],
        *,
        equity: float | None = None,
    ) -> BacktestResult:
        settings = self.settings
        start = equity if equity is not None else settings.default_equity
        cash = start
        live: dict[str, _Live] = {}
        trades: list[TradeRecord] = []
        equity_curve: list[float] = [start]
        daily_equity: dict[int, float] = {}

        by_symbol: dict[str, list[OHLCVBar]] = {}
        for bar in bars:
            by_symbol.setdefault(bar.symbol, []).append(bar)
        for rows in by_symbol.values():
            rows.sort(key=lambda b: b.open_ts_ms)

        events: list[tuple[int, str, object]] = []
        for bar in bars:
            events.append((bar.open_ts_ms, "bar", bar))
        for i, sig in enumerate(signals):
            events.append((sig.ts_ms, "signal", (i, sig)))
        events.sort(key=lambda e: (e[0], 0 if e[1] == "bar" else 1))

        last_close: dict[str, float] = {}
        sig_n = 0

        for _, kind, payload in events:
            if kind == "bar":
                bar: OHLCVBar = payload  # type: ignore[assignment]
                last_close[bar.symbol] = bar.close
                pos = live.get(bar.symbol)
                if pos is not None:
                    exit_px, status = _intrabar_exit(pos.trade, bar)
                    if exit_px is not None and status is not None:
                        pnl = _close_trade(pos.trade, exit_px, bar.close_ts_ms, status, pos.remaining, settings)
                        cash += pnl
                        del live[bar.symbol]
                mark = cash + _mtm(live, last_close)
                equity_curve.append(mark)
                day = bar.open_ts_ms // 86_400_000
                daily_equity[day] = mark
                continue

            _idx, sig = payload  # type: ignore[misc]
            sig_n += 1
            symbol = sig.symbol.upper()
            if symbol in live:
                continue
            side = Side(sig.side)
            entry = sig.entry
            if entry is None:
                # Use last close at/before the signal if we have one; else skip.
                entry = last_close.get(symbol)
            if entry is None:
                continue
            try:
                levels = compute_usme_levels(
                    side=side,
                    entry=entry,
                    atr=sig.atr,
                    invalidation=sig.invalidation,
                    stop=sig.stop,
                    target=sig.target,
                    sl_atr_multiple=settings.sl_atr_multiple,
                    tp_r_multiple=settings.tp_r_multiple,
                    min_rr=settings.min_rr,
                )
            except ValueError:
                continue

            size = fixed_fractional_size(cash, settings.risk_fraction, levels.risk_per_unit)
            if size <= 0:
                continue
            fill = _apply_slippage(levels.entry, side, settings.slippage_bps, entering=True)
            notional = fill * size
            commission = notional * settings.commission_bps / 10_000.0
            cash -= commission
            trade = TradeRecord(
                signal_id=sig.signal_id or f"bt-{sig_n}",
                symbol=symbol,
                setup_type=sig.setup_type,
                side=side,
                entry=fill,
                stop=levels.stop,
                target=levels.target,
                size=size,
                entry_ts_ms=sig.ts_ms,
                status=SignalStatus.ACTIVE,
            )
            live[symbol] = _Live(trade=trade, remaining=size)
            trades.append(trade)

        # Flatten leftovers at last close.
        for symbol, pos in list(live.items()):
            px = last_close.get(symbol, pos.trade.entry)
            last_ts = max((b.close_ts_ms for b in bars if b.symbol == symbol), default=pos.trade.entry_ts_ms)
            pnl = _close_trade(pos.trade, px, last_ts, SignalStatus.CANCELLED, pos.remaining, self.settings)
            cash += pnl
            del live[symbol]

        ending = cash
        equity_curve.append(ending)
        days = sorted(daily_equity)
        daily_returns: list[float] = []
        for i in range(1, len(days)):
            prev = daily_equity[days[i - 1]]
            cur = daily_equity[days[i]]
            if prev:
                daily_returns.append((cur - prev) / prev)

        metrics = compute_metrics(
            trades,
            starting_equity=start,
            ending_equity=ending,
            equity_curve=equity_curve,
            daily_returns=daily_returns,
        )
        return BacktestResult(metrics=metrics, trades=trades, equity_curve=equity_curve)


def _apply_slippage(price: float, side: Side, bps: float, *, entering: bool) -> float:
    frac = bps / 10_000.0
    if entering:
        return price * (1 + frac) if side is Side.LONG else price * (1 - frac)
    return price * (1 - frac) if side is Side.LONG else price * (1 + frac)


def _intrabar_exit(trade: TradeRecord, bar: OHLCVBar) -> tuple[float | None, SignalStatus | None]:
    if trade.side is Side.LONG:
        hit_sl = bar.low <= trade.stop
        hit_tp = bar.high >= trade.target
        if hit_sl and hit_tp:
            return trade.stop, SignalStatus.SL_HIT
        if hit_sl:
            return trade.stop, SignalStatus.SL_HIT
        if hit_tp:
            return trade.target, SignalStatus.TP_HIT
        return None, None
    hit_sl = bar.high >= trade.stop
    hit_tp = bar.low <= trade.target
    if hit_sl and hit_tp:
        return trade.stop, SignalStatus.SL_HIT
    if hit_sl:
        return trade.stop, SignalStatus.SL_HIT
    if hit_tp:
        return trade.target, SignalStatus.TP_HIT
    return None, None


def _close_trade(
    trade: TradeRecord,
    raw_exit: float,
    ts_ms: int,
    status: SignalStatus,
    size: float,
    settings: Settings,
) -> float:
    fill = _apply_slippage(raw_exit, trade.side, settings.slippage_bps, entering=False)
    if trade.side is Side.LONG:
        gross = (fill - trade.entry) * size
    else:
        gross = (trade.entry - fill) * size
    commission = abs(fill * size) * settings.commission_bps / 10_000.0
    pnl = gross - commission
    risk = abs(trade.entry - trade.stop) * size
    trade.exit_price = fill
    trade.exit_ts_ms = ts_ms
    trade.pnl = pnl
    trade.r_multiple = (pnl / risk) if risk > 0 else 0.0
    trade.status = status
    return pnl


def _mtm(live: dict[str, _Live], last_close: dict[str, float]) -> float:
    total = 0.0
    for symbol, pos in live.items():
        px = last_close.get(symbol, pos.trade.entry)
        if pos.trade.side is Side.LONG:
            total += (px - pos.trade.entry) * pos.remaining
        else:
            total += (pos.trade.entry - px) * pos.remaining
    return total
