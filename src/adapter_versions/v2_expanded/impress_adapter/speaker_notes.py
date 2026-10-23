from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import AdapterError


NOTES_SHAPE_TYPE = "com.sun.star.presentation.NotesShape"


def _shape_type(shape: Any) -> str:
    for attribute in ("ShapeType", "ImplementationName"):
        value = getattr(shape, attribute, "")
        if value:
            return str(value)
    return ""


def _shape_text(shape: Any) -> str:
    try:
        return str(shape.getText().getString())
    except Exception:
        return ""


def resolve_speaker_notes_shape(
    notes_page: Any,
    *,
    create_instance: Callable[[str], Any] | None = None,
) -> Any | None:
    """Resolve only Impress' semantic speaker-notes body shape."""

    matches = []
    for index in range(notes_page.getCount()):
        shape = notes_page.getByIndex(index)
        if _shape_type(shape).casefold() == NOTES_SHAPE_TYPE.casefold():
            matches.append(shape)
    if len(matches) > 1:
        raise AdapterError(
            "NOTES_BODY_AMBIGUOUS",
            "the notes page contains multiple semantic speaker-notes body shapes",
            {"shape_type": NOTES_SHAPE_TYPE, "count": len(matches)},
            409,
        )
    if matches:
        return matches[0]
    if create_instance is None:
        return None

    target = create_instance(NOTES_SHAPE_TYPE)
    observed_type = _shape_type(target)
    if observed_type.casefold() != NOTES_SHAPE_TYPE.casefold():
        raise AdapterError(
            "NOTES_BODY_UNAVAILABLE",
            "LibreOffice did not create a semantic speaker-notes body shape",
            {
                "expected_shape_type": NOTES_SHAPE_TYPE,
                "observed_shape_type": observed_type,
            },
            422,
        )
    notes_page.add(target)
    return target


def speaker_notes_text(notes_page: Any) -> str:
    """Read the semantic notes body without including page-number placeholders."""

    target = resolve_speaker_notes_shape(notes_page)
    return _shape_text(target) if target is not None else ""


def set_speaker_notes(
    notes_page: Any,
    text: str,
    *,
    create_instance: Callable[[str], Any],
) -> str:
    """Write and verify the semantic notes body, creating it when absent."""

    target = resolve_speaker_notes_shape(
        notes_page,
        create_instance=create_instance,
    )
    if target is None:  # Defensive: create_instance makes this unreachable.
        raise AdapterError(
            "NOTES_BODY_UNAVAILABLE", "speaker-notes body is unavailable"
        )
    try:
        target.String = text
    except Exception as exc:
        raise AdapterError(
            "NOTES_WRITE_FAILED",
            "LibreOffice rejected the speaker-notes body text",
            {"error": f"{type(exc).__name__}: {exc}"},
            422,
        ) from exc
    observed = _shape_text(target)
    if observed != text:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "speaker-notes body did not equal the requested text after mutation",
            {"expected": text, "observed": observed},
            422,
        )
    return observed


__all__ = [
    "NOTES_SHAPE_TYPE",
    "resolve_speaker_notes_shape",
    "set_speaker_notes",
    "speaker_notes_text",
]
