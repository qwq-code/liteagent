"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


from .adapter_results import (
    adapter_context_hint as adapter_context_hint,
    compact_adapter_body as compact_adapter_body,
)
from .completion_policy import (
    completion_claim_contradictions as completion_claim_contradictions,
)


def first_display_row(value: Any) -> list[str]:
    if isinstance(value, dict):
        display_text = value.get("display_text")
        if (
            isinstance(display_text, list)
            and display_text
            and isinstance(display_text[0], list)
        ):
            return [str(item) for item in display_text[0]]
        if value.get("truncated") and isinstance(value.get("preview"), str):
            preview = value["preview"]
            marker = preview.find('"display_text"')
            outer_start = preview.find("[", marker)
            row_start = preview.find("[", outer_start + 1)
            if marker >= 0 and row_start >= 0:
                try:
                    row, _end = json.JSONDecoder().raw_decode(preview, row_start)
                    if isinstance(row, list):
                        return [str(item) for item in row]
                except (ValueError, json.JSONDecodeError):
                    pass
        for nested in value.values():
            row = first_display_row(nested)
            if row:
                return row
    elif isinstance(value, list):
        for nested in value:
            row = first_display_row(nested)
            if row:
                return row
    return []


def display_rows(value: Any) -> list[list[str]]:
    if isinstance(value, dict):
        display_text = value.get("display_text")
        if isinstance(display_text, list) and all(
            isinstance(row, list) for row in display_text
        ):
            return [[str(item) for item in row] for row in display_text]
        if value.get("truncated") and isinstance(value.get("preview"), str):
            preview = value["preview"]
            marker = preview.find('"display_text"')
            outer_start = preview.find("[", marker)
            if marker >= 0 and outer_start >= 0:
                try:
                    rows, _end = json.JSONDecoder().raw_decode(preview, outer_start)
                    if isinstance(rows, list) and all(
                        isinstance(row, list) for row in rows
                    ):
                        return [[str(item) for item in row] for row in rows]
                except (ValueError, json.JSONDecodeError):
                    pass
        for nested in value.values():
            rows = display_rows(nested)
            if rows:
                return rows
    elif isinstance(value, list):
        for nested in value:
            rows = display_rows(nested)
            if rows:
                return rows
    return []


def matrix_field(value: Any, field: str) -> list[list[Any]]:
    if isinstance(value, dict):
        matrix = value.get(field)
        if isinstance(matrix, list) and all(isinstance(row, list) for row in matrix):
            return matrix
        if value.get("truncated") and isinstance(value.get("preview"), str):
            preview = value["preview"]
            marker = re.search(rf'"{re.escape(field)}"\s*:\s*', preview)
            if marker is not None:
                try:
                    matrix, _end = json.JSONDecoder().raw_decode(preview, marker.end())
                    if isinstance(matrix, list) and all(
                        isinstance(row, list) for row in matrix
                    ):
                        return matrix
                except (ValueError, json.JSONDecodeError):
                    pass
        for nested in value.values():
            found = matrix_field(nested, field)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = matrix_field(nested, field)
            if found:
                return found
    return []


def mapping_field(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, dict):
        mapping = value.get(field)
        if isinstance(mapping, dict):
            return dict(mapping)
        if value.get("truncated") and isinstance(value.get("preview"), str):
            preview = value["preview"]
            marker = re.search(rf'"{re.escape(field)}"\s*:\s*', preview)
            if marker is not None:
                try:
                    parsed, _end = json.JSONDecoder().raw_decode(preview, marker.end())
                    if isinstance(parsed, dict):
                        return dict(parsed)
                except (ValueError, json.JSONDecodeError):
                    pass
        for nested in value.values():
            found = mapping_field(nested, field)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = mapping_field(nested, field)
            if found:
                return found
    return {}


def sequence_field(value: Any, field: str) -> list[Any]:
    if isinstance(value, dict):
        sequence = value.get(field)
        if isinstance(sequence, list):
            return list(sequence)
        if value.get("truncated") and isinstance(value.get("preview"), str):
            preview = value["preview"]
            marker = re.search(rf'"{re.escape(field)}"\s*:\s*', preview)
            if marker is not None:
                try:
                    parsed, _end = json.JSONDecoder().raw_decode(preview, marker.end())
                    if isinstance(parsed, list):
                        return list(parsed)
                except (ValueError, json.JSONDecodeError):
                    pass
        for nested in value.values():
            found = sequence_field(nested, field)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = sequence_field(nested, field)
            if found:
                return found
    return []


def parsed_display_date(value: Any) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass
    for date_format in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return None


__all__ = {
    "first_display_row",
    "parsed_display_date",
    "matrix_field",
    "sequence_field",
    "display_rows",
    "mapping_field",
}
