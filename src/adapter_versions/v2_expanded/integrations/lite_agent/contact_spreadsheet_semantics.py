"""Generic semantics for contact export followed by spreadsheet conversion."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .completion_policy import requires_terminal_provenance


_SPREADSHEET_FORMAT_RE = re.compile(
    r"(?i)(?<![a-z0-9])\.?((?:csv|ods|xlsx))(?![a-z0-9])"
)
_CONTACT_EXPORT_VERB_RE = re.compile(
    r"(?i)\b(?:export(?:ed|ing|s)?|sav(?:e|ed|es|ing))\b"
)


def _spreadsheet_formats(instruction: str) -> set[str]:
    return {
        match.group(1).casefold()
        for match in _SPREADSHEET_FORMAT_RE.finditer(instruction)
    }


def requests_contact_csv_export(instruction: str) -> bool:
    """Return whether the instruction explicitly exports an address book to CSV."""
    normalized = re.sub(r"[-_]", " ", instruction.casefold())
    return bool(
        _CONTACT_EXPORT_VERB_RE.search(normalized)
        and re.search(
            r"\b(?:contacts?|address\s+books?|collected\s+addresses)\b",
            normalized,
        )
        and "csv" in _spreadsheet_formats(normalized)
    )


def requests_spreadsheet_file_conversion(instruction: str) -> bool:
    """Return whether one local spreadsheet format is converted to another."""
    normalized = re.sub(r"[-_]", " ", instruction.casefold())
    return bool(
        re.search(r"\b(?:convert|conversion|transform)\b", normalized)
        and len(_spreadsheet_formats(normalized)) >= 2
    )


def requests_command_line_spreadsheet_conversion(instruction: str) -> bool:
    """Return whether conversion must be performed through a terminal command."""
    return requests_spreadsheet_file_conversion(
        instruction
    ) and requires_terminal_provenance(instruction)


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return owning-Adapter action hints for adapter.call catalog search."""
    if domain != "multi_apps":
        return []
    actions: list[str] = []
    if requests_contact_csv_export(instruction):
        actions.append("contacts.export_csv")
    if requests_spreadsheet_file_conversion(instruction):
        actions.append(
            "command.run"
            if requests_command_line_spreadsheet_conversion(instruction)
            else "document.convert"
        )
    return actions


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Keep the generic adapter.call surface selected by normal orchestration."""
    return list(actions)


__all__ = [
    "requests_contact_csv_export",
    "requests_command_line_spreadsheet_conversion",
    "requests_spreadsheet_file_conversion",
    "required_actions",
    "stage_actions",
]
