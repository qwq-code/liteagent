"""Semantic routing for filling blank presentation notes from a document."""

from __future__ import annotations

import re
from typing import Any, Iterable


ACTION = "presentation.fill_missing_notes_from_document"

_PRESENTATION_RE = re.compile(
    r"(?i)(?:\b(?:deck|impress|powerpoint|presentation|slides?)\b|\.(?:odp|pptx?)\b)"
)
_NOTES_SOURCE_RE = re.compile(
    r"(?is)\b(?:planned\s+remarks?|presenter\s+(?:notes?|plan)|speaker\s+notes?|"
    r"speaking\s+notes?|remarks?)\b.{0,160}\b(?:desktop|docx?|document|file|word)\b|"
    r"\b(?:desktop|docx?|document|file|word)\b.{0,160}\b(?:planned\s+remarks?|"
    r"presenter\s+(?:notes?|plan)|speaker\s+notes?|speaking\s+notes?|remarks?)\b"
)
_TRANSFER_RE = re.compile(
    r"(?i)\b(?:add|complete|copy|fill|import|insert|place|transfer|use)\w*\b"
)
_MISSING_ONLY_RE = re.compile(
    r"(?is)\b(?:blank|empty|incomplete|missing|remaining|unfinished)\b|"
    r"\b(?:already|existing|previously)\b.{0,100}\b(?:complete|completed|filled|notes?)\b|"
    r"\b(?:complete|completed|filled|notes?)\b.{0,100}\b(?:already|existing|previously)\b"
)


def requests_missing_notes_transfer(instruction: str) -> bool:
    """Recognize the reusable document-to-blank-slide-notes workflow."""

    normalized = re.sub(
        r"\s+",
        " ",
        re.sub(r"[-_]+", " ", instruction),
    ).strip()
    return bool(
        _PRESENTATION_RE.search(normalized)
        and _NOTES_SOURCE_RE.search(normalized)
        and _TRANSFER_RE.search(normalized)
        and _MISSING_ONLY_RE.search(normalized)
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    if domain == "multi_apps" and requests_missing_notes_transfer(instruction):
        return [ACTION]
    return []


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """After live presentation grounding, expose only the workflow facade."""

    selected = list(actions)
    if (
        str(getattr(state, "domain", "")) != "multi_apps"
        or not requests_missing_notes_transfer(str(getattr(state, "instruction", "")))
        or state.successful_action_events(ACTION)
        or not state.successful_action_events("presentation.inspect_current")
    ):
        return selected
    focused = [action for action in selected if action == ACTION]
    return focused or selected


__all__ = [
    "ACTION",
    "requests_missing_notes_transfer",
    "required_actions",
    "stage_actions",
]
