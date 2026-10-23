from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


ROLE_ALIASES = {"body": "content"}
TEXT_ROLES = frozenset({"all", "title", "content", "body", "table", "text"})
VISUAL_TITLE_MIN_FONT_RATIO = 1.5


def normalize_roles(roles: Iterable[str]) -> tuple[str, ...]:
    """Normalize public role aliases while preserving the model's order."""
    normalized = [ROLE_ALIASES.get(role, role) for role in roles]
    return tuple(dict.fromkeys(normalized))


def shape_text_role(shape: Any) -> str | None:
    """Classify an Impress shape from its public UNO application semantics."""
    kind = str(
        getattr(shape, "ShapeType", "") or getattr(shape, "ImplementationName", "")
    ).casefold()
    model = getattr(shape, "Model", None)
    if "tableshape" in kind or (
        model is not None and hasattr(model, "getCellByPosition")
    ):
        return "table"
    if "titletextshape" in kind:
        return "title"
    if "outlinershape" in kind or "subtitleshape" in kind:
        return "content"
    if hasattr(shape, "getText"):
        return "text"
    return None


def _shape_text(shape: Any) -> str:
    try:
        return str(shape.getText().getString())
    except Exception:
        return ""


def _shape_font_size(shape: Any) -> float:
    try:
        text = shape.getText()
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        value = cursor.getPropertyValue("CharHeight")
    except Exception:
        value = getattr(shape, "CharHeight", 0.0)
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else 0.0
    )


def _container_height(container: Any) -> float:
    value = getattr(container, "Height", None)
    if value is None:
        value = getattr(getattr(container, "Size", None), "Height", 0)
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else 0.0
    )


def _shape_vertical_center(shape: Any) -> float:
    position = getattr(shape, "Position", None)
    size = getattr(shape, "Size", None)
    return float(getattr(position, "Y", 0)) + float(getattr(size, "Height", 0)) / 2


def _shape_records(
    container: Any,
    prefix: list[int] | None = None,
) -> Iterator[tuple[list[int], Any, str]]:
    base = prefix or []
    for index in range(container.getCount()):
        shape = container.getByIndex(index)
        path = [*base, index]
        role = shape_text_role(shape)
        if role is not None:
            yield path, shape, role
        if hasattr(shape, "getCount") and hasattr(shape, "getByIndex"):
            yield from _shape_records(shape, path)


def _visual_title_path(
    container: Any,
    records: list[tuple[list[int], Any, str]],
) -> tuple[int, ...] | None:
    """Resolve one imported-deck heading conservatively from live visual semantics."""
    height = _container_height(container)
    if height <= 0:
        return None
    candidates = []
    for path, shape, role in records:
        if (
            role != "text"
            or not _shape_text(shape).strip()
            or not bool(getattr(shape, "Visible", True))
        ):
            continue
        font_size = _shape_font_size(shape)
        if font_size > 0:
            candidates.append((path, font_size, _shape_vertical_center(shape)))
    candidates.sort(key=lambda item: (-item[1], tuple(item[0])))
    if not candidates:
        return None
    _path, largest, vertical_center = candidates[0]
    if vertical_center > height / 2:
        return None
    if len(candidates) > 1:
        second = candidates[1][1]
        if largest == second or largest < second * VISUAL_TITLE_MIN_FONT_RATIO:
            return None
    return tuple(candidates[0][0])


def iter_shapes_for_roles(
    container: Any,
    roles: Iterable[str],
    prefix: list[int] | None = None,
) -> Iterator[tuple[list[int], Any, str]]:
    """Yield live shapes matching the requested semantic roles."""
    selected = set(normalize_roles(roles))
    select_all = "all" in selected
    records = list(_shape_records(container, prefix))
    visual_title = None
    if "title" in selected and not any(
        role == "title" for _path, _shape, role in records
    ):
        visual_title = _visual_title_path(container, records)
    for path, shape, native_role in records:
        role = "title" if tuple(path) == visual_title else native_role
        if select_all or role in selected:
            yield path, shape, role
