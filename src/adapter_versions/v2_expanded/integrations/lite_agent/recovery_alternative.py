"""One-turn recovery filtering for model-requested alternative actions."""

from __future__ import annotations

import re
from typing import Any, Iterable


_ALTERNATIVE_QUERY = re.compile(
    r"(?i)\b(?:alternative|alternatives|alternate|another|different|instead|"
    r"other|replacement|substitute)\b"
)


def _latest_alternative_search(state: Any) -> Any | None:
    events = getattr(state, "events", None)
    if not events:
        return None
    latest = events[-1]
    proposed = getattr(latest, "proposed", None)
    arguments = proposed.get("arguments") if isinstance(proposed, dict) else None
    query = arguments.get("query") if isinstance(arguments, dict) else None
    if (
        not getattr(latest, "executed", False)
        or not isinstance(proposed, dict)
        or proposed.get("kind") != "catalog"
        or not isinstance(query, str)
        or not _ALTERNATIVE_QUERY.search(query)
    ):
        return None
    return latest


def blocked_actions_for_requested_alternative(state: Any) -> set[str]:
    """Return current blocked actions only after an immediate alternative search."""
    if _latest_alternative_search(state) is None:
        return set()
    active_blocks = getattr(state, "active_request_blocks", None)
    if not callable(active_blocks):
        return set()
    blocks = active_blocks()
    if not isinstance(blocks, dict):
        return set()
    return {
        action
        for block in blocks.values()
        if isinstance(block, dict)
        and isinstance((action := block.get("action")), str)
        and action
        and action != "adapter.call"
    }


def filter_requested_alternative_actions(
    state: Any, actions: Iterable[str]
) -> list[str]:
    """Omit disproven actions without choosing among the remaining alternatives."""
    blocked = blocked_actions_for_requested_alternative(state)
    return [action for action in actions if action not in blocked]


__all__ = [
    "blocked_actions_for_requested_alternative",
    "filter_requested_alternative_actions",
]
