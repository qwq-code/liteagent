"""Semantic routing for filtered spreadsheet rows inserted into Writer."""

from __future__ import annotations

import re
from typing import Any, Iterable


ACTION = "spreadsheet.insert_matching_rows_into_document"

_SPREADSHEET_SOURCE_RE = re.compile(
    r"(?i)(?:\b(?:csv|ods|spreadsheet|workbook|worksheet|xlsx?)\b|"
    r"\.(?:csv|ods|xlsx)\b)"
)
_WRITER_DESTINATION_RE = re.compile(r"(?i)\b(?:docx?|document|odt|report|writer)\b")
_TABLE_TRANSFER_RE = re.compile(
    r"(?is)\b(?:copy|extract|include|insert|paste|place|transfer)\w*\b"
    r".{0,180}\btable\b|"
    r"\btable\b.{0,180}\b(?:copy|extract|include|insert|paste|place|transfer)\w*\b"
)
_DESTINATION_LOCATION_RE = re.compile(
    r"(?i)\b(?:after|below|into|under|within)\b.{0,100}"
    r"\b(?:heading|paragraph|report|section|title|writer)\b|"
    r"\b(?:heading|paragraph|section|title)\b.{0,100}"
    r"\b(?:after|below|insert|paste|place|under|within)\w*\b"
)
_FILTERED_ROWS_RE = re.compile(
    r"(?is)\b(?:result|row|record|entry)s?\b\s+"
    r"(?:for|of|where|whose|matching|identified\s+by)\b|"
    r"\b(?:for|where|whose|matching|identified\s+by)\b.{0,100}"
    r"\b(?:result|row|record|entry)s?\b"
)


def requests_matching_row_transfer(instruction: str) -> bool:
    """Recognize a selected-row spreadsheet-to-Writer table workflow.

    This predicate classifies only the public workflow. It deliberately does
    not extract a path, header, requested value, table matrix, or destination
    text from the instruction.
    """

    normalized = re.sub(r"\s+", " ", instruction).strip()
    return bool(
        _SPREADSHEET_SOURCE_RE.search(normalized)
        and _WRITER_DESTINATION_RE.search(normalized)
        and _TABLE_TRANSFER_RE.search(normalized)
        and _DESTINATION_LOCATION_RE.search(normalized)
        and _FILTERED_ROWS_RE.search(normalized)
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return the existing parameterized facade for this workflow class."""

    if domain == "multi_apps" and requests_matching_row_transfer(instruction):
        return [ACTION]
    return []


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Remove a redundant source read after truthful spreadsheet grounding."""

    selected = list(actions)
    if (
        str(getattr(state, "domain", "")) != "multi_apps"
        or not requests_matching_row_transfer(str(getattr(state, "instruction", "")))
        or state.successful_action_events(ACTION)
        or not state.successful_action_events("spreadsheet.read_file")
    ):
        return selected
    focused = [action for action in selected if action == ACTION]
    return focused or selected


__all__ = [
    "ACTION",
    "requests_matching_row_transfer",
    "required_actions",
    "stage_actions",
]
