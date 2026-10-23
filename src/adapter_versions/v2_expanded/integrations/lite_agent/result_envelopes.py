"""Bounded traversal helpers for truthful Adapter result envelopes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


_ENVELOPE_KEYS = ("adapter_response", "response", "result")


def iter_result_mappings(value: Any, *, max_depth: int = 8) -> Iterator[dict[str, Any]]:
    """Yield mapping layers reachable through standard result-envelope keys."""
    pending: list[Any] = [value]
    seen: set[int] = set()
    for _depth in range(max_depth):
        if not pending:
            return
        next_pending: list[Any] = []
        for candidate in pending:
            if not isinstance(candidate, dict) or id(candidate) in seen:
                continue
            seen.add(id(candidate))
            yield candidate
            for key in _ENVELOPE_KEYS:
                child = candidate.get(key)
                if isinstance(child, dict):
                    next_pending.append(child)
        pending = next_pending


__all__ = ["iter_result_mappings"]
