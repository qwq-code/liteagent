from __future__ import annotations

from typing import Any
from uuid import uuid4

from .errors import AdapterError
from .schema import REFERENCE_DISPLAY_MODES


REFERENCE_FIELD_SOURCE_BOOKMARK = 2
# com.sun.star.style.NumberingType values that do not produce a numeric label.
NON_NUMERIC_NUMBERING_TYPES = {5, 6, 8}
REFERENCE_FIELD_PARTS = {
    "page": 0,
    "chapter": 1,
    "text": 2,
    "above_below": 3,
    "page_style": 4,
    "number": 8,
    "number_no_context": 9,
    "number_full_context": 10,
}

if set(REFERENCE_FIELD_PARTS) != set(REFERENCE_DISPLAY_MODES):
    raise RuntimeError("cross-reference display modes are out of sync")


def _body_paragraphs(document: Any) -> list[Any]:
    paragraphs = []
    enumeration = document.Text.createEnumeration()
    while enumeration.hasMoreElements():
        item = enumeration.nextElement()
        try:
            if item.supportsService("com.sun.star.text.Paragraph"):
                paragraphs.append(item)
        except Exception:
            continue
    return paragraphs


def _paragraph_at(document: Any, index: int) -> Any:
    paragraphs = _body_paragraphs(document)
    if index >= len(paragraphs):
        raise AdapterError(
            "PARAGRAPH_NOT_FOUND",
            "paragraph index is out of range",
            {"paragraph_count": len(paragraphs), "index": index},
            404,
        )
    return paragraphs[index]


def _range_string(text_range: Any) -> str:
    value = getattr(text_range, "String", None)
    if value is not None:
        return str(value)
    getter = getattr(text_range, "getString", None)
    return str(getter()) if getter is not None else ""


def _move_right(cursor: Any, count: int, expand: bool) -> None:
    remaining = count
    while remaining:
        step = min(remaining, 32_767)
        if cursor.goRight(step, expand) is False:
            raise AdapterError(
                "TEXT_RANGE_NOT_FOUND",
                "could not reach the requested character offset",
                {"requested_count": count},
                404,
            )
        remaining -= step


def _explicit_range(
    paragraph: Any,
    *,
    start_offset: int,
    end_offset: int,
    expected_text: str,
) -> Any:
    paragraph_text = str(paragraph.String)
    if end_offset > len(paragraph_text):
        raise AdapterError(
            "TEXT_RANGE_NOT_FOUND",
            "character range exceeds the selected paragraph",
            {
                "paragraph_length": len(paragraph_text),
                "start_offset": start_offset,
                "end_offset": end_offset,
            },
            404,
        )
    observed = paragraph_text[start_offset:end_offset]
    if observed != expected_text:
        raise AdapterError(
            "TEXT_MISMATCH",
            "selected paragraph range does not match expected_text",
            {
                "start_offset": start_offset,
                "end_offset": end_offset,
                "expected_text": expected_text,
                "observed_text": observed,
            },
            409,
        )
    text = paragraph.getText()
    cursor = text.createTextCursorByRange(paragraph.getStart())
    _move_right(cursor, start_offset, False)
    _move_right(cursor, end_offset - start_offset, True)
    cursor_text = _range_string(cursor)
    if cursor_text != expected_text:
        raise AdapterError(
            "TEXT_RANGE_NOT_FOUND",
            "UNO cursor did not select the requested character range",
            {
                "expected_text": expected_text,
                "cursor_text": cursor_text,
                "start_offset": start_offset,
                "end_offset": end_offset,
            },
            409,
        )
    return cursor


def _numbering_type(numbering_rules: Any, level: int) -> int:
    try:
        properties = numbering_rules.getByIndex(level)
    except Exception as exc:
        raise AdapterError(
            "SOURCE_NOT_NUMBERED",
            "source numbering rules do not contain the requested level",
            {"level": level},
            409,
        ) from exc
    for prop in properties:
        if str(getattr(prop, "Name", "")) == "NumberingType":
            value = int(getattr(prop, "Value"))
            if value in NON_NUMERIC_NUMBERING_TYPES:
                raise AdapterError(
                    "SOURCE_NOT_NUMBERED",
                    "source paragraph uses a non-numeric list format",
                    {"level": level, "numbering_type": value},
                    409,
                )
            return value
    raise AdapterError(
        "SOURCE_NOT_NUMBERED",
        "source numbering rules do not expose NumberingType",
        {"level": level},
        409,
    )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def paragraph_numbering_state(paragraph: Any) -> dict[str, Any]:
    return {
        "style_name": str(getattr(paragraph, "NumberingStyleName", "") or ""),
        "level": _optional_int(getattr(paragraph, "NumberingLevel", None)),
        "restart": bool(getattr(paragraph, "ParaIsNumberingRestart", False)),
        "start_value": _optional_int(getattr(paragraph, "NumberingStartValue", None)),
        "list_label": str(getattr(paragraph, "ListLabelString", "") or ""),
        "is_numbered": bool(getattr(paragraph, "NumberingIsNumber", False)),
    }


def apply_paragraph_numbering(session: Any, params: dict[str, Any]) -> dict[str, Any]:
    source_index = int(params["source_index"])
    target_index = int(params["target_index"])
    level = int(params["level"])
    restart = bool(params["restart"])
    source = _paragraph_at(session.doc, source_index)
    target = _paragraph_at(session.doc, target_index)

    source_label = str(getattr(source, "ListLabelString", "") or "")
    source_is_numbered = bool(getattr(source, "NumberingIsNumber", False))
    if not source_is_numbered and not source_label:
        raise AdapterError(
            "SOURCE_NOT_NUMBERED",
            "source paragraph does not have native Writer numbering",
            {"source_index": source_index},
            409,
        )
    try:
        source_rules = source.NumberingRules
    except AttributeError as exc:
        raise AdapterError(
            "SOURCE_NOT_NUMBERED",
            "source paragraph has no reusable numbering rules",
            {"source_index": source_index},
            409,
        ) from exc
    numbering_type = _numbering_type(source_rules, level)

    original_text = str(target.String)
    source_style = str(getattr(source, "NumberingStyleName", "") or "")
    if source_style:
        target.NumberingStyleName = source_style
    target.NumberingRules = source_rules
    target.NumberingLevel = level
    target.ParaIsNumberingRestart = restart
    if restart:
        target.NumberingStartValue = int(params["start_value"])

    observed = paragraph_numbering_state(target)
    if (
        str(target.String) != original_text
        or observed["level"] != level
        or observed["restart"] is not restart
        or (source_style and observed["style_name"] != source_style)
        or not observed["is_numbered"]
    ):
        raise AdapterError(
            "VERIFICATION_FAILED",
            "native paragraph numbering did not match the requested state",
            {
                "source_index": source_index,
                "target_index": target_index,
                "original_text": original_text,
                "observed_text": str(target.String),
                "observed": observed,
            },
        )
    if restart and observed["start_value"] != int(params["start_value"]):
        raise AdapterError(
            "VERIFICATION_FAILED",
            "native paragraph numbering did not use the requested start value",
            {"target_index": target_index, "observed": observed},
        )
    return {
        "source_index": source_index,
        "target_index": target_index,
        "source_list_label": source_label,
        "numbering_type": numbering_type,
        **observed,
    }


def create_bookmark(session: Any, params: dict[str, Any]) -> dict[str, Any]:
    name = params["name"]
    bookmarks = session.doc.getBookmarks()
    if bookmarks.hasByName(name):
        raise AdapterError(
            "BOOKMARK_EXISTS",
            "bookmark name already exists",
            {"name": name},
            409,
        )
    paragraph_index = int(params["paragraph_index"])
    paragraph = _paragraph_at(session.doc, paragraph_index)
    cursor = _explicit_range(
        paragraph,
        start_offset=int(params["start_offset"]),
        end_offset=int(params["end_offset"]),
        expected_text=params["expected_text"],
    )
    bookmark = session.doc.createInstance("com.sun.star.text.Bookmark")
    bookmark.setName(name)
    bookmark.attach(cursor)

    if not bookmarks.hasByName(name):
        raise AdapterError(
            "VERIFICATION_FAILED",
            "bookmark was not registered in the active document",
            {"name": name},
        )
    observed = bookmarks.getByName(name)
    observed_name = str(observed.getName())
    anchor_text = _range_string(observed.getAnchor())
    if observed_name != name or anchor_text != params["expected_text"]:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "bookmark anchor does not match the requested range",
            {
                "expected_name": name,
                "observed_name": observed_name,
                "expected_text": params["expected_text"],
                "anchor_text": anchor_text,
            },
        )
    return {
        "name": observed_name,
        "paragraph_index": paragraph_index,
        "start_offset": int(params["start_offset"]),
        "end_offset": int(params["end_offset"]),
        "anchor_text": anchor_text,
    }


def insert_cross_reference(session: Any, params: dict[str, Any]) -> dict[str, Any]:
    bookmark_name = params["bookmark_name"]
    bookmarks = session.doc.getBookmarks()
    if not bookmarks.hasByName(bookmark_name):
        raise AdapterError(
            "BOOKMARK_NOT_FOUND",
            "cross-reference bookmark does not exist",
            {"bookmark_name": bookmark_name},
            404,
        )
    display = params["display"]
    if display in {"number", "number_no_context", "number_full_context"}:
        anchor = bookmarks.getByName(bookmark_name).getAnchor()
        source = anchor.getText().createTextCursorByRange(anchor.getStart())
        source.gotoStartOfParagraph(False)
        source.gotoEndOfParagraph(True)
        numbering = paragraph_numbering_state(source)
        source_details = {
            "bookmark_name": bookmark_name,
            "anchor_text": _range_string(anchor),
            "source_paragraph_text": _range_string(source),
            "numbering": numbering,
            "destination_unchanged": True,
            "guidance": (
                "The reference displays the number of the paragraph covered by its source "
                "bookmark. Check that this bookmark covers the content you want to cite. "
                "The insertion destination can remain ordinary unnumbered text. "
                "paragraph.apply_numbering can continue an observed list on the cited source; "
                "bookmark.create can anchor that source for a later cross_reference.insert."
            ),
        }
        try:
            level = numbering["level"]
            if (
                (not numbering["is_numbered"] and not numbering["list_label"])
                or level is None
                or not 0 <= level <= 9
            ):
                raise AdapterError(
                    "SOURCE_NOT_NUMBERED",
                    "bookmark source paragraph does not have native numeric numbering",
                    http_status=409,
                )
            _numbering_type(getattr(source, "NumberingRules", None), level)
        except AdapterError as exc:
            raise AdapterError(
                exc.code, exc.message, source_details | (exc.details or {}), exc.http_status
            ) from exc
    paragraph_index = int(params["paragraph_index"])
    paragraph = _paragraph_at(session.doc, paragraph_index)
    cursor = _explicit_range(
        paragraph,
        start_offset=int(params["start_offset"]),
        end_offset=int(params["end_offset"]),
        expected_text=params["expected_text"],
    )
    part = REFERENCE_FIELD_PARTS[display]
    field = session.doc.createInstance("com.sun.star.text.textfield.GetReference")
    field.SourceName = bookmark_name
    field.ReferenceFieldSource = REFERENCE_FIELD_SOURCE_BOOKMARK
    field.ReferenceFieldPart = part
    original_paragraph_text = str(paragraph.String)
    undo_title = f"Insert Writer cross-reference {uuid4().hex}"
    try:
        undo = session.doc.getUndoManager()
        if undo.isLocked():
            raise RuntimeError("Writer undo recording is locked")
        undo.enterUndoContext(undo_title)
    except Exception as exc:
        raise AdapterError(
            "LIBREOFFICE_NOT_READY",
            "Writer could not record a reversible cross-reference insertion",
            {"destination_unchanged": True, "cause": str(exc)},
            503,
        ) from exc

    failure = None
    try:
        paragraph.getText().insertTextContent(cursor, field, True)
        text_fields = session.doc.getTextFields()
        refresh = getattr(text_fields, "refresh", None)
        if refresh is not None:
            refresh()
        observed_source = str(getattr(field, "SourceName", "") or "")
        observed_source_type = int(getattr(field, "ReferenceFieldSource", -1))
        observed_part = int(getattr(field, "ReferenceFieldPart", -1))
        try:
            presentation = str(field.getPresentation(False))
        except Exception:
            presentation = str(getattr(field, "CurrentPresentation", "") or "")
        if (
            observed_source != bookmark_name
            or observed_source_type != REFERENCE_FIELD_SOURCE_BOOKMARK
            or observed_part != part
            or "reference source not found" in presentation.casefold()
            or (display != "text" and not presentation.strip())
        ):
            raise AdapterError(
                "VERIFICATION_FAILED",
                "native cross-reference field did not resolve as requested",
                {
                    "bookmark_name": bookmark_name,
                    "display": display,
                    "observed_source": observed_source,
                    "observed_source_type": observed_source_type,
                    "observed_part": observed_part,
                    "presentation": presentation,
                },
            )
    except Exception as exc:
        failure = exc
    finally:
        try:
            undo.leaveUndoContext()
        except Exception as exc:
            failure = failure or exc
    if failure is not None:
        restored = False
        restoration_attempted = False
        restoration_error = None
        try:
            # An empty undo context vanishes; never undo an earlier Agent action.
            if undo.isUndoPossible() and undo.getCurrentUndoActionTitle() == undo_title:
                restoration_attempted = True
                undo.undo()
                restored = True
        except Exception as exc:
            restoration_error = str(exc)
        destination_text = None
        field_present = None
        remaining_presentation = None
        try:
            destination_text = str(_paragraph_at(session.doc, paragraph_index).String)
            fields = session.doc.getTextFields().createEnumeration()
            field_present = False
            while fields.hasMoreElements():
                if fields.nextElement() == field:
                    field_present = True
                    remaining_presentation = str(field.getPresentation(False))
                    break
        except Exception as exc:
            restoration_error = restoration_error or str(exc)
        details = {
            "bookmark_name": bookmark_name,
            "display": display,
            "paragraph_index": paragraph_index,
            "restoration_attempted": restoration_attempted,
            "destination_restored": bool(
                restored and destination_text == original_paragraph_text and field_present is False
            ),
            "destination_text": destination_text,
            "field_present": field_present,
            "remaining_field_presentation": remaining_presentation,
        }
        if restoration_error is not None:
            details["restoration_error"] = restoration_error
        if isinstance(failure, AdapterError):
            raise AdapterError(
                failure.code, failure.message, (failure.details or {}) | details, failure.http_status
            ) from failure
        raise AdapterError(
            "CROSS_REFERENCE_INSERT_FAILED",
            "native cross-reference insertion or refresh failed",
            details | {"cause": str(failure)},
            500,
        ) from failure
    return {
        "bookmark_name": bookmark_name,
        "paragraph_index": paragraph_index,
        "start_offset": int(params["start_offset"]),
        "end_offset": int(params["end_offset"]),
        "display": display,
        "presentation": presentation,
        "field_service": "com.sun.star.text.textfield.GetReference",
    }
