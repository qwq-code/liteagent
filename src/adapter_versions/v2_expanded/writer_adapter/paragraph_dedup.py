"""Pure planning helpers for stable, field-based paragraph de-duplication."""

from __future__ import annotations

from typing import Any, Iterable


def plan_paragraph_deduplication(
    values: Iterable[str],
    *,
    delimiter: str,
    key_column: int,
    trim_key: bool = True,
    case_sensitive: bool = True,
    skip_blank: bool = True,
) -> dict[str, Any]:
    """Return a stable first-occurrence plan without mutating the document.

    Paragraph order is part of the document's user-visible data.  The helper
    therefore never sorts, normalizes complete records, or invents replacement
    text; it only identifies later records whose selected field has already
    occurred.  The native worker applies the returned removal indices in reverse
    order so the indices remain valid while content is removed.
    """
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("delimiter must be one character")
    if isinstance(key_column, bool) or not isinstance(key_column, int) or key_column < 0:
        raise ValueError("key_column must be a non-negative integer")

    records = [str(value) for value in values]
    seen: set[str] = set()
    keep_indices: list[int] = []
    remove_indices: list[int] = []
    duplicate_keys: list[str] = []
    for index, value in enumerate(records):
        if skip_blank and not value.strip():
            keep_indices.append(index)
            continue
        fields = value.split(delimiter)
        if key_column >= len(fields):
            raise ValueError(
                f"paragraph {index} has no field at key_column {key_column}"
            )
        raw_key = fields[key_column]
        key = raw_key.strip() if trim_key else raw_key
        compare_key = key if case_sensitive else key.casefold()
        if compare_key in seen:
            remove_indices.append(index)
            if key not in duplicate_keys:
                duplicate_keys.append(key)
        else:
            seen.add(compare_key)
            keep_indices.append(index)
    return {
        "keep_indices": keep_indices,
        "remove_indices": remove_indices,
        "duplicate_keys": duplicate_keys,
        "input_count": len(records),
        "kept_count": len(keep_indices),
        "removed_count": len(remove_indices),
    }


__all__ = ["plan_paragraph_deduplication"]
