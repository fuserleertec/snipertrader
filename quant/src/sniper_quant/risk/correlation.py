"""60-day rolling Pearson correlation filter against open positions."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrelationCheck:
    ok: bool
    skipped: bool
    max_abs_corr: float | None
    vs_symbol: str | None
    lookback: int


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    a = xs[-n:]
    b = ys[-n:]
    mx = sum(a) / n
    my = sum(b) / n
    num = sum((x - mx) * (y - my) for x, y in zip(a, b))
    denx = math.sqrt(sum((x - mx) ** 2 for x in a))
    deny = math.sqrt(sum((y - my) ** 2 for y in b))
    if denx <= 0 or deny <= 0:
        return None
    return num / (denx * deny)


def correlation_check(
    candidate_symbol: str,
    open_symbols: list[str],
    daily_returns: dict[str, list[float]],
    *,
    lookback: int = 60,
    threshold: float = 0.70,
    min_overlap: int = 20,
) -> CorrelationCheck:
    """Reject when |ρ| vs any open symbol exceeds ``threshold``.

    Same-symbol is a conflict check, not a correlation check — skip self.
    Insufficient history → skipped (ok=True) so the in-memory demo can run.
    """
    cand = candidate_symbol.upper()
    peers = [s.upper() for s in open_symbols if s.upper() != cand]
    if not peers:
        return CorrelationCheck(ok=True, skipped=True, max_abs_corr=None, vs_symbol=None, lookback=lookback)

    series = daily_returns.get(cand) or daily_returns.get(candidate_symbol)
    if not series:
        return CorrelationCheck(ok=True, skipped=True, max_abs_corr=None, vs_symbol=None, lookback=lookback)

    worst: float | None = None
    worst_sym: str | None = None
    for peer in peers:
        other = daily_returns.get(peer)
        if not other:
            continue
        window_a = series[-lookback:]
        window_b = other[-lookback:]
        n = min(len(window_a), len(window_b))
        if n < min_overlap:
            continue
        rho = pearson(window_a[-n:], window_b[-n:])
        if rho is None:
            continue
        mag = abs(rho)
        if worst is None or mag > worst:
            worst = mag
            worst_sym = peer

    if worst is None:
        return CorrelationCheck(ok=True, skipped=True, max_abs_corr=None, vs_symbol=None, lookback=lookback)
    return CorrelationCheck(
        ok=worst <= threshold + 1e-12,
        skipped=False,
        max_abs_corr=worst,
        vs_symbol=worst_sym,
        lookback=lookback,
    )
