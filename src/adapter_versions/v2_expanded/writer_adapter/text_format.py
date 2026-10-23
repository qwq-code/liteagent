"""Character formatting on one explicit, caller-selected body-text range."""

from __future__ import annotations

from typing import Any

from .errors import AdapterError
from .native_references import _explicit_range, _paragraph_at


def _enum_name(value: Any) -> str:
    return str(getattr(value, "value", value)).rsplit(".", 1)[-1].lower()


def range_format(cursor: Any) -> dict[str, Any]:
    size = getattr(cursor, "CharHeight", None)
    weight = getattr(cursor, "CharWeight", None)
    posture = getattr(cursor, "CharPosture", None)
    escapement = getattr(cursor, "CharEscapement", None)
    return {
        "font_size": float(size) if size is not None else None,
        "bold": float(weight) >= 150 if weight is not None else None,
        "italic": _enum_name(posture) in {"italic", "oblique"}
        if posture is not None
        else None,
        "script": (
            "mixed"
            if escapement is None
            else "subscript"
            if int(escapement) < 0
            else "superscript"
            if int(escapement) > 0
            else "normal"
        ),
    }


def set_text_format(session: Any, params: dict[str, Any]) -> dict[str, Any]:
    paragraph_index = int(params["paragraph_index"])
    paragraph = _paragraph_at(session.doc, paragraph_index)
    original_text = str(paragraph.String)
    cursor = _explicit_range(
        paragraph,
        start_offset=int(params["start_offset"]),
        end_offset=int(params["end_offset"]),
        expected_text=params["expected_text"],
    )
    if "font_size" in params:
        for name in ("CharHeight", "CharHeightAsian", "CharHeightComplex"):
            setattr(cursor, name, float(params["font_size"]))
    if "bold" in params:
        cursor.CharWeight = 150.0 if params["bold"] else 100.0
    if "italic" in params:
        import uno

        cursor.CharPosture = uno.Enum(
            "com.sun.star.awt.FontSlant", "ITALIC" if params["italic"] else "NONE"
        )
    if "script" in params:
        selected_script = params["script"]
        if selected_script == "normal":
            cursor.CharEscapement = 0
            cursor.CharEscapementHeight = 100
        elif range_format(cursor)["script"] != selected_script:
            # Use Writer's native preset, without a hard-coded text-size or shift offset.
            cursor.CharEscapement = 0
            session.doc.getCurrentController().select(cursor)
            session.dispatch(
                ".uno:SubScript"
                if selected_script == "subscript"
                else ".uno:SuperScript"
            )
    observed = range_format(cursor)
    requested = {key: params[key] for key in observed if key in params}
    if str(paragraph.String) != original_text or any(
        observed[key] != value for key, value in requested.items()
    ):
        raise AdapterError(
            "VERIFICATION_FAILED",
            "selected text formatting did not match the request",
            {"requested": requested, "observed": observed},
        )
    return {
        "paragraph_index": paragraph_index,
        "start_offset": int(params["start_offset"]),
        "end_offset": int(params["end_offset"]),
        "text": params["expected_text"],
        "format": observed,
        "text_unchanged": True,
    }
