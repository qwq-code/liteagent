"""Instruction-only staging for files in the active VS Code workspace."""

from __future__ import annotations

import re
from typing import Any, Iterable


ACTION = "workspace.find_files"
_VSCODE_WORKSPACE = re.compile(
    r"(?i)\b(?:current|opened|the|your)?\s*(?:vs\s*code|vscode)\s+"
    r"(?:project|workspace)\b|"
    r"\b(?:project|workspace)\s+(?:opened\s+)?in\s+(?:vs\s*code|vscode)\b"
)
_FILE_SELECTION = re.compile(
    r"(?i)\b(?:all|each|every|file|files)\b|\.[a-z0-9]{1,12}\b"
)
_FILE_USE = re.compile(
    r"(?i)\b(?:analy[sz]e|combine|concatenate|convert|copy|find|inspect|join|"
    r"merge|open|process|read|run|search|summari[sz]e|transfer|use)\b"
)
_WRITER_BATCH = re.compile(
    r"(?i)\b(?:combine|concatenate|join|merge)\b.*\b(?:docx|document|writer)\b|"
    r"\b(?:docx|document|writer)\b.*\b(?:combine|concatenate|join|merge)\b"
)


def requests_active_workspace_files(instruction: str) -> bool:
    """Return whether an instruction consumes files from the active VS Code project."""
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    return bool(
        _VSCODE_WORKSPACE.search(normalized)
        and _FILE_SELECTION.search(normalized)
        and _FILE_USE.search(normalized)
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    return []


def _contains_matches(value: Any, depth: int = 0) -> bool:
    if not isinstance(value, dict) or depth > 6:
        return False
    matches = value.get("matches")
    if isinstance(matches, list) and bool(matches):
        return True
    return any(
        _contains_matches(value.get(key), depth + 1)
        for key in (
            "adapter_response",
            "context_hint",
            "downstream_context",
            "response",
            "result",
        )
    )


def has_positive_discovery(state: Any) -> bool:
    return any(
        isinstance(getattr(event, "proposed", None), dict)
        and event.proposed.get("kind") == "adapter"
        and event.proposed.get("action") == ACTION
        and getattr(event, "executed", False)
        and not getattr(event, "error", None)
        and _contains_matches(getattr(event, "result", None))
        for event in getattr(state, "events", ())
    )


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Ground active-workspace paths before exposing consuming actions."""
    selected = list(actions)
    positive = has_positive_discovery(state)
    if (
        getattr(state, "domain", None) == "multi_apps"
        and ACTION in selected
        and requests_active_workspace_files(str(getattr(state, "instruction", "")))
        and not positive
    ):
        return [ACTION]
    if positive:
        return [action for action in selected if action != ACTION]
    return selected


def stage_active(state: Any, actions: Iterable[str]) -> bool:
    return bool(
        getattr(state, "domain", None) == "multi_apps"
        and list(actions) == [ACTION]
        and requests_active_workspace_files(str(getattr(state, "instruction", "")))
        and not has_positive_discovery(state)
    )


__all__ = [
    "ACTION",
    "has_positive_discovery",
    "requests_active_workspace_files",
    "required_actions",
    "stage_actions",
    "stage_active",
]
