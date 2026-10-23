"""Strict generic semantics for replacing one complete Impress table row."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


ACTION = "table.replace_row"
_ORDINAL_ROWS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}
_ROW_RE = re.compile(
    r"(?i)\b(?:change|replace|set|update)\s+(?:the\s+)?"
    r"(?:(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+row|"
    r"row\s+(\d+)(?:st|nd|rd|th)?)\b"
)
_SLIDE_RE = re.compile(r"(?i)\b(?:on|in)\s+(?:the\s+)?(?:slide|page)\s+(\d+)\b")
_VALUE_RE = re.compile(r'["“]([^"”\r\n]+)["”]')


@dataclass(frozen=True)
class TableRowIntent:
    slide_number: int
    row_number: int
    values: tuple[str, ...]

    def arguments(self) -> dict[str, Any]:
        return {
            "slide_number": self.slide_number,
            "row_number": self.row_number,
            "values": list(self.values),
        }


def parse_table_row_intent(instruction: str) -> TableRowIntent | None:
    row_match = _ROW_RE.search(instruction)
    slide_match = _SLIDE_RE.search(instruction)
    values = tuple(_VALUE_RE.findall(instruction))
    if row_match is None or slide_match is None or not values:
        return None
    slide_number = int(slide_match.group(1))
    row_number = (
        _ORDINAL_ROWS[row_match.group(1).casefold()]
        if row_match.group(1) is not None
        else int(row_match.group(2))
    )
    if slide_number < 1 or row_number < 1:
        return None
    return TableRowIntent(slide_number, row_number, values)


def required_actions(domain: str, instruction: str) -> list[str]:
    if domain != "libreoffice_impress":
        return []
    return [ACTION] if parse_table_row_intent(instruction) is not None else []


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    if action != ACTION:
        return []
    intent = parse_table_row_intent(str(state.instruction))
    if intent is None:
        return []
    expected = intent.arguments()
    if arguments == expected:
        return []
    return [
        "table.replace_row must use the exact one-based slide_number, one-based "
        "row_number, and complete left-to-right values explicitly requested by the "
        f"instruction; expected fields are {sorted(expected)}"
    ]


def _mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mappings(child)


def _confirmed_result(event: Any, state: Any) -> bool:
    arguments = event.proposed.get("arguments")
    if not isinstance(arguments, dict) or argument_contract_errors(
        state, ACTION, arguments
    ):
        return False
    return any(
        candidate.get("display_slide_number") == arguments["slide_number"]
        and candidate.get("row_number") == arguments["row_number"]
        and candidate.get("values") == arguments["values"]
        and candidate.get("actual_values") == arguments["values"]
        and candidate.get("verification_passed") is True
        and isinstance(candidate.get("path"), list)
        and isinstance(candidate.get("rows"), int)
        and isinstance(candidate.get("columns"), int)
        and candidate.get("columns") == len(arguments["values"])
        for candidate in _mappings(event.result)
    )


def requirement_errors(state: Any) -> list[str]:
    if parse_table_row_intent(str(state.instruction)) is None:
        return []
    if any(
        _confirmed_result(event, state)
        for event in state.successful_action_events(ACTION)
    ):
        return []
    return [
        "table.replace_row lacks Adapter-confirmed live-table resolution and exact "
        "row read-back for the requested model-selected values"
    ]


def search_relevance_bonus(action: str, query: str, instruction: str = "") -> int:
    if action != ACTION:
        return 0
    text = f"{query}\n{instruction}"
    return 1_000 if parse_table_row_intent(text) is not None else 0


__all__ = [
    "ACTION",
    "TableRowIntent",
    "argument_contract_errors",
    "parse_table_row_intent",
    "required_actions",
    "requirement_errors",
    "search_relevance_bonus",
]
