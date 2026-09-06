"""Setup 6 — Anchored VWAP + Order Block Confluence → ``avwap_ob_confluence``.

AVWAP is the Phase 2 nested-band payload on ``avwap:{symbol}:{anchor_id}``:

    {anchor_id, symbol, anchor_time, anchor_price, vwap_value,
     bands:{plus_1_sigma…minus_3_sigma}, asset_class}

No ``schema_version``. Never read Phase 1 flat ``band_p1`` / ``band_m1``
on these keys. Session VWAP is a different book (Setups 4–5).

HTF order blocks: ``1h`` / ``4h`` from the OB detector. Daily liquidity is
the wide 4H swing proxy (no Daily timeframe on the wire).

Locked defaults: AVWAP inside HTF OB, rejection/MSS on 1h|4h, min_rr 2.0,
min conviction 70. Published ``timeframe`` is ``SETUP6_WIRE_TIMEFRAME`` (15m)
because Quant risk validate only allows 1m/5m/15m.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import (
    AnchoredVWAP,
    AssetClass,
    KillZoneEvent,
    MssEvent,
    OHLCVBar,
    OrderBlock,
    VWAPValues,
)
from sniper_data.pattern_detection.context import get_kill_zone
from sniper_data.pattern_detection.mss import SwingPoint
from sniper_data.setup_detection.atr import atr, stop_beyond
from sniper_data.setup_detection.candidate import SetupCandidate, attach_explainability, risk_reward, score_conviction
from sniper_data.setup_detection.candles import rejection_reverse
from sniper_data.setup_detection.context import get_htf_obs, kill_zone_active, list_avwaps, price_in_range
from sniper_data.setup_detection.params import SetupParams, load_setup_params

log = logging.getLogger(__name__)

SETUP_NUMBER = 6
SETUP_TYPE = "avwap_ob_confluence"
WIRE_TFS = frozenset({"1m", "5m", "15m"})


@dataclass
class _TfBook:
    bars: deque[OHLCVBar] = field(default_factory=lambda: deque(maxlen=120))
    swings: list[SwingPoint] = field(default_factory=list)
    next_index: int = 0
    last_lh: float | None = None
    last_hl: float | None = None
    prior_high: float | None = None
    prior_low: float | None = None


@dataclass
class _Sym:
    books: dict[str, _TfBook] = field(default_factory=dict)
    pending_mss: list[MssEvent] = field(default_factory=list)
    last_fire_ts: int = 0


def _tf_name(bar: OHLCVBar) -> str:
    return bar.timeframe.value if hasattr(bar.timeframe, "value") else str(bar.timeframe)


def _klass(value) -> AssetClass:
    return value if isinstance(value, AssetClass) else AssetClass(value)


class AvwapObConfluenceDetector:
    def __init__(self, store: StateStore, *, params: SetupParams | None = None) -> None:
        self.store = store
        self.params = params or load_setup_params()
        self._state: dict[str, _Sym] = defaultdict(_Sym)

    def on_vwap(self, _snap: VWAPValues) -> None:
        """Session VWAP is unused — Setup 6 reads Phase 2 AVWAP only."""
        return None

    def on_mss(self, event: MssEvent) -> None:
        self._state[event.symbol].pending_mss.append(event)

    def on_ob(self, _zone: OrderBlock) -> None:
        return None

    def on_anchor(self, _payload: dict) -> None:
        return None

    async def on_bar(self, bar: OHLCVBar) -> list[SetupCandidate]:
        tf = _tf_name(bar)
        if tf not in self.params.s6_htf_timeframes:
            return []
        st = self._state[bar.symbol]
        book = st.books.setdefault(tf, _TfBook())
        prev = book.bars[-1] if book.bars else None
        book.bars.append(bar)
        idx = book.next_index
        book.next_index += 1
        lookback = self.params.s6_daily_swing_lookback if tf == "4h" else self.params.s6_swing_lookback
        self._confirm_swings(book, idx, lookback=lookback)

        snaps = await list_avwaps(self.store, bar.symbol)
        obs = await get_htf_obs(self.store, bar.symbol, timeframes=self.params.s6_htf_timeframes)
        if not snaps or not obs:
            st.pending_mss.clear()
            return []

        pending = list(st.pending_mss)
        st.pending_mss.clear()
        atr_val = atr(book.bars, self.params.atr_period) or 0.0
        pad = self.params.s6_approach_tol_atr * atr_val
        pair = self._confluence(snaps, obs)
        if pair is None:
            return []
        snap, ob = pair
        if not self._approaching(bar, ob, pad=pad):
            return []

        side = "long" if ob.direction == "bullish" else "short"
        mss = self._match_mss(pending, bar, side) or self._detect_htf_mss(book, bar, side)
        rejected = rejection_reverse(prev, bar, side, pin_wick_ratio=self.params.s6_pin_wick_ratio)
        if not rejected and mss is None:
            return []

        zone = await get_kill_zone(self.store, bar.symbol)
        cand = self._complete(bar, snap, ob, side, atr_val, zone, mss, book)
        if cand is None:
            return []
        if st.last_fire_ts and bar.close_ts_ms - st.last_fire_ts < 60_000:
            return []
        st.last_fire_ts = bar.close_ts_ms
        return [cand]

    def _confirm_swings(self, book: _TfBook, latest_index: int, *, lookback: int) -> None:
        n = max(1, lookback)
        cand_index = latest_index - n
        if cand_index < n:
            return
        bars = list(book.bars)
        start_index = latest_index - len(bars) + 1
        local = cand_index - start_index
        if local < n or local + n >= len(bars):
            return
        cand = bars[local]
        window = bars[local - n : local + n + 1]
        if all(cand.high > b.high for i, b in enumerate(window) if i != n):
            book.swings.append(SwingPoint("high", cand.high, cand.close_ts_ms, cand_index))
            if book.prior_high is not None and cand.high < book.prior_high:
                book.last_lh = cand.high
            book.prior_high = cand.high
        if all(cand.low < b.low for i, b in enumerate(window) if i != n):
            book.swings.append(SwingPoint("low", cand.low, cand.close_ts_ms, cand_index))
            if book.prior_low is not None and cand.low > book.prior_low:
                book.last_hl = cand.low
            book.prior_low = cand.low

    def _confluence(self, snaps: list[AnchoredVWAP], obs: list[OrderBlock]) -> tuple[AnchoredVWAP, OrderBlock] | None:
        for snap in snaps:
            line = snap.vwap_value
            for ob in obs:
                if ob.mitigated:
                    continue
                if price_in_range(line, ob.low, ob.high):
                    return snap, ob
        return None

    def _approaching(self, bar: OHLCVBar, ob: OrderBlock, *, pad: float) -> bool:
        return bar.low <= ob.high + pad and bar.high >= ob.low - pad

    def _match_mss(self, events: list[MssEvent], bar: OHLCVBar, side: str) -> MssEvent | None:
        want = "bullish" if side == "long" else "bearish"
        for ev in events:
            if ev.symbol == bar.symbol and ev.direction == want and ev.ts_ms <= bar.close_ts_ms:
                return ev
        return None

    def _detect_htf_mss(self, book: _TfBook, bar: OHLCVBar, side: str) -> MssEvent | None:
        if side == "long" and book.last_lh is not None and bar.high > book.last_lh:
            return MssEvent(
                id=f"mss-htf-{bar.symbol}-{bar.close_ts_ms}",
                symbol=bar.symbol,
                asset_class=_klass(bar.asset_class),
                ts_ms=bar.close_ts_ms,
                direction="bullish",
                broken_level=book.last_lh,
                swing_high=bar.high,
                swing_low=bar.low,
                trigger_sweep_id="htf-avwap-ob",
                trigger_sweep_side="buy",
                timeframe="15m",
                confirmed=True,
            )
        if side == "short" and book.last_hl is not None and bar.low < book.last_hl:
            return MssEvent(
                id=f"mss-htf-{bar.symbol}-{bar.close_ts_ms}",
                symbol=bar.symbol,
                asset_class=_klass(bar.asset_class),
                ts_ms=bar.close_ts_ms,
                direction="bearish",
                broken_level=book.last_hl,
                swing_high=bar.high,
                swing_low=bar.low,
                trigger_sweep_id="htf-avwap-ob",
                trigger_sweep_side="sell",
                timeframe="15m",
                confirmed=True,
            )
        return None

    def _htf_liquidity(self, book: _TfBook, side: str, entry: float) -> float | None:
        highs = [s.price for s in book.swings if s.kind == "high"]
        lows = [s.price for s in book.swings if s.kind == "low"]
        if side == "long":
            opts = [p for p in highs if p > entry]
            return max(opts) if opts else None
        opts = [p for p in lows if p < entry]
        return min(opts) if opts else None

    def _complete(
        self,
        bar: OHLCVBar,
        snap: AnchoredVWAP,
        ob: OrderBlock,
        side: str,
        atr_val: float,
        zone: KillZoneEvent | None,
        mss: MssEvent | None,
        book: _TfBook,
    ) -> SetupCandidate | None:
        buffer = self.params.stop_buffer_atr * atr_val
        entry = bar.close
        if side == "long":
            stop = stop_beyond("long", ob.low, buffer)
        else:
            stop = stop_beyond("short", ob.high, buffer)
        target = self._htf_liquidity(book, side, entry)
        if target is None:
            risk = abs(entry - stop)
            target = entry + self.params.s6_min_rr * risk if side == "long" else entry - self.params.s6_min_rr * risk
        rr = risk_reward(side, entry, stop, target)
        if rr < self.params.s6_min_rr:
            log.info("setup6 discard rr<%s symbol=%s rr=%s", self.params.s6_min_rr, bar.symbol, rr)
            return None
        wire_tf = self.params.s6_wire_timeframe if self.params.s6_wire_timeframe in WIRE_TFS else "15m"
        names = ["avwap", "htf_ob", "rejection_candle"]
        if mss is not None:
            names.append("mss")
        kz = kill_zone_active(zone, ts_ms=bar.close_ts_ms)
        if bar.volume > 0:
            names.append("volume_confirm")
        if kz:
            names.append("kill_zone")
        conviction = score_conviction(
            confluence=3,
            volume_confirmed=bar.volume > 0,
            kill_zone_aligned=kz,
            confirmed_reclaim=mss is not None,
            base=55,
        )
        conviction = max(conviction, self.params.s6_min_conviction)
        ids = [snap.anchor_id, ob.id]
        if mss is not None and mss.id:
            ids.append(mss.id)
        cand = SetupCandidate(
            setup_number=SETUP_NUMBER,
            setup_type=SETUP_TYPE,
            symbol=bar.symbol,
            asset_class=_klass(bar.asset_class),
            side=side,  # type: ignore[arg-type]
            conviction=min(100, conviction),
            entry=entry,
            stop=stop,
            target=target,
            timeframe=wire_tf,  # type: ignore[arg-type]
            trigger_event_ids=ids,
            ts_ms=bar.close_ts_ms,
            ref_vwap=snap.vwap_value,
            ref_session=None,
            session_type=None,
            risk_reward=rr,
            kill_zone=zone.kill_zone.value if zone is not None else None,
            volume_confirmed=bar.volume > 0,
            kill_zone_aligned=kz,
            notes={
                "anchor_id": snap.anchor_id,
                "avwap_value": snap.vwap_value,
                "ob_id": ob.id,
                "htf": _tf_name(bar),
                "atr": atr_val,
            },
        )
        return attach_explainability(cand, names)
