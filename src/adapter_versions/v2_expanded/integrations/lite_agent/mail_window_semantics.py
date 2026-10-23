"""Generic semantics for querying the latest bounded mail window."""

from __future__ import annotations

import re
from typing import Any, Iterable


_COUNT = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_MESSAGE = r"(?:emails?|mail\s+messages?|messages?)"
_LATEST_WINDOW_PATTERNS = (
    re.compile(
        rf"\b(?:latest|newest|most\s+recent)\s+{_COUNT}\s+{_MESSAGE}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:the\s+)?{_COUNT}\s+(?:latest|newest|most\s+recent)\s+{_MESSAGE}\b",
        re.IGNORECASE,
    ),
)


def requests_latest_message_window(instruction: str) -> bool:
    """Return whether a bounded latest/newest message window is requested."""
    normalized = re.sub(r"[-_]", " ", instruction)
    return bool(
        re.search(
            r"\b(?:collect|extract|find|get|list|query|read|retrieve|show)\b",
            normalized,
            re.IGNORECASE,
        )
        and any(pattern.search(normalized) for pattern in _LATEST_WINDOW_PATTERNS)
    )


def requests_spreadsheet_report(instruction: str) -> bool:
    """Return whether the instruction creates a local spreadsheet report."""
    normalized = re.sub(r"[-_]", " ", instruction.casefold())
    return bool(
        re.search(
            r"\b(?:build|create|generate|make|produce|save|store|write)\w*\b",
            normalized,
        )
        and re.search(
            r"\b(?:calc|ods|report|spreadsheet|workbook|xlsx)\b",
            normalized,
        )
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return public actions implied by a latest-mail report workflow."""
    if domain != "multi_apps" or not requests_latest_message_window(instruction):
        return []
    actions = ["mail.query_latest_messages"]
    if requests_spreadsheet_report(instruction):
        actions.append("spreadsheet.create_workbook")
    return actions


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Expose the mail read before a dependent spreadsheet creation."""
    selected = list(actions)
    required = required_actions(str(state.domain), str(state.instruction))
    if not required:
        return selected
    if not state.successful_action_events("mail.query_latest_messages"):
        target = "mail.query_latest_messages"
    elif (
        "spreadsheet.create_workbook" in required
        and not state.successful_action_events("spreadsheet.create_workbook")
    ):
        target = "spreadsheet.create_workbook"
    else:
        return selected
    focused = [action for action in selected if action == target]
    return focused or selected


def completion_errors(state: Any) -> list[str]:
    """Require both public steps when the instruction names both operations."""
    required = required_actions(str(state.domain), str(state.instruction))
    return [
        f"the instruction requires a successful {action} call before completion"
        for action in required
        if not state.successful_action_events(action)
    ]


__all__ = [
    "completion_errors",
    "requests_latest_message_window",
    "requests_spreadsheet_report",
    "required_actions",
    "stage_actions",
]
