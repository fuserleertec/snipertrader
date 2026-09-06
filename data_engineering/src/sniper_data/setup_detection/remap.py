"""Copy fixture models onto another symbol (uppercase, inferred asset class)."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from sniper_data.symbols import infer_asset_class, normalize_symbol

T = TypeVar("T")

_ID_FIELDS = (
    "id",
    "trigger_sweep_id",
    "trigger_event_ids",
    "anchor_id",
)


def remap_model(model: T, symbol: str) -> T:
    """Return a copy of ``model`` pointed at ``symbol`` (unique ids)."""
    sym = normalize_symbol(symbol)
    klass = infer_asset_class(sym)
    if isinstance(model, BaseModel):
        updates: dict[str, Any] = {}
        data = model.model_dump()
        if "symbol" in data:
            updates["symbol"] = sym
        if "asset_class" in data:
            updates["asset_class"] = klass
        if "id" in data and data["id"]:
            updates["id"] = f"{data['id']}-{sym}"
        if "trigger_sweep_id" in data and data["trigger_sweep_id"]:
            updates["trigger_sweep_id"] = f"{data['trigger_sweep_id']}-{sym}"
        if "trigger_event_ids" in data and data["trigger_event_ids"]:
            updates["trigger_event_ids"] = [f"{x}-{sym}" for x in data["trigger_event_ids"]]
        if "anchor_id" in data and data["anchor_id"]:
            updates["anchor_id"] = f"{data['anchor_id']}-{sym}"
        return model.model_copy(update=updates)
    return model


def remap_many(items: list[T], symbol: str) -> list[T]:
    return [remap_model(item, symbol) for item in items]
