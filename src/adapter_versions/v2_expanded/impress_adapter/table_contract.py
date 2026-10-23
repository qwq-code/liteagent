from __future__ import annotations

from typing import Any, Mapping

from .errors import AdapterError


TABLE_PLACEMENTS = frozenset({"auto", "content_placeholder", "custom"})
TABLE_GEOMETRY_FIELDS = frozenset({"x", "y", "width", "height"})


def validate_table_placement(params: Mapping[str, Any]) -> None:
    placement = params.get("placement", "auto")
    if placement not in TABLE_PLACEMENTS:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.placement must be auto, content_placeholder, or custom",
        )
    explicit_geometry = sorted(TABLE_GEOMETRY_FIELDS.intersection(params))
    if placement == "content_placeholder" and explicit_geometry:
        raise AdapterError(
            "INVALID_REQUEST",
            "content_placeholder placement cannot be combined with explicit geometry",
            {"conflicting_fields": explicit_geometry},
        )


def may_use_content_placeholder(params: Mapping[str, Any]) -> bool:
    placement = params.get("placement", "auto")
    if placement == "content_placeholder":
        return True
    return placement == "auto" and not TABLE_GEOMETRY_FIELDS.intersection(params)


def is_empty_content_placeholder(shape: Any, text: str) -> bool:
    kind = str(
        getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
    ).casefold()
    return "outlinershape" in kind and not text.strip()
