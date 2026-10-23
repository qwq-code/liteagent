"""Generic Calc column-reorder instruction and result semantics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


_REORDER_CLAUSE_RE = re.compile(
    r"(?is)\b(?:reorder|rearrange|arrange)\s+(?:the\s+)?columns?\b"
    r"(?P<tail>[^.\r\n]{0,320})"
)
_QUOTED_VALUE_RE = re.compile(r'["“]([^"”\r\n]+)["”]')
_NEGATED_REORDER_RE = re.compile(
    r"(?i)\b(?:do\s+not|don't|never|without)\s+(?:reorder|rearrange|arrange)\s*$"
)


@dataclass(frozen=True)
class ColumnReorderIntent:
    headers: tuple[str, ...]


def _normalized_header(value: Any) -> str:
    return " ".join(str(value).split()).casefold()


def parse_column_reorder_intent(instruction: str) -> ColumnReorderIntent | None:
    """Parse an explicit ordered header list without deriving any table coordinates."""
    for match in _REORDER_CLAUSE_RE.finditer(instruction):
        prefix = instruction[max(0, match.start() - 32) : match.start()]
        if _NEGATED_REORDER_RE.search(prefix + match.group(0).split()[0]):
            continue
        headers = tuple(
            value.strip()
            for value in _QUOTED_VALUE_RE.findall(match.group("tail"))
            if value.strip()
        )
        normalized = [_normalized_header(value) for value in headers]
        if len(headers) >= 2 and len(set(normalized)) == len(headers):
            return ColumnReorderIntent(headers=headers)
    return None


def missing_column_reorder_call(
    instruction: str, calls: Iterable[dict[str, Any]]
) -> ColumnReorderIntent | None:
    """Return the unmet intent unless a model-selected call covers it exactly."""
    intent = parse_column_reorder_intent(instruction)
    if intent is None:
        return None
    expected = tuple(_normalized_header(value) for value in intent.headers)
    for arguments in calls:
        headers = arguments.get("headers")
        if not isinstance(headers, list):
            continue
        observed = tuple(_normalized_header(value) for value in headers)
        if observed == expected:
            return None
    return intent


def column_reorder_context(result: dict[str, Any]) -> dict[str, Any] | None:
    """Project a successful Adapter result into compact model-facing evidence."""
    headers = result.get("headers")
    table_range = result.get("range")
    if not isinstance(headers, list) or not headers or not isinstance(table_range, str):
        return None
    blank_edges_preserved = result.get("trimmed_blank_edge_columns") is True
    return {
        key: result.get(key)
        for key in (
            "sheet",
            "requested_range",
            "rows",
            "columns",
            "auto_expanded",
        )
    } | {
        "table_range": table_range,
        "headers": headers,
        "blank_edge_columns_preserved": blank_edges_preserved,
        "guidance": (
            "The selected nonblank table now has the model-selected header order. "
            + (
                "Blank edge columns outside table_range were intentionally preserved as "
                "unrelated cells; do not shift the table or rewrite those cells. "
                if blank_edges_preserved
                else "Cells outside table_range were not part of this operation. "
            )
            + "Save the workbook, perform one read-only structural check, then propose completion."
        ),
    }
