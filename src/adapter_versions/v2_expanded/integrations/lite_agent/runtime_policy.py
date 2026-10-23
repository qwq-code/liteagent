"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations

import hashlib
import json
from typing import Any


from .adapter_results import (
    a1_geometry,
    adapter_context_hint as adapter_context_hint,
    column_number,
    compact,
    compact_adapter_body as compact_adapter_body,
)
from .completion_policy import (
    completion_claim_contradictions as completion_claim_contradictions,
)


ACTION_BLOCK_WINDOW_STEPS = 6


class RepeatedRequestBlocked(RuntimeError):
    def __init__(self, error: dict[str, Any]):
        super().__init__(str(error.get("detail", "repeated request blocked")))
        self.error = error


def error_signature(error: Any) -> Any:
    if not isinstance(error, dict):
        return compact(error, 500)
    nested = error.get("error")
    if not isinstance(nested, dict):
        # Forwarded Adapter failures keep the actual code below the wrapper.
        details = error.get("details")
        response = details.get("response") if isinstance(details, dict) else None
        if isinstance(response, dict):
            nested = response.get("error")
    if isinstance(nested, dict):
        return (
            nested.get("code") or nested.get("type"),
            nested.get("message") or nested.get("detail"),
        )
    previous = error.get("previous_error")
    if previous is not None:
        return (error.get("type"), error_signature(previous))
    return (
        error.get("type") or error.get("status"),
        error.get("detail") or error.get("message"),
        tuple(str(item) for item in error.get("missing", [])),
    )


def argument_signature(arguments: Any) -> str:
    encoded = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_adapter_arguments(
    domain: str, action: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if domain == "libreoffice_calc" and action == "range.write":
        values = arguments.get("values")
        geometry = a1_geometry(str(arguments.get("range", "")))
        if (
            isinstance(values, list)
            and values
            and all(isinstance(cell, dict) for cell in values)
        ):
            if geometry is not None:
                start_column, start_row, end_column, end_row = geometry
                target_rows = end_row - start_row + 1
                target_columns = (
                    column_number(end_column) - column_number(start_column) + 1
                )
                if (
                    target_columns == 1
                    and target_rows > 1
                    and len(values) == target_rows
                ):
                    return {**arguments, "values": [[cell] for cell in values]}
            return {**arguments, "values": [values]}
        if (
            geometry is not None
            and isinstance(values, list)
            and len(values) == 1
            and isinstance(values[0], list)
        ):
            start_column, start_row, end_column, end_row = geometry
            target_rows = end_row - start_row + 1
            target_columns = column_number(end_column) - column_number(start_column) + 1
            if (
                target_columns == 1
                and target_rows > 1
                and len(values[0]) == target_rows
            ):
                return {**arguments, "values": [[cell] for cell in values[0]]}
    if domain == "libreoffice_calc" and action == "rows.set_hidden":
        rows = arguments.get("rows")
        if isinstance(rows, list) and all(
            isinstance(row, int) and not isinstance(row, bool) for row in rows
        ):
            return {**arguments, "rows": sorted(set(rows))}
    return arguments
