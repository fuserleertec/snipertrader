"""Anchored VWAP (Phase 2).

Redis public key: ``avwap:{symbol}:{anchor_id}``
Wire payload matches ``schemas/avwap.schema.json`` exactly (no schema_version).

σ uses the same volume-weighted variance as Phase 1:

    σ = sqrt( Σ v_i (p_i − VWAP)² / Σ v_i )
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from sniper_data.bus.redis_store import StateStore
from sniper_data.models import (
    AVWAPBands,
    AnchorMeta,
    AnchorRegistration,
    AnchorSource,
    AnchoredVWAP,
    AssetClass,
)
from sniper_data.symbols import infer_asset_class, normalize_symbol
from sniper_data.vwap import _Accumulator


def redis_avwap_key(symbol: str, anchor_id: str) -> str:
    return f"avwap:{symbol}:{anchor_id}"


def redis_avwap_meta_key(symbol: str, anchor_id: str) -> str:
    return f"avwap:meta:{symbol}:{anchor_id}"


def redis_avwap_acc_key(symbol: str, anchor_id: str) -> str:
    return f"avwap:acc:{symbol}:{anchor_id}"


def redis_avwap_index_key(symbol: str) -> str:
    return f"avwap:index:{symbol}"


def redis_avwap_latest_key(symbol: str) -> str:
    return f"avwap:latest:{symbol}"


def redis_avwap_channel(symbol: str) -> str:
    return f"avwap:{symbol}"


def bands_from_sigma(vwap: float, sigma: float) -> AVWAPBands:
    return AVWAPBands(
        plus_1_sigma=vwap + 1 * sigma,
        plus_2_sigma=vwap + 2 * sigma,
        plus_3_sigma=vwap + 3 * sigma,
        minus_1_sigma=vwap - 1 * sigma,
        minus_2_sigma=vwap - 2 * sigma,
        minus_3_sigma=vwap - 3 * sigma,
    )


def to_wire(snap: AnchoredVWAP) -> dict:
    """Exact Phase 2 JSON (field names only)."""
    return snap.model_dump(mode="json")


@dataclass
class _AnchorState:
    meta: AnchorMeta
    acc: _Accumulator = field(default_factory=_Accumulator)


class AnchoredVWAPEngine:
    """In-process accumulators; Redis is the shared source of truth for workers."""

    def __init__(self, max_anchors_per_symbol: int = 32) -> None:
        self.max_anchors_per_symbol = max_anchors_per_symbol
        self._state: dict[str, dict[str, _AnchorState]] = {}

    def register(self, req: AnchorRegistration, *, created_ts_ms: int | None = None) -> AnchorMeta:
        symbol = normalize_symbol(req.symbol)
        klass = infer_asset_class(symbol, req.asset_class)
        anchor_id = req.anchor_id or str(uuid.uuid4())
        bucket = self._state.setdefault(symbol, {})
        existing = bucket.get(anchor_id)
        if existing is not None:
            return existing.meta
        meta = AnchorMeta(
            anchor_id=anchor_id,
            symbol=symbol,
            anchor_time=int(req.anchor_time),
            anchor_price=float(req.anchor_price),
            source=req.source,
            asset_class=klass,
            created_ts_ms=created_ts_ms if created_ts_ms is not None else int(time.time() * 1000),
        )
        bucket[anchor_id] = _AnchorState(meta=meta)
        self._evict_overflow(symbol)
        return meta

    def _evict_overflow(self, symbol: str) -> None:
        bucket = self._state.get(symbol, {})
        if len(bucket) <= self.max_anchors_per_symbol:
            return
        ordered = sorted(bucket.values(), key=lambda s: (s.meta.anchor_time, s.meta.created_ts_ms))
        for stale in ordered[: len(bucket) - self.max_anchors_per_symbol]:
            bucket.pop(stale.meta.anchor_id, None)

    def known(self, symbol: str) -> list[AnchorMeta]:
        return [s.meta for s in self._state.get(symbol, {}).values()]

    def get(self, symbol: str, anchor_id: str) -> _AnchorState | None:
        return self._state.get(symbol, {}).get(anchor_id)

    def on_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        ts_ms: int,
        asset_class: AssetClass | str | None = None,
    ) -> list[AnchoredVWAP]:
        klass = infer_asset_class(symbol, asset_class)
        out: list[AnchoredVWAP] = []
        for state in self._state.get(symbol, {}).values():
            if ts_ms < state.meta.anchor_time:
                continue
            state.acc.add(price, volume)
            snap = self._snapshot(state, klass)
            if snap is not None:
                out.append(snap)
        return out

    def _snapshot(self, state: _AnchorState, klass: AssetClass) -> AnchoredVWAP | None:
        pair = state.acc.snapshot()
        if pair is None:
            return None
        vwap, sigma = pair
        return AnchoredVWAP(
            anchor_id=state.meta.anchor_id,
            symbol=state.meta.symbol,
            anchor_time=state.meta.anchor_time,
            anchor_price=state.meta.anchor_price,
            vwap_value=vwap,
            bands=bands_from_sigma(vwap, sigma),
            asset_class=klass,
        )

    def acc_payload(self, symbol: str, anchor_id: str) -> dict | None:
        state = self.get(symbol, anchor_id)
        if state is None:
            return None
        return {
            "weight": state.acc.weight,
            "price_vol": state.acc.price_vol,
            "price_sq_vol": state.acc.price_sq_vol,
            "n_obs": state.acc.n_obs,
        }

    def load_acc(self, symbol: str, anchor_id: str, payload: dict) -> None:
        state = self.get(symbol, anchor_id)
        if state is None:
            return
        state.acc.weight = float(payload.get("weight") or 0.0)
        state.acc.price_vol = float(payload.get("price_vol") or 0.0)
        state.acc.price_sq_vol = float(payload.get("price_sq_vol") or 0.0)
        state.acc.n_obs = int(payload.get("n_obs") or 0)


async def index_ids(store: StateStore, symbol: str) -> list[str]:
    raw = await store.get(redis_avwap_index_key(symbol))
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


async def index_add(store: StateStore, symbol: str, anchor_id: str) -> None:
    ids = await index_ids(store, symbol)
    if anchor_id not in ids:
        ids.append(anchor_id)
        await store.set(redis_avwap_index_key(symbol), ids)


async def persist_anchor(store: StateStore, meta: AnchorMeta) -> None:
    await store.set(redis_avwap_meta_key(meta.symbol, meta.anchor_id), meta)
    await index_add(store, meta.symbol, meta.anchor_id)


async def persist_avwap(
    store: StateStore,
    snap: AnchoredVWAP,
    acc: dict | None = None,
) -> None:
    payload = to_wire(snap)
    await store.set(redis_avwap_key(snap.symbol, snap.anchor_id), payload)
    await store.set(redis_avwap_latest_key(snap.symbol), payload)
    if acc is not None:
        await store.set(redis_avwap_acc_key(snap.symbol, snap.anchor_id), acc)
    await store.publish(redis_avwap_channel(snap.symbol), payload)


async def sync_anchors_from_store(
    engine: AnchoredVWAPEngine,
    store: StateStore,
    symbol: str,
) -> list[AnchorMeta]:
    """Load Redis-registered anchors the local worker does not yet know."""
    added: list[AnchorMeta] = []
    for anchor_id in await index_ids(store, symbol):
        if engine.get(symbol, anchor_id) is not None:
            continue
        raw = await store.get(redis_avwap_meta_key(symbol, anchor_id))
        if not isinstance(raw, dict):
            continue
        meta = AnchorMeta.model_validate(raw)
        engine.register(
            AnchorRegistration(
                symbol=meta.symbol,
                anchor_time=meta.anchor_time,
                anchor_price=meta.anchor_price,
                source=meta.source,
                asset_class=meta.asset_class,
                anchor_id=meta.anchor_id,
            ),
            created_ts_ms=meta.created_ts_ms,
        )
        acc = await store.get(redis_avwap_acc_key(symbol, anchor_id))
        if isinstance(acc, dict):
            engine.load_acc(symbol, anchor_id, acc)
        added.append(meta)
    return added


async def register_anchor(
    engine: AnchoredVWAPEngine,
    store: StateStore,
    req: AnchorRegistration,
) -> AnchorMeta:
    meta = engine.register(req)
    await persist_anchor(store, meta)
    return meta
