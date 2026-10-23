from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Sequence

from .semantic_tables import SemanticTableError


AGGREGATIONS = frozenset({"sum", "count", "average", "max", "min"})
_NUMERIC_AGGREGATIONS = frozenset({"sum", "average", "max", "min"})


@dataclass(frozen=True)
class StackedAggregateFields:
    group_fields: tuple[str, ...]
    value_field: str
    aggregation: str


def _rectangular_width(matrix: Sequence[Sequence[Any]], *, name: str) -> int:
    if not matrix or not matrix[0]:
        raise SemanticTableError(f"{name} must be a non-empty rectangular matrix")
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise SemanticTableError(f"{name} must be rectangular")
    return width


def _semantic_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _resolve_header(headers: Sequence[str], selector: str) -> str:
    requested = selector.strip()
    exact = [
        header
        for header in headers
        if header.strip().casefold() == requested.casefold()
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise SemanticTableError(f"header selector is ambiguous: {selector}")

    key = _semantic_key(requested)
    if not key:
        raise SemanticTableError(f"header selector has no searchable text: {selector}")
    equivalent = [header for header in headers if _semantic_key(header) == key]
    if len(equivalent) == 1:
        return equivalent[0]
    if not equivalent:
        raise SemanticTableError(f"header selector was not found: {selector}")
    raise SemanticTableError(f"header selector is ambiguous: {selector}")


def resolve_stacked_aggregate_fields(
    display_text: Sequence[Sequence[Any]],
    kinds: Sequence[Sequence[str]],
    *,
    group_selectors: Sequence[str],
    value_selector: str,
    aggregation: str,
) -> StackedAggregateFields:
    """Resolve model selectors against one live table before creating any pivots."""
    width = _rectangular_width(display_text, name="display_text")
    if _rectangular_width(kinds, name="kinds") != width or len(kinds) != len(
        display_text
    ):
        raise SemanticTableError("display_text and kinds must have identical geometry")
    if len(display_text) < 2:
        raise SemanticTableError("source table needs one header row and one data row")
    if not group_selectors:
        raise SemanticTableError("group_selectors must not be empty")

    headers = [str(value).strip() for value in display_text[0]]
    if any(not header for header in headers):
        raise SemanticTableError("source table headers must not be blank")

    normalized_aggregation = aggregation.strip().casefold()
    if normalized_aggregation not in AGGREGATIONS:
        raise SemanticTableError(f"unsupported aggregation: {aggregation}")

    group_fields = tuple(
        _resolve_header(headers, str(selector)) for selector in group_selectors
    )
    if len(set(group_fields)) != len(group_fields):
        raise SemanticTableError("group selectors must resolve to unique headers")
    value_field = _resolve_header(headers, value_selector)
    if value_field in group_fields:
        raise SemanticTableError("value field must differ from every group field")

    value_column = headers.index(value_field)
    populated_kinds = [
        str(row[value_column]).casefold()
        for display_row, row in zip(display_text[1:], kinds[1:])
        if str(display_row[value_column]).strip()
    ]
    if not populated_kinds:
        raise SemanticTableError("value field contains no populated data")
    if normalized_aggregation in _NUMERIC_AGGREGATIONS and any(
        kind not in {"number", "formula"} for kind in populated_kinds
    ):
        raise SemanticTableError(
            f"value field must contain only numeric or formula data for {normalized_aggregation}"
        )

    return StackedAggregateFields(
        group_fields=group_fields,
        value_field=value_field,
        aggregation=normalized_aggregation,
    )
