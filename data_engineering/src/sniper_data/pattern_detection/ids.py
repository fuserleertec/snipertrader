"""Deterministic zone / event ids (no colons — Redis uses colon separators)."""

from __future__ import annotations


def make_id(*parts: object) -> str:
    tokens = [str(p).replace(":", "-") for p in parts if p is not None and str(p) != ""]
    return "-".join(tokens)
