"""Generic staging for row-wise concatenation across spreadsheet columns."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .completion_policy import requires_terminal_provenance


CONCATENATE_ACTION = "spreadsheet.concatenate_single_columns"
TERMINAL_ACTION = "spreadsheet.open_in_terminal"
_SPREADSHEET_SUFFIX = re.compile(r"(?i)\.(?:csv|ods|xlsx)\b")


def requests_spreadsheet_column_concatenation(instruction: str) -> bool:
    """Recognize a row-wise join across two or more spreadsheet files."""
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    explicit_sources = len(_SPREADSHEET_SUFFIX.findall(normalized)) >= 2
    plural_sources = bool(
        re.search(
            r"\b(?:two|three|multiple|several)\b.{0,50}"
            r"\b(?:files?|spreadsheets?|workbooks?)\b",
            normalized,
        )
    )
    return bool(
        (explicit_sources or plural_sources)
        and re.search(r"\b(?:column|columns|strings?|values?)\b", normalized)
        and re.search(r"\b(?:concatenate|join|merge)\w*\b", normalized)
        and re.search(
            r"\b(?:corresponding|each|per|row|rows|rowwise|row wise)\b", normalized
        )
    )


def requests_terminal_open(instruction: str) -> bool:
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    return bool(
        re.search(r"\b(?:open|launch|start)\w*\b", normalized)
        and re.search(r"\b(?:calc|libreoffice|spreadsheet|csv)\b", normalized)
        and (
            requires_terminal_provenance(normalized)
            or re.search(
                r"\b(?:open|launch|start)\w*\b.{0,100}"
                r"\b(?:from|in|using|via|with)\s+(?:the\s+)?(?:current\s+)?"
                r"(?:command line|terminal|shell)\b",
                normalized,
            )
        )
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    if domain != "multi_apps" or not requests_spreadsheet_column_concatenation(
        instruction
    ):
        return []
    actions = [CONCATENATE_ACTION]
    if requests_terminal_open(instruction):
        actions.append(TERMINAL_ACTION)
    return actions


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Expose the first incomplete model-owned action in the dependency chain."""
    selected = list(actions)
    required = required_actions(str(state.domain), str(state.instruction))
    target = next(
        (action for action in required if not state.successful_action_events(action)),
        None,
    )
    if target is None:
        return selected
    focused = [action for action in selected if action == target]
    return focused or selected


def completion_errors(state: Any) -> list[str]:
    return [
        f"the instruction requires a successful {action} call before completion"
        for action in required_actions(str(state.domain), str(state.instruction))
        if not state.successful_action_events(action)
    ]


__all__ = [
    "completion_errors",
    "required_actions",
    "requests_spreadsheet_column_concatenation",
    "requests_terminal_open",
    "stage_actions",
]
