"""Generic Calc fill-down target semantics for strict episodes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .adapter_results import a1_geometry, column_label, column_number


_FILL_COLUMNS_RE = re.compile(
    r"(?is)\bfill(?:\s+(?:out|down))?\b(?P<body>[^.;\r\n]{0,180}?)"
    r"\bcolumns?\s+(?P<columns>[^.;\r\n]{1,100}?)"
    r"(?=\b(?:next|then)\b|[.;\r\n]|$)"
)
_NEGATED_FILL_RE = re.compile(
    r"(?i)\b(?:do\s+not|don't|never|without)\s+fill(?:\s+(?:out|down))?\s*$"
)
_COLUMN_SPAN_RE = re.compile(
    r"(?i)^\s*([A-Z]{1,3})\s*(?:to|through|thru|[-–:])\s*([A-Z]{1,3})\s*$"
)
_COLUMN_TOKEN_RE = re.compile(r"(?<![A-Za-z])([A-Z]{1,3})(?![A-Za-z])")
_ROW_RE = re.compile(r"(?i)\brow\s+(\d+)\b")


@dataclass(frozen=True)
class FillDownIntent:
    columns: tuple[str, ...]
    seed_row: int | None
    contiguous: bool


def parse_fill_down_intent(instruction: str) -> FillDownIntent | None:
    """Parse explicitly named spreadsheet columns without deriving a target range."""
    for match in _FILL_COLUMNS_RE.finditer(instruction):
        prefix = instruction[max(0, match.start() - 40) : match.start()]
        if _NEGATED_FILL_RE.search(prefix + "fill"):
            continue
        expression = match.group("columns").strip()
        span = _COLUMN_SPAN_RE.fullmatch(expression)
        if span is not None:
            start, end = (value.upper() for value in span.groups())
            start_number = column_number(start)
            end_number = column_number(end)
            if start_number > end_number:
                continue
            columns = tuple(
                column_label(number) for number in range(start_number, end_number + 1)
            )
            contiguous = True
        else:
            columns = tuple(dict.fromkeys(_COLUMN_TOKEN_RE.findall(expression)))
            contiguous = False
        if not columns:
            continue
        nearby = instruction[max(0, match.start() - 180) : match.end()]
        row_matches = _ROW_RE.findall(nearby)
        seed_row = int(row_matches[-1]) if row_matches else None
        return FillDownIntent(
            columns=columns,
            seed_row=seed_row,
            contiguous=contiguous,
        )
    return None


def missing_fill_down_columns(
    instruction: str, calls: Iterable[dict[str, Any]]
) -> tuple[str, ...]:
    """Return explicit target columns not covered by successful model-selected calls."""
    intent = parse_fill_down_intent(instruction)
    if intent is None:
        return ()
    expected = set(intent.columns)
    covered: set[str] = set()
    for arguments in calls:
        geometry = a1_geometry(str(arguments.get("range", "")))
        if geometry is None:
            continue
        start_column, start_row, end_column, end_row = geometry
        if end_row <= start_row or (
            intent.seed_row is not None and start_row != intent.seed_row
        ):
            continue
        call_columns = {
            column_label(number)
            for number in range(
                column_number(start_column), column_number(end_column) + 1
            )
        }
        if not intent.contiguous and not call_columns.issubset(expected):
            continue
        covered.update(call_columns.intersection(expected))
    return tuple(column for column in intent.columns if column not in covered)
