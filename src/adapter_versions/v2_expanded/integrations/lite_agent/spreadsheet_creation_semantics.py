"""Generic lifecycle for a header-first spreadsheet creation."""

from __future__ import annotations

from typing import Any, Iterable


CREATE_ACTION = "spreadsheet.create_workbook"
WRITE_ACTION = "spreadsheet.write_range"


def _arguments(event: Any) -> dict[str, Any]:
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return {}
    arguments = proposed.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def pending_header_first_creation(state: Any) -> Any | None:
    """Return the latest header-only create that has no later successful data write."""
    creates = list(state.successful_action_events(CREATE_ACTION))
    if not creates:
        return None
    latest = creates[-1]
    arguments = _arguments(latest)
    if "headers" not in arguments or "rows" in arguments:
        return None
    if any(
        event.step > latest.step
        for event in state.successful_action_events(WRITE_ACTION)
    ):
        return None
    return latest


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Expose the model-owned range write while a header-first workbook is incomplete."""
    selected = list(actions)
    if pending_header_first_creation(state) is None:
        return selected
    return [WRITE_ACTION]


def completion_errors(state: Any) -> list[str]:
    if pending_header_first_creation(state) is None:
        return []
    return [
        "the header-only spreadsheet.create_workbook call requires a later successful "
        "model-selected spreadsheet.write_range call before completion"
    ]


__all__ = [
    "CREATE_ACTION",
    "WRITE_ACTION",
    "completion_errors",
    "pending_header_first_creation",
    "stage_actions",
]
