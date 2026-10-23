from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .errors import AdapterError


def slide_index_from_reference(
    data: Mapping[str, Any], *, allow_consistent_pair: bool = False
) -> int | None:
    """Resolve a public slide reference without mutating its source."""
    has_index = "slide" in data
    has_number = "slide_number" in data
    if not has_index and not has_number:
        return None
    if has_index and has_number:
        index = data["slide"]
        number = data["slide_number"]
        if (
            not allow_consistent_pair
            or isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or isinstance(number, bool)
            or not isinstance(number, int)
            or number < 1
            or number != index + 1
        ):
            return None
        return index
    if has_index:
        value = data["slide"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value
    value = data["slide_number"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value - 1


def require_slide_index(
    data: Mapping[str, Any],
    prefix: str = "params",
    *,
    allow_consistent_pair: bool = False,
) -> int:
    """Validate a public slide reference and return its zero-based index."""
    has_index = "slide" in data
    has_number = "slide_number" in data
    if not has_index and not has_number:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix} must contain exactly one of slide or slide_number",
        )
    if has_index and has_number and not allow_consistent_pair:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix} must contain exactly one of slide or slide_number",
        )
    resolved = slide_index_from_reference(
        data, allow_consistent_pair=allow_consistent_pair
    )
    if resolved is not None:
        return resolved
    if has_index and has_number:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix}.slide_number must equal {prefix}.slide + 1 when both are supplied",
        )
    field = "slide" if has_index else "slide_number"
    expectation = (
        "a non-negative 0-based index"
        if field == "slide"
        else "a positive 1-based number"
    )
    raise AdapterError(
        "INVALID_REQUEST",
        f"{prefix}.{field} must be {expectation}",
    )


def slide_referenced_arguments_equal(
    observed: Any,
    expected: Any,
) -> bool:
    """Compare argument mappings while treating the two public slide forms equally."""
    if not isinstance(observed, Mapping) or not isinstance(expected, Mapping):
        return False
    observed_slide = slide_index_from_reference(observed, allow_consistent_pair=True)
    expected_slide = slide_index_from_reference(expected, allow_consistent_pair=True)
    if observed_slide is None or expected_slide is None:
        return False
    if observed_slide != expected_slide:
        return False
    location_fields = {"slide", "slide_number"}
    observed_body = {
        key: value for key, value in observed.items() if key not in location_fields
    }
    expected_body = {
        key: value for key, value in expected.items() if key not in location_fields
    }
    return observed_body == expected_body
