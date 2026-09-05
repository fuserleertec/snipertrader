"""Risk Pre-Filter orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field

from sniper_quant.config import Settings, get_settings
from sniper_quant.models import (
    CandidateSignal,
    OpenPosition,
    RiskParams,
    SignalStatus,
    StoredSignal,
    ValidateResponse,
    normalize_symbol,
)
from sniper_quant.risk.correlation import correlation_check
from sniper_quant.risk.daily_loss import daily_loss_check
from sniper_quant.risk.sizing import fixed_fractional_size, requested_risk
from sniper_quant.usme import check_provided_levels


@dataclass
class RiskState:
    """In-process book used by the pre-filter (and by tests)."""

    equity: float = 100_000.0
    daily_pnl: float = 0.0
    positions: list[OpenPosition] = field(default_factory=list)
    daily_returns: dict[str, list[float]] = field(default_factory=dict)
    account_id: str = "default"

    def open_symbols(self) -> list[str]:
        return [p.symbol for p in self.positions]

    def has_symbol(self, symbol: str) -> bool:
        symbol = normalize_symbol(symbol)
        return any(p.symbol == symbol for p in self.positions)

    def add_position(self, position: OpenPosition) -> None:
        self.positions.append(position)

    def clear_positions(self) -> None:
        self.positions.clear()

    def sync_from_signals(self, signals: list[StoredSignal]) -> None:
        """Treat ACTIVE signals as open positions for conflict / correlation."""
        self.positions = [
            OpenPosition(
                symbol=s.symbol,
                side=s.side,
                size=s.position_size or 0.0,
                entry=s.entry or 0.0,
                stop=s.stop,
                opened_ts_ms=s.ts_ms,
            )
            for s in signals
            if s.status is SignalStatus.ACTIVE
        ]


class RiskEngine:
    def __init__(self, settings: Settings | None = None, state: RiskState | None = None) -> None:
        self.settings = settings or get_settings()
        self.state = state or RiskState(equity=self.settings.default_equity)

    def params(self) -> RiskParams:
        s = self.settings
        return RiskParams(
            risk_fraction=s.risk_fraction,
            max_daily_loss_frac=s.max_daily_loss_frac,
            corr_lookback_days=s.corr_lookback_days,
            corr_threshold=s.corr_threshold,
            sl_atr_multiple=s.sl_atr_multiple,
            tp_r_multiple=s.tp_r_multiple,
            min_rr=s.min_rr,
            commission_bps=s.commission_bps,
            slippage_bps=s.slippage_bps,
        )

    def validate(
        self,
        candidate: CandidateSignal,
        *,
        extra_positions: list[OpenPosition] | None = None,
    ) -> ValidateResponse:
        settings = self.settings
        equity = self.state.equity
        entry = candidate.entry
        checks: dict = {}

        try:
            levels = check_provided_levels(
                side=candidate.side,
                entry=entry,
                stop=candidate.stop,
                target=candidate.target,
                min_rr=settings.min_rr,
            )
        except ValueError as exc:
            return ValidateResponse(
                approved=False,
                reason="invalid_levels",
                adjusted_position_size=0.0,
                entry=entry,
                stop=candidate.stop,
                target=candidate.target,
                checks={"levels": str(exc)},
            )

        checks["levels"] = {
            "source": levels.source,
            "r_multiple": levels.r_multiple,
            "setup_type": candidate.setup_type.value
            if hasattr(candidate.setup_type, "value")
            else str(candidate.setup_type),
            "timeframe": candidate.timeframe.value
            if hasattr(candidate.timeframe, "value")
            else str(candidate.timeframe),
        }

        max_size = fixed_fractional_size(equity, settings.risk_fraction, levels.risk_per_unit)
        requested = candidate.proposed_position_size
        size_ok = requested is None or requested <= max_size + 1e-9
        planned = requested if (requested is not None and size_ok) else max_size
        checks["position_sizing"] = {
            "ok": size_ok,
            "max_size": max_size,
            "requested": requested,
            "risk_fraction": settings.risk_fraction,
        }

        positions = list(self.state.positions)
        if extra_positions:
            positions.extend(extra_positions)
        symbol = candidate.symbol
        conflict = any(p.symbol == symbol for p in positions)
        checks["same_symbol_conflict"] = {"ok": not conflict, "open": [p.symbol for p in positions]}

        new_risk = planned * levels.risk_per_unit
        daily = daily_loss_check(
            equity=equity,
            daily_pnl=self.state.daily_pnl,
            new_risk=new_risk,
            risk_per_unit=levels.risk_per_unit,
            max_daily_loss_frac=settings.max_daily_loss_frac,
        )
        checks["daily_loss"] = {
            "ok": daily.ok,
            "already_breached": daily.already_breached,
            "remaining_risk_budget": daily.remaining_risk_budget,
            "daily_pnl": self.state.daily_pnl,
        }

        corr = correlation_check(
            symbol,
            [p.symbol for p in positions],
            self.state.daily_returns,
            lookback=settings.corr_lookback_days,
            threshold=settings.corr_threshold,
        )
        checks["correlation"] = {
            "ok": corr.ok,
            "skipped": corr.skipped,
            "max_abs_corr": corr.max_abs_corr,
            "vs_symbol": corr.vs_symbol,
            "threshold": settings.corr_threshold,
            "lookback": corr.lookback,
        }

        if conflict:
            return ValidateResponse(
                approved=False,
                reason="same_symbol_conflict",
                adjusted_position_size=0.0,
                entry=levels.entry,
                stop=levels.stop,
                target=levels.target,
                risk_per_unit=levels.risk_per_unit,
                checks=checks,
            )

        if daily.already_breached:
            return ValidateResponse(
                approved=False,
                reason="daily_loss_limit",
                adjusted_position_size=0.0,
                entry=levels.entry,
                stop=levels.stop,
                target=levels.target,
                risk_per_unit=levels.risk_per_unit,
                checks=checks,
            )

        if not daily.ok:
            # Trade risk would breach remaining budget — reject, suggest fit size.
            return ValidateResponse(
                approved=False,
                reason="daily_loss_limit",
                adjusted_position_size=round(daily.max_additional_size, 8),
                entry=levels.entry,
                stop=levels.stop,
                target=levels.target,
                risk_per_unit=levels.risk_per_unit,
                checks=checks,
            )

        if not corr.ok:
            return ValidateResponse(
                approved=False,
                reason="correlation_threshold",
                adjusted_position_size=0.0,
                entry=levels.entry,
                stop=levels.stop,
                target=levels.target,
                risk_per_unit=levels.risk_per_unit,
                checks=checks,
            )

        if requested is not None and not size_ok:
            return ValidateResponse(
                approved=False,
                reason="position_size_exceeds_limit",
                adjusted_position_size=round(max_size, 8),
                entry=levels.entry,
                stop=levels.stop,
                target=levels.target,
                risk_per_unit=levels.risk_per_unit,
                checks=checks,
            )

        # If daily budget is tighter than 2% risk, shrink (should not happen if daily.ok).
        _ = requested_risk
        return ValidateResponse(
            approved=True,
            reason="ok",
            adjusted_position_size=round(planned, 8),
            entry=levels.entry,
            stop=levels.stop,
            target=levels.target,
            risk_per_unit=levels.risk_per_unit,
            checks=checks,
        )
