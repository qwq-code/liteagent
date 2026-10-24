from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from impress_adapter.geometry_contract import order_shapes_by_position

from .calc_column_reorder import column_reorder_context
from .filesystem_contexts import filesystem_rename_context
from .vscode_workspace_context import workspace_mutation_context
from .context_projection import (
    MODEL_CONTEXT_HINT_DEFAULT_MAX_CHARS as _MODEL_CONTEXT_HINT_DEFAULT_MAX_CHARS,
    MODEL_CONTEXT_HINT_MAX_CHARS as _MODEL_CONTEXT_HINT_MAX_CHARS,
    MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS as _MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS,
    MODEL_CONTEXT_MAX_LIST_ITEMS,
    MODEL_CONTEXT_MAX_STRING_CHARS,
    TEXT_BATCH_READING_GUIDANCE,
    TEXT_FILE_READING_GUIDANCE,
    WRITER_TEXT_READING_GUIDANCE,
    _fit_batch_text_windows,
    _financial_amount_hint,
    _fit_string,
    _slim_batch_optional_fields,
    compact_hint as _compact_context_hint,
    compact_execution_summary_for_model as _compact_execution_summary_for_model,
    contains_text_batch_context as _contains_text_batch_context,
    declared_budget as _declared_context_hint_budget,
    summarize_events as _summarize_events,
)

TEXT_BATCH_CONTEXT_MAX_FILES = 20
TEXT_BATCH_CONTEXT_MAX_CHARS = 64_000
TEXT_BATCH_CONTEXT_PER_FILE_MAX_CHARS = 16_000
# Batch readers can return tens of thousands of characters.  Keep the model
# projection substantially smaller than the complete Adapter evidence while
# retaining exact file handles and a resumable, typed text chunk.
TEXT_BATCH_MODEL_CONTEXT_MAX_CHARS = 18_000
TEXT_BATCH_MODEL_CHUNK_MAX_CHARS = TEXT_BATCH_CONTEXT_PER_FILE_MAX_CHARS
TEXT_BATCH_MODEL_TABLE_ROW_MAX_CHARS = 480
TEXT_BATCH_MODEL_TABLE_ROWS_PER_FILE = 2
MODEL_CONTEXT_HINT_DEFAULT_MAX_CHARS = _MODEL_CONTEXT_HINT_DEFAULT_MAX_CHARS
MODEL_CONTEXT_HINT_MAX_CHARS = _MODEL_CONTEXT_HINT_MAX_CHARS
MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS = _MODEL_CONTEXT_HINT_TOTAL_MAX_CHARS

PRESENTATION_SELECTOR_GUIDANCE = (
    "Human page=display_slide_number; zero-based index=slide_index. Copy complete "
    "tool_target. text_shape_order is list order; index/path are IDs. "
    "x/y start top-left; smaller y is higher. Geometry uses 1/100 mm (100=1mm): "
    "copy into numeric fields. *_measurement instead takes physical sizes/units."
)

_TABLE_ROW_SUMMARY_RE = re.compile(
    r"(?i)\b(?:grand\s+)?(?:total|subtotal|summary|overall|result)\b"
)
_TABLE_ROW_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])[+-]?(?:\d[\d,]*(?:\.\d+)?%?)(?![A-Za-z0-9])"
)
_TABLE_ROW_SUMMARY_LABELS = ("subtotal", "total", "summary", "overall", "result")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact(value: Any, max_chars: int = 6000) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= max_chars:
        return value
    return {"truncated": True, "chars": len(encoded), "preview": encoded[:max_chars]}


def declared_context_hint_budget(value: dict[str, Any]) -> int:
    """Compatibility wrapper for the model-context budget helper."""
    return _declared_context_hint_budget(value)


def compact_context_hint_for_model(
    value: dict[str, Any], *, remaining_chars: int
) -> dict[str, Any]:
    # Keep whole observed selectors instead of dividing their fields across
    # a deck-wide recursive budget. Picture and text actions both need them.
    if (
        isinstance(value, dict)
        and isinstance(value.get("slides"), list)
        and any(
            isinstance(slide, dict) and isinstance(slide.get("text_shapes"), list)
            for slide in value["slides"]
        )
    ):
        return _compact_presentation_hint_for_model(value, remaining_chars)
    return _compact_context_hint(value, remaining_chars=remaining_chars)


def _compact_presentation_hint_for_model(
    value: dict[str, Any], remaining_chars: int
) -> dict[str, Any]:
    """Keep exact shape selectors available for bounded Impress observations."""
    if remaining_chars <= 0:
        return {}
    result: dict[str, Any] = {
        key: value.get(key)
        for key in ("identity", "url", "title", "slide_count", "inspected_slides")
        if key in value
    }
    slides: list[dict[str, Any]] = []
    result["context_char_budget"] = remaining_chars
    sources = [slide for slide in value.get("slides", []) if isinstance(slide, dict)]
    collections = (
        "media_shapes",
        "text_shapes",
        "graphic_shapes",
        "picture_containers",
        "table_shapes",
    )
    result["slides"] = slides
    result["slides_omitted_from_context"] = value.get(
        "slides_omitted_from_context", 0
    ) + len(sources)
    full_guidance = value.get("guidance") or (
        PRESENTATION_SELECTOR_GUIDANCE + " "
        "shape.export_image writes a picture to your output_path for file tools. "
        "media_shapes lists existing audio/video URLs and native selectors; inspect "
        "it before inserting media."
    )
    # Reserve the selector/unit contract, then spend the budget on observed
    # objects. Extended usage advice must not displace their paths or URLs.
    result["guidance"] = PRESENTATION_SELECTOR_GUIDANCE
    # Add slides with their selectors in document order. A full-deck empty
    # index must not consume the space needed for actionable observations.
    for source in sources:
        entry = {
            "slide_index": source.get("slide_index", source.get("slide")),
            **{
                key: source.get(key)
                for key in (
                    "display_slide_number",
                    "width",
                    "height",
                    "orientation",
                    "text_shape_order",
                    "notes",
                )
                if key in source
            },
            **(
                {"has_speaker_notes": source.get("has_speaker_notes")}
                if "notes" in source
                else {}
            ),
        }
        for collection in collections:
            if collection == "media_shapes" and not source.get(collection):
                continue
            entry[collection] = []
            entry[f"{collection}_omitted"] = source.get(
                f"{collection}_omitted", 0
            ) + len(source.get(collection, []))
        slides.append(entry)
        result["slides_omitted_from_context"] -= 1
        if len(json.dumps(result, ensure_ascii=False, default=str)) > remaining_chars:
            slides.pop()
            result["slides_omitted_from_context"] += 1
            break
        for collection in collections:
            if collection == "media_shapes" and not source.get(collection):
                continue
            for shape in source.get(collection, []):
                if not isinstance(shape, dict):
                    continue
                candidate = {
                    key: shape[key]
                    for key in (
                        "index",
                        "path",
                        "name",
                        "kind",
                        "x",
                        "y",
                        "width",
                        "height",
                        "lines",
                        "paragraphs",
                        "text_style",
                        "tool_target",
                        "layout_role",
                        "orientation",
                        "area",
                        "rows",
                        "columns",
                        "media_url",
                    )
                    if shape.get(key) is not None
                }
                entry[collection].append(candidate)
                entry[f"{collection}_omitted"] -= 1
                if (
                    len(json.dumps(result, ensure_ascii=False, default=str))
                    > remaining_chars
                ):
                    entry[collection].pop()
                    entry[f"{collection}_omitted"] += 1
    result["guidance"] = full_guidance
    if len(json.dumps(result, ensure_ascii=False, default=str)) > remaining_chars:
        result["guidance"] = PRESENTATION_SELECTOR_GUIDANCE
    return _compact_context_hint(result, remaining_chars=remaining_chars)


def compact_execution_summary_for_model(
    value: Any, *, max_chars: int = 9_000
) -> list[dict[str, Any]]:
    """Compatibility wrapper for the bounded protocol-recovery transcript."""
    return _compact_execution_summary_for_model(value, max_chars=max_chars)


def contains_text_batch_context(value: Any) -> bool:
    """Compatibility wrapper for the bounded batch-observation detector."""
    return _contains_text_batch_context(value)


def _picture_layout_role(shape: dict[str, Any], slide: dict[str, Any]) -> str:
    """Classify a live picture container from slide-relative geometry."""
    keys = ("width", "height")
    slide_values = [slide.get(key) for key in keys]
    shape_values = [shape.get(key) for key in ("x", "y", *keys)]
    values = [*slide_values, *shape_values]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return "unknown"
    slide_width, slide_height, x, y, width, height = values
    if min(slide_width, slide_height, width, height) <= 0:
        return "unknown"
    near_origin = x <= slide_width * 0.05 and y <= slide_height * 0.05
    spans_slide = width >= slide_width * 0.9 and height >= slide_height * 0.6
    return "slide_cover" if near_origin and spans_slide else "foreground_content"


def _graphic_geometry_semantics(shape: dict[str, Any]) -> dict[str, Any]:
    width = shape.get("width")
    height = shape.get("height")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
    ):
        return {}
    orientation = (
        "landscape" if width > height else "portrait" if height > width else "square"
    )
    return {"orientation": orientation, "area": width * height}


def _compact_picture_candidate(
    shape: dict[str, Any], slide: dict[str, Any]
) -> dict[str, Any]:
    summary = {
        key: shape.get(key)
        for key in (
            "index",
            "path",
            "name",
            "kind",
            "x",
            "y",
            "width",
            "height",
            "visible",
        )
    }
    summary.update(
        {
            key: shape[key]
            for key in ("graphic_count", "bitmap_fill_count")
            if key in shape
        }
    )
    summary.update(_shape_tool_target(shape, slide))
    summary["layout_role"] = _picture_layout_role(shape, slide)
    summary.update(_graphic_geometry_semantics(shape))
    return summary


def _shape_tool_target(shape: dict[str, Any], slide: dict[str, Any]) -> dict[str, Any]:
    """Keep an observed page and its native selector together for model copying."""
    slide_index = slide.get("slide")
    path = shape.get("path")
    index = shape.get("index")
    name = shape.get("name")
    selector = None
    if isinstance(path, list):
        selector = {"path": path}
    elif isinstance(index, int) and not isinstance(index, bool):
        selector = {"index": index}
    elif isinstance(name, str) and name:
        selector = {"name": name}
    if isinstance(slide_index, int) and not isinstance(slide_index, bool) and selector:
        return {"tool_target": {"slide": slide_index, "selector": selector}}
    return {}


def compact_presentation_hint_for_model(
    value: dict[str, Any],
) -> dict[str, Any]:
    """Return a complete compact view of a direct Impress inspection.

    The native inspection result is intentionally rich for Adapter-side state
    validation, but truncating that JSON in the model request can leave the
    model with a syntactically incomplete shape list.  Strict episodes use this
    bounded structural projection while the truthful event retains the full
    inspection result.
    """
    raw_slides = value.get("slides")
    if not isinstance(raw_slides, list):
        return value
    raw_identity = value.get("identity")
    identity = raw_identity if isinstance(raw_identity, dict) else {}
    slide_summaries: list[dict[str, Any]] = []
    remaining_picture_containers = 24
    remaining_graphics = 24
    remaining_media_shapes = 12
    remaining_text_shapes = 24
    remaining_tables = 12
    for slide in raw_slides[:64]:
        if not isinstance(slide, dict):
            continue
        raw_graphics = slide.get("graphic_shapes")
        graphics = raw_graphics if isinstance(raw_graphics, list) else []
        raw_picture_containers = slide.get("picture_containers")
        all_picture_containers = (
            raw_picture_containers if isinstance(raw_picture_containers, list) else []
        )
        graphic_paths = {
            tuple(shape["path"])
            for shape in graphics
            if isinstance(shape, dict) and isinstance(shape.get("path"), list)
        }
        picture_containers = [
            shape
            for shape in all_picture_containers
            if isinstance(shape, dict)
            and (
                not isinstance(shape.get("path"), list)
                or tuple(shape["path"]) not in graphic_paths
            )
        ]
        raw_text_shapes = slide.get("text_shapes")
        text_shapes = raw_text_shapes if isinstance(raw_text_shapes, list) else []
        ordered_text = order_shapes_by_position(text_shapes, "top_to_bottom")
        text_shape_order = "native"
        if ordered_text is not None and len(ordered_text) == len(text_shapes):
            text_shapes = ordered_text
            text_shape_order = "top_to_bottom_then_left_to_right"
        raw_tables = slide.get("table_shapes")
        tables = raw_tables if isinstance(raw_tables, list) else []
        contextual_picture_containers = picture_containers[
            :remaining_picture_containers
        ]
        contextual_graphics = graphics[:remaining_graphics]
        raw_media_shapes = slide.get("media_shapes")
        media_shapes = raw_media_shapes if isinstance(raw_media_shapes, list) else []
        contextual_media_shapes = media_shapes[:remaining_media_shapes]
        contextual_text_shapes = text_shapes[:remaining_text_shapes]
        contextual_tables = tables[:remaining_tables]
        remaining_picture_containers -= len(contextual_picture_containers)
        remaining_graphics -= len(contextual_graphics)
        remaining_media_shapes -= len(contextual_media_shapes)
        remaining_text_shapes -= len(contextual_text_shapes)
        remaining_tables -= len(contextual_tables)
        slide_summaries.append(
            {
                "slide_index": slide.get("slide"),
                "display_slide_number": (
                    slide["slide"] + 1
                    if isinstance(slide.get("slide"), int)
                    and not isinstance(slide.get("slide"), bool)
                    else None
                ),
                "width": slide.get("width"),
                "height": slide.get("height"),
                "orientation": slide.get("orientation"),
                "background": slide.get("background"),
                "picture_containers": [
                    _compact_picture_candidate(shape, slide)
                    for shape in contextual_picture_containers
                    if isinstance(shape, dict)
                ],
                "picture_containers_omitted": max(
                    0,
                    len(picture_containers) - len(contextual_picture_containers),
                ),
                "graphic_shapes": [
                    _compact_picture_candidate(shape, slide)
                    for shape in contextual_graphics
                    if isinstance(shape, dict)
                ],
                "graphic_shapes_omitted": max(
                    0, len(graphics) - len(contextual_graphics)
                ),
                **(
                    {
                        "media_shapes": [
                            {
                                key: shape.get(key)
                                for key in (
                                    "index",
                                    "path",
                                    "name",
                                    "kind",
                                    "media_url",
                                    "x",
                                    "y",
                                    "width",
                                    "height",
                                    "visible",
                                )
                                if shape.get(key) is not None
                            }
                            for shape in contextual_media_shapes
                            if isinstance(shape, dict)
                        ],
                        "media_shapes_omitted": max(
                            0, len(media_shapes) - len(contextual_media_shapes)
                        ),
                    }
                    if media_shapes
                    else {}
                ),
                "text_shapes": [
                    {
                        **{
                            key: shape.get(key)
                            for key in (
                                "index",
                                "path",
                                "name",
                                "kind",
                                "x",
                                "y",
                                "width",
                                "height",
                                "lines",
                                "paragraphs",
                                "text_style",
                            )
                        },
                        **_shape_tool_target(shape, slide),
                    }
                    for shape in contextual_text_shapes
                    if isinstance(shape, dict)
                ],
                "text_shape_order": text_shape_order,
                "text_shapes_omitted": max(
                    0, len(text_shapes) - len(contextual_text_shapes)
                ),
                "table_shapes": [
                    {
                        key: table.get(key)
                        for key in (
                            "index",
                            "path",
                            "name",
                            "kind",
                            "x",
                            "y",
                            "width",
                            "height",
                            "rows",
                            "columns",
                        )
                    }
                    for table in contextual_tables
                    if isinstance(table, dict)
                ],
                "table_shapes_omitted": max(0, len(tables) - len(contextual_tables)),
                **(
                    {
                        "notes": _fit_string(
                            str(slide["notes"]), MODEL_CONTEXT_MAX_STRING_CHARS
                        )
                    }
                    if "notes" in slide
                    else {}
                ),
                "has_speaker_notes": bool(str(slide.get("notes", "")).strip()),
            }
        )
    context = {
        "identity": {
            "url": identity.get("url"),
            "title": identity.get("title"),
        },
        "url": value.get("url") or identity.get("url"),
        "title": value.get("title") or identity.get("title"),
        "slide_count": value.get("slide_count"),
        **(
            {"inspected_slides": value["inspected_slides"]}
            if "inspected_slides" in value
            else {}
        ),
        "slides": slide_summaries,
        "slides_omitted_from_context": max(0, len(raw_slides) - len(slide_summaries)),
        "context_char_budget": 12_000,
        "guidance": (
            PRESENTATION_SELECTOR_GUIDANCE + " Keep each tool_target's slide and "
            "selector together; paths are slide-local. Do not guess "
            "shape names or file paths. graphic_shapes lists top-level pictures; "
            "picture_containers adds non-duplicate groups that recursively contain "
            "pictures. media_shapes lists existing audio/video URLs and native "
            "selectors, so inspect it before inserting media. For an "
            "unqualified singular picture/photo/image, prefer a foreground_content "
            "candidate over a slide_cover candidate; choose slide_cover only when the "
            "instruction requests the background, cover, or full-slide image. "
            "Speaker notes are metadata, not visible slide text. An omitted count means "
            "more slides or shapes exist than fit in this compact view; presentation.inspect "
            "with explicit slides reads only those zero-based pages. shape.export_image "
            "exports to your output_path; use its returned path for file tools."
        ),
    }
    # Metadata and notes alone can exceed the budget. Keep complete early
    # observations and count omitted slides before deleting their useful text.
    if len(json.dumps(context, ensure_ascii=False, default=str)) > 12_000:
        return _compact_presentation_hint_for_model(context, 12_000)
    return context


def context_hint_for_model(
    domain: str,
    action: str,
    value: dict[str, Any],
    *,
    strict_generic: bool,
) -> dict[str, Any]:
    """Select the model-facing projection without changing stored evidence."""
    if strict_generic and _text_batch_observation(value):
        return text_batch_context_for_model(value)
    # ``multi_apps`` exposes a generic wrapper around OS Adapter calls.  Keep
    # the wrapper metadata while applying the same bounded projection to its
    # nested observation; this avoids routing decisions based on wrapper shape.
    nested = value.get("downstream_context")
    if strict_generic and isinstance(nested, dict):
        if _text_batch_observation(nested):
            projected = dict(value)
            projected["downstream_context"] = text_batch_context_for_model(nested)
            return projected
        # ``multi_apps.adapter.call`` wraps application observations.  Apply
        # the owning Impress projection inside that wrapper as well; otherwise
        # the generic fitter can spend the whole budget on slide text and
        # discard the exact graphic selectors needed by a later export or
        # image operation.
        if isinstance(nested.get("slides"), list) and any(
            isinstance(slide, dict)
            and (
                isinstance(slide.get("graphic_shapes"), list)
                or isinstance(slide.get("picture_containers"), list)
            )
            for slide in nested["slides"]
        ):
            projected = dict(value)
            projected["downstream_context"] = compact_presentation_hint_for_model(
                nested
            )
            return projected
    if (
        strict_generic
        and domain == "libreoffice_impress"
        and action == "presentation.inspect"
    ):
        return compact_presentation_hint_for_model(value)
    return value


def execution_context_summary(
    events: list[Any],
    domain: str,
    *,
    limit: int = 12,
    strict_generic: bool = False,
) -> list[dict[str, Any]]:
    """Compatibility wrapper for the bounded execution transcript."""
    return _summarize_events(
        events,
        domain,
        limit=limit,
        strict_generic=strict_generic,
        context_hint_for_model=context_hint_for_model,
    )


def has_passed_verification(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    verification = value.get("verification")
    if isinstance(verification, dict) and verification.get("passed") is True:
        return True
    if value.get("verification_passed") is True:
        return True
    return any(
        has_passed_verification(value.get(key))
        for key in (
            "context_hint",
            "adapter_response",
            "result",
            "response",
            "downstream_context",
        )
    )


def column_number(label: str) -> int:
    value = 0
    for character in label.upper():
        if not "A" <= character <= "Z":
            raise ValueError(f"invalid spreadsheet column: {label}")
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def column_label(number: int) -> str:
    if number < 1:
        raise ValueError(f"spreadsheet column number must be positive: {number}")
    label = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def a1_geometry(cell_range: str) -> tuple[str, int, str, int] | None:
    match = re.fullmatch(
        r"\$?([A-Za-z]+)\$?(\d+)(?::\$?([A-Za-z]+)\$?(\d+))?",
        cell_range.strip(),
    )
    if not match:
        return None
    start_column, start_row, end_column, end_row = match.groups()
    return (
        start_column.upper(),
        int(start_row),
        (end_column or start_column).upper(),
        int(end_row or start_row),
    )


def range_cell_addresses(cell_range: Any) -> list[list[str]] | None:
    """Return a positional A1 address matrix for one contiguous range."""
    if not isinstance(cell_range, str):
        return None
    geometry = a1_geometry(cell_range)
    if geometry is None:
        return None
    start_column, start_row, end_column, end_row = geometry
    start_index = column_number(start_column)
    end_index = column_number(end_column)
    return [
        [
            f"{column_label(column_index)}{row_number}"
            for column_index in range(start_index, end_index + 1)
        ]
        for row_number in range(start_row, end_row + 1)
    ]


def calc_summary_row_context(
    display_text: Any, kinds: Any, addresses: Any
) -> list[dict[str, Any]]:
    """Describe observed Total/Subtotal rows without choosing any mutation."""
    if not (
        isinstance(display_text, list)
        and isinstance(kinds, list)
        and isinstance(addresses, list)
    ):
        return []
    rows: list[dict[str, Any]] = []
    for row_index, values in enumerate(display_text):
        if not (
            isinstance(values, list)
            and row_index < len(kinds)
            and row_index < len(addresses)
            and isinstance(kinds[row_index], list)
            and isinstance(addresses[row_index], list)
        ):
            continue
        label_index = next(
            (
                index
                for index, value in enumerate(values)
                if isinstance(value, str)
                and value.strip().casefold() in _TABLE_ROW_SUMMARY_LABELS
            ),
            None,
        )
        if label_index is None:
            continue
        row_kinds = kinds[row_index]
        row_addresses = addresses[row_index]
        if any(
            row_kinds[index] != "blank"
            for index in range(min(label_index, len(row_kinds)))
        ):
            # A header such as ``Product | Q1 | Total`` is not a summary row;
            # only treat a leading Total/Subtotal label as row semantics.
            continue
        blank_cells = [
            row_addresses[index]
            for index in range(label_index + 1, min(len(row_kinds), len(row_addresses)))
            if row_kinds[index] == "blank"
        ]
        if not blank_cells:
            continue
        summary: dict[str, Any] = {
            "label": str(values[label_index]).strip(),
            "label_cell": row_addresses[label_index]
            if label_index < len(row_addresses)
            else None,
            "blank_cells": blank_cells,
        }

        # Give the model the observed detail-row span that feeds this summary.
        # This is derived only from the live matrix: stop at a header, category,
        # separator, or any row without numeric/formula cells.  The model still
        # chooses every destination cell and formula.
        detail_indices: list[int] = []
        for candidate in range(row_index - 1, -1, -1):
            candidate_values = display_text[candidate]
            candidate_kinds = kinds[candidate]
            if not (
                isinstance(candidate_values, list)
                and isinstance(candidate_kinds, list)
                and len(candidate_values) == len(candidate_kinds)
            ):
                break
            has_numeric = any(
                kind in {"number", "formula"}
                for kind in candidate_kinds[label_index + 1 :]
            )
            if not has_numeric:
                break
            detail_indices.append(candidate)
        if detail_indices:
            detail_indices.reverse()
            first_detail = detail_indices[0]
            detail_addresses = [
                addresses[index][0]
                for index in detail_indices
                if index < len(addresses)
                and isinstance(addresses[index], list)
                and addresses[index]
            ]
            if detail_addresses:
                row_numbers = [
                    match.group(1)
                    for address in detail_addresses
                    if isinstance(address, str)
                    and (match := re.search(r"([1-9][0-9]*)$", address))
                ]
                if row_numbers:
                    summary["detail_row_range"] = (
                        row_numbers[0]
                        if len(row_numbers) == 1
                        else f"{row_numbers[0]}:{row_numbers[-1]}"
                    )
            # Expose blank trailing Total cells on the detail rows as a second,
            # distinct target set. This is derived from the observed header and
            # live cell kinds; the model still selects each formula and address.
            header_total_index = None
            for candidate in range(first_detail - 1, -1, -1):
                candidate_values = display_text[candidate]
                if not isinstance(candidate_values, list):
                    continue
                total_index = next(
                    (
                        index
                        for index, value in enumerate(candidate_values)
                        if isinstance(value, str)
                        and value.strip().casefold() in {"total", "grand total"}
                    ),
                    None,
                )
                if total_index is not None and total_index > label_index:
                    header_total_index = total_index
                    break
            if header_total_index is not None:
                summary["period_cells"] = [
                    row_addresses[index]
                    for index in range(label_index + 1, header_total_index)
                    if index < len(row_addresses) and row_kinds[index] == "blank"
                ]
                if header_total_index < len(row_addresses):
                    summary["final_total_cell"] = row_addresses[header_total_index]
                summary["formula_roles"] = {
                    "period_cells": "vertical SUM of the same column over detail_row_range",
                    "final_total_cell": "horizontal SUM across period_cells on this summary row",
                }
                detail_total_cells = []
                for detail_index in detail_indices:
                    detail_kinds = kinds[detail_index]
                    if (
                        header_total_index >= len(detail_kinds)
                        or detail_kinds[header_total_index] != "blank"
                    ):
                        continue
                    if not any(
                        kind in {"number", "formula"}
                        for kind in detail_kinds[label_index + 1 : header_total_index]
                    ):
                        continue
                    detail_row_addresses = addresses[detail_index]
                    if isinstance(
                        detail_row_addresses, list
                    ) and header_total_index < len(detail_row_addresses):
                        detail_total_cells.append(
                            detail_row_addresses[header_total_index]
                        )
                if detail_total_cells:
                    summary["detail_total_cells"] = detail_total_cells
        rows.append(summary)
    return rows


def display_matrix_summary(value: Any) -> dict[str, Any] | None:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(row, list) for row in value)
    ):
        return None
    width = max((len(row) for row in value), default=0)
    if width < 1:
        return None
    columns = [
        [row[index] if index < len(row) else None for row in value]
        for index in range(width)
    ]
    error_count = sum(
        1
        for row in value
        for cell in row
        if str(cell)
        .strip()
        .upper()
        .startswith(("#NAME?", "#VALUE!", "#REF!", "#DIV/0!", "#N/A"))
    )
    return {
        "rows": len(value),
        "columns": width,
        "headers": [
            value[0][index] if index < len(value[0]) else None for index in range(width)
        ],
        "column_sha256": [
            hashlib.sha256(
                json.dumps(
                    column,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            for column in columns
        ],
        "error_count": error_count,
    }


def compact_adapter_body(body: Any, max_chars: int = 6000) -> Any:
    compacted = compact(body, max_chars)
    if not (
        isinstance(body, dict)
        and isinstance(compacted, dict)
        and compacted.get("truncated") is True
    ):
        return compacted

    summary: dict[str, Any] = {
        key: body[key]
        for key in ("status", "adapter", "action", "request_id")
        if key in body
    }
    verification = body.get("verification")
    if isinstance(verification, dict):
        summary["verification"] = {
            key: verification[key]
            for key in ("passed", "error_code", "details")
            if key in verification
        }
        checks = verification.get("checks")
        if isinstance(checks, list):
            summary["verification"]["check_count"] = len(checks)

    result = body.get("result")
    if isinstance(result, dict):
        result_summary: dict[str, Any] = {
            key: result[key]
            for key in (
                "route",
                "task_id",
                "prefix",
                "path",
                "url",
                "saved",
                "logs",
                "sheet",
                "range",
                "weekdays",
                "matched_cells",
                "matched_count",
                "background_cells",
                "date_cells",
                "background_cells_truncated",
                "date_cells_truncated",
                "truncated",
                "formatted_ranges",
                "destination_range",
                "source_sheet",
                "source_range",
                "destination_sheet",
                "operation",
                "header",
                "decimal_places",
                "written_cells",
                "filled_cells",
                "error_cells",
            )
            if key in result
        }
        display = result.get("display_text")
        if not isinstance(display, list) and isinstance(result.get("readback"), dict):
            display = result["readback"].get("display_text")
        if display_summary := display_matrix_summary(display):
            result_summary["display_summary"] = display_summary
            encoded_display = json.dumps(display, ensure_ascii=False, default=str)
            if len(encoded_display) <= 4000:
                result_summary["display_text"] = display
        formulas = result.get("formulas")
        if not isinstance(formulas, list) and isinstance(result.get("readback"), dict):
            formulas = result["readback"].get("formulas")
        if isinstance(formulas, list):
            encoded_formulas = json.dumps(formulas, ensure_ascii=False, default=str)
            if len(encoded_formulas) <= 4000:
                result_summary["formulas"] = formulas
        styles = result.get("styles")
        if not isinstance(styles, list) and isinstance(result.get("readback"), dict):
            styles = result["readback"].get("styles")
        cell_range = str(result.get("range", ""))
        geometry = a1_geometry(cell_range)
        if isinstance(styles, list) and geometry is not None:
            style_cells: dict[str, Any] = {}
            start_column = column_number(geometry[0])
            start_row = geometry[1]
            for row_offset, row in enumerate(styles):
                if not isinstance(row, list):
                    continue
                for column_offset, style in enumerate(row):
                    if not isinstance(style, dict):
                        continue
                    if (
                        str(style.get("background_color", "")).casefold() == "#ffffff"
                        and str(style.get("font_color", "")).casefold() == "#000000"
                        and style.get("bold") is not True
                    ):
                        continue
                    coordinate = (
                        f"{column_label(start_column + column_offset)}"
                        f"{start_row + row_offset}"
                    )
                    style_cells[coordinate] = style
            if style_cells:
                result_summary["style_cells"] = style_cells
        outputs = result.get("outputs")
        if isinstance(outputs, list):
            result_summary["outputs"] = [
                {
                    key: output[key]
                    for key in ("destination", "path", "size", "sha256")
                    if key in output
                }
                for output in outputs
                if isinstance(output, dict)
            ]
        nested_verification = result.get("verification")
        if isinstance(nested_verification, dict):
            result_summary["verification"] = {
                key: nested_verification[key]
                for key in ("passed", "error_code", "details")
                if key in nested_verification
            }
        if result_summary:
            summary["result"] = result_summary

    summary.update(compacted)
    return summary


def flattened_shape_summaries(shapes: Any) -> list[dict[str, Any]]:
    if not isinstance(shapes, list):
        return []
    flattened: list[dict[str, Any]] = []
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        flattened.append(shape)
        flattened.extend(flattened_shape_summaries(shape.get("children")))
    return flattened


def picture_container_summaries(shapes: Any) -> list[dict[str, Any]]:
    """Summarize top-level shapes that are or recursively contain pictures."""
    if not isinstance(shapes, list):
        return []
    containers: list[dict[str, Any]] = []
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        graphics = [
            item
            for item in flattened_shape_summaries([shape])
            if "graphicobjectshape" in str(item.get("kind", "")).casefold()
        ]
        bitmap_fills = [
            item
            for item in flattened_shape_summaries([shape])
            if str(item.get("fill_style", "")).casefold() == "bitmap"
        ]
        if not graphics and not bitmap_fills:
            continue
        containers.append(
            {
                key: shape.get(key)
                for key in (
                    "index",
                    "path",
                    "name",
                    "kind",
                    "x",
                    "y",
                    "width",
                    "height",
                    "visible",
                )
            }
            | {
                "graphic_count": len(graphics),
                "graphic_paths": [item.get("path") for item in graphics],
            }
            | (
                {
                    "bitmap_fill_count": len(bitmap_fills),
                    "bitmap_fill_paths": [item.get("path") for item in bitmap_fills],
                }
                if bitmap_fills
                else {}
            )
        )
    return containers


def writer_paragraph_context(result: dict[str, Any]) -> dict[str, Any]:
    raw_details = result.get("paragraph_details")
    details = [item for item in raw_details or [] if isinstance(item, dict)]
    paged = "paragraph_start" in result or "paragraph_limit" in result
    paragraph_count = result.get("paragraph_count")
    nonempty_count = result.get("nonempty_paragraph_count")
    if (
        not details
        and not isinstance(paragraph_count, int)
        and not isinstance(nonempty_count, int)
    ):
        return {}
    if len(details) > 24:
        selected = [*details[:12], *details[-12:]]
        omitted = len(details) - len(selected)
    else:
        selected = details
        omitted = 0
    compact_details = [
        {
            key: item.get(key)
            for key in (
                "index",
                "nonempty_ordinal",
                "line_spacing",
                "alignment",
                "font_size",
                "strikethrough",
            )
        }
        | (
            {"numbering": item["numbering"]}
            if isinstance(item.get("numbering"), dict)
            else {}
        )
        | {
            key: item[key]
            for key in (
                "tab_stops", "has_tab_character", "tab_character_offsets",
                "literal_tab_escape_count", "text_length",
            )
            if key in item
        }
        | {"text": str(item.get("text", ""))[: None if paged else 180]}
        for item in selected
    ]
    return {
        "paragraph_count": paragraph_count,
        "nonempty_paragraph_count": nonempty_count,
        "valid_raw_index_range": [0, paragraph_count - 1]
        if isinstance(paragraph_count, int) and paragraph_count > 0
        else [],
        "valid_nonempty_paragraph_number_range": [1, nonempty_count]
        if isinstance(nonempty_count, int) and nonempty_count > 0
        else [],
        "paragraph_details": compact_details,
        "paragraph_details_omitted": omitted,
        "guidance": (
            "text_length is the full native paragraph length; overview text is a preview. "
            "Before replacing text, read the selected paragraph with document.inspect, "
            "paragraph_start=<its index>, paragraph_limit=1. context_truncated or "
            "...<truncated>... means the context is still partial; do not reconstruct "
            "missing wording."
        ),
    } | {
        key: result[key]
        for key in (
            "paragraph_start",
            "paragraph_limit",
            "next_paragraph_start",
            "has_more",
        )
        if key in result
    }


def thunderbird_message_query_context(result: dict[str, Any]) -> dict[str, Any]:
    raw_messages = result.get("messages")
    messages = [item for item in raw_messages or [] if isinstance(item, dict)]
    context: dict[str, Any] = {
        "folder": result.get("folder"),
        "matched_count": result.get("matched_count"),
        "returned_count": result.get("returned_count"),
        "select_from": result.get("select_from"),
        "order": result.get("order"),
        "mailbox_indices": [
            item.get("mailbox_index")
            for item in messages
            if isinstance(item.get("mailbox_index"), int)
            and not isinstance(item.get("mailbox_index"), bool)
        ],
        "messages": [],
        "messages_omitted": len(messages),
    }
    for message in messages[:20]:
        row = {
            key: str(message.get(key, ""))[:300]
            for key in (
                "sender_name",
                "sender_address",
                "to",
                "cc",
                "subject",
                "date",
            )
        } | {
            "mailbox_index": message.get("mailbox_index"),
            "number_of_attachments": message.get("number_of_attachments"),
            "starred": message.get("starred"),
            "attachment_names": [
                str(name)[:100] for name in message.get("attachment_names", [])[:10]
            ]
            if isinstance(message.get("attachment_names"), list)
            else [],
        }
        message_id = message.get("message_id")
        if isinstance(message_id, str) and message_id.strip():
            row["message_id"] = message_id.strip()[:300]
        context["messages"].append(row)
        context["messages_omitted"] = len(messages) - len(context["messages"])
        if len(json.dumps(context, ensure_ascii=False, default=str)) > 4200:
            context["messages"].pop()
            context["messages_omitted"] = len(messages) - len(context["messages"])
            break
    context["selector_guidance"] = (
        "Use the exact mailbox_index from each returned message. Include message_id only "
        "when that field is present; omit it when the mailbox has no Message-ID."
    )
    if context["matched_count"] != context["returned_count"]:
        context["selector_guidance"] += (
            " The query did not return every matching message; do not apply a folder-wide "
            "change until the remaining matches are queried."
        )
    return context


def json_string_content_length(value: str) -> int:
    return len(json.dumps(value, ensure_ascii=False)) - 2


def json_prefix_within_budget(value: str, encoded_budget: int, max_chars: int) -> str:
    upper = min(len(value), max_chars)
    if upper <= 0 or encoded_budget <= 0:
        return ""
    if json_string_content_length(value[:upper]) <= encoded_budget:
        return value[:upper]
    lower = 0
    while lower < upper:
        middle = (lower + upper + 1) // 2
        if json_string_content_length(value[:middle]) <= encoded_budget:
            lower = middle
        else:
            upper = middle - 1
    return value[:lower]


def _table_row_windows(
    text: str,
    *,
    offset_base: int,
    total_chars: int,
    source_has_more: bool,
    offset_basis: str = "adapter_returned_text",
    excluded: list[tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    """Select a few high-information row windows from a long text result.

    PDF/OCR output is often a flattened table.  A prefix/suffix projection can
    therefore omit the only row that identifies a summary or a numeric record.
    This helper keeps bounded, *observed* line slices with absolute offsets; it
    never parses, computes, or supplies a value.  The marker and density rules
    are intentionally generic so the same projection works for reports,
    invoices, and other tabular documents.
    """
    if not text:
        return []
    excluded = excluded or []
    lines: list[tuple[int, int, str, int, int, bool]] = []
    header_start: int | None = None
    header_end = 0
    header_closed = False
    cursor = 0
    for raw_line in text.splitlines(keepends=True):
        start = cursor
        cursor += len(raw_line)
        content = raw_line.rstrip("\r\n")
        if not content.strip():
            continue
        # A row candidate has either explicit column separators with numeric
        # content or a generic summary label.  Plain prose is left untouched.
        tab_count = content.count("\t")
        number_count = len(_TABLE_ROW_NUMBER_RE.findall(content))
        # Keep adjacent label rows together before numeric records. Splitting
        # a grouped header can hide whether a number is a count or an amount.
        if not header_closed:
            if tab_count >= 2 and number_count == 0:
                if header_start is None:
                    header_start = start
                header_end = cursor
            elif (
                header_start is not None
                or sum(
                    _TABLE_ROW_NUMBER_RE.fullmatch(cell.strip()) is not None
                    for cell in content.split("\t")
                )
                >= 2
            ):
                header_closed = True
        summary = bool(_TABLE_ROW_SUMMARY_RE.search(content))
        if not summary:
            # ``pdftotext -layout`` can split a label into character groups
            # (for example ``T o t al``).  Restrict the normalization to the
            # first tab-delimited label so ordinary prose containing a word
            # such as "result" is never promoted to a table row.
            label = content.split("\t", 1)[0].strip()
            compact_label = re.sub(r"[^A-Za-z]", "", label).casefold()
            summary = any(
                compact_label.endswith(marker) for marker in _TABLE_ROW_SUMMARY_LABELS
            )
        if not ((tab_count >= 2 and number_count >= 2) or (summary and tab_count >= 1)):
            continue
        lines.append((start, cursor, content, tab_count, number_count, summary))
    if not lines:
        return []
    if header_start is not None:
        header_text = text[header_start:header_end].rstrip("\r\n")
        lines = [item for item in lines if not header_start <= item[0] < header_end]
        lines.append((header_start, header_end, header_text, 0, 0, False))

    def score(item: tuple[int, int, str, int, int, bool]) -> tuple[int, ...]:
        start, _end, row_text, tabs, numbers, summary = item
        label = row_text.split("\t", 1)[0].strip()
        compact_label = re.sub(r"[^A-Za-z]", "", label).casefold()
        # Prefer an aggregate ``Total`` row over a section heading when both
        # fit the small per-file allowance.  The distinction is based only on
        # the observed label; no values are interpreted or synthesized.
        overall_total = compact_label in {"total", "grandtotal"}
        return (
            int(overall_total and numbers > 0),
            int(start == header_start),
            int(summary),
            min(tabs, 24),
            min(numbers, 24),
            -start,
        )

    selected: list[tuple[int, int, str, int, int, bool]] = []
    for candidate in sorted(lines, key=score, reverse=True):
        start, end, content, _tabs, _numbers, _summary = candidate
        # Keep summary rows even when a coarse head/tail chunk currently
        # overlaps them.  That chunk may be shortened by a later recovery
        # budget pass; dropping the row here would make the useful middle
        # observation disappear permanently.
        if (
            start != header_start
            and not candidate[5]
            and any(
                start < other_end and end > other_start
                for other_start, other_end in excluded
            )
        ):
            continue
        selected.append(candidate)
        if len(selected) >= TEXT_BATCH_MODEL_TABLE_ROWS_PER_FILE:
            break
    selected.sort(key=lambda item: item[0])

    rows: list[dict[str, Any]] = []
    for index, (start, end, content, _tabs, _numbers, _summary) in enumerate(selected):
        visible = content[:TEXT_BATCH_MODEL_TABLE_ROW_MAX_CHARS]
        row_end = start + len(visible)
        rows.append(
            {
                "type": "table_header" if start == header_start else "table_row",
                "offset_basis": offset_basis,
                "index": index,
                "start_char": offset_base + start,
                "end_char": offset_base + row_end,
                "total_chars": max(total_chars, offset_base + len(text)),
                "text": visible,
                "source_has_more": bool(source_has_more),
                "context_has_more": len(visible) < len(content),
                "has_more": bool(source_has_more),
                "line_end_char": offset_base + end,
            }
        )
    return rows


def fair_encoded_text_budgets(capacities: list[int], total: int) -> list[int]:
    budgets = [0] * len(capacities)
    remaining = set(range(len(capacities)))
    available = max(0, total)
    while remaining and available > 0:
        share = available // len(remaining)
        if share <= 0:
            break
        completed = {index for index in remaining if capacities[index] <= share}
        if not completed:
            for index in remaining:
                budgets[index] = share
            break
        for index in completed:
            budgets[index] = capacities[index]
            available -= capacities[index]
        remaining -= completed
    return budgets


def pdf_text_batch_context(result: dict[str, Any]) -> dict[str, Any]:
    raw_files = result.get("files")
    files = [item for item in raw_files or [] if isinstance(item, dict)]
    selected = files[:TEXT_BATCH_CONTEXT_MAX_FILES]
    context: dict[str, Any] = {
        "input_directory": result.get("input_directory"),
        "input_pattern": result.get("input_pattern"),
        "start_page": result.get("start_page"),
        "page_count": result.get("page_count"),
        "max_pages_per_pdf": result.get("max_pages_per_pdf"),
        "ocr_engine": result.get("ocr_engine"),
        "ocr_language": result.get("ocr_language"),
        "matched_count": len(files),
        "total_returned_chars": result.get("total_returned_chars"),
        "context_char_budget": TEXT_BATCH_CONTEXT_MAX_CHARS,
        "files": [
            {
                "path": item.get("path"),
                "status": item.get("status"),
                "returned_chars": item.get("returned_chars"),
                "extracted_chars": item.get("extracted_chars"),
                "raw_extracted_chars": item.get("raw_extracted_chars"),
                "layout_compacted": item.get("layout_compacted"),
                "source_start_char": item.get("source_start_char", 0),
                "source_end_char": item.get("source_end_char"),
                "source_total_chars": item.get(
                    "source_total_chars", item.get("extracted_chars")
                ),
                "next_start_char": item.get("next_start_char"),
                "offset_basis": item.get("offset_basis"),
                "source_truncated": item.get("source_truncated", item.get("truncated")),
                "source_kind": item.get("source_kind"),
                "pages_processed": item.get("pages_processed"),
                "empty_text": item.get("empty_text"),
                "text": "",
                "context_truncated": True,
            }
            for item in selected
        ],
        "files_omitted": len(files) - len(selected),
        "context_files_omitted": len(files) - len(selected),
        "source_has_more": any(_source_has_more_for_item(item) for item in files),
        "visible_text_chars": TEXT_BATCH_CONTEXT_MAX_CHARS,
        "all_text_visible": False,
        "guidance": (
            "Some text is shortened only in model context. To inspect more, rerun with "
            "input_pattern set to one returned basename or a narrower pattern and optionally "
            "limit the page range. Increasing max_chars_per_file alone cannot exceed the "
            "bounded model-context budget."
        ),
    }
    # Preserve generic receipt/invoice final-amount evidence beside each file.
    # This is derived only from the OCR text and applies to any batch source.
    financial_hints = []
    for item, destination in zip(selected, context["files"], strict=True):
        hint = _financial_amount_hint(str(item.get("text", "")))
        if hint is None:
            continue
        destination["financial_amount_hint"] = hint
        # A bookkeeping consumer can use this structured candidate directly;
        # it is derived from the observed receipt text and remains generic.
        amount = hint.get("amount")
        if isinstance(amount, (int, float)) and not isinstance(amount, bool):
            destination["expense_entry"] = {
                "type": "Expense",
                "amount": -abs(amount),
            }
        label = hint.get("label")
        path = destination.get("path")
        if isinstance(path, str) and isinstance(amount, (int, float)) and not isinstance(amount, bool):
            financial_hints.append(f"{path} -> {amount:g} ({label})")
    encoded_without_text = json.dumps(context, ensure_ascii=False, default=str)
    available = max(0, TEXT_BATCH_CONTEXT_MAX_CHARS - len(encoded_without_text))
    source_texts = [str(item.get("text", "")) for item in selected]
    capacities = [
        json_string_content_length(text[:TEXT_BATCH_CONTEXT_PER_FILE_MAX_CHARS])
        for text in source_texts
    ]
    budgets = fair_encoded_text_budgets(capacities, available)
    for text, budget, destination in zip(
        source_texts, budgets, context["files"], strict=True
    ):
        destination["text"] = json_prefix_within_budget(
            text, budget, TEXT_BATCH_CONTEXT_PER_FILE_MAX_CHARS
        )
        destination["context_truncated"] = len(destination["text"]) < len(text)
    truncated_files = sum(item["context_truncated"] for item in context["files"])
    context["visible_text_chars"] = sum(len(item["text"]) for item in context["files"])
    context["all_text_visible"] = (
        not context["context_files_omitted"] and not truncated_files
    )
    context["guidance"] = (
        "All returned text is visible in this context; use it before repeating extraction."
        if context["all_text_visible"]
        else (
            "Some text is shortened only in model context. To inspect more, rerun with "
            "input_pattern set to one returned basename or a narrower pattern and optionally "
            "limit the page range. Increasing max_chars_per_file alone cannot exceed the "
            "bounded model-context budget."
        )
    )
    if financial_hints:
        context["guidance"] += (
            " For receipts or invoices, use the final labeled amount near the end "
            "(TOTAL, BALANCE, AMOUNT DUE, PAID, or TAKE-OUT TOTAL); when present, "
            "use files[].financial_amount_hint.amount and evidence; for an expense "
            "ledger use files[].expense_entry. Observed mapping: "
            + "; ".join(financial_hints)
            + ". Do not substitute a product price, subtotal, or unrelated number."
            " For a bookkeeping instruction that asks for expenses, classify each "
            "receipt, invoice, or cash-out source as Type=Expense and write the amount "
            "as negative even when OCR displays a positive total; extend a Balance "
            "column with =previous_balance+current_amount for each appended row."
        )
    return context


def _text_batch_observation(value: dict[str, Any]) -> bool:
    """Return whether ``value`` has the public shape of a text batch result."""
    files = value.get("files")
    return isinstance(files, list) and any(
        isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and ("text" in item or "returned_chars" in item)
        for item in files
    )


def _source_has_more_for_item(item: dict[str, Any]) -> bool:
    """Return whether an Adapter file result has an unread source window.

    ``truncated`` and character-count differences predate the model-context
    projection and are ambiguous once an Adapter compacts layout text. A
    continuation is scheduled only from an explicit source flag or a
    coherent source window; context-only metadata remains inert.
    """
    explicit = item.get("source_has_more")
    if isinstance(explicit, bool):
        return explicit

    source_start = item.get("source_start_char")
    source_end = item.get("source_end_char")
    source_total = item.get("source_total_chars")
    has_window = any(
        key in item
        for key in ("source_end_char", "source_total_chars", "next_start_char")
    )
    if has_window:
        valid_window = all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (source_start, source_end, source_total)
        )
        if valid_window:
            if source_end < source_total:
                return True
            next_start = item.get("next_start_char")
            if (
                isinstance(next_start, int)
                and not isinstance(next_start, bool)
                and next_start > source_end
            ):
                return True
            return False

    source_truncated = item.get("source_truncated")
    if isinstance(source_truncated, bool):
        return source_truncated
    truncated = item.get("truncated")
    if isinstance(truncated, bool):
        return truncated

    # Layout compaction changes representation length, not the source cursor.
    if item.get("layout_compacted") is True:
        return False
    extracted = item.get("extracted_chars")
    text = item.get("text")
    return (
        isinstance(extracted, int)
        and not isinstance(extracted, bool)
        and isinstance(text, str)
        and extracted > len(text)
    )


def _text_chunk(
    *,
    index: int,
    start_char: int,
    end_char: int,
    total_chars: int,
    text: str,
    source_has_more: bool,
    context_has_more: bool = False,
    offset_basis: str = "adapter_returned_text",
) -> dict[str, Any]:
    """Build one truthful source slice for a model-facing batch projection.

    ``has_more`` is retained as a compatibility alias for the source cursor.
    A model-context cap is represented separately by ``context_has_more`` so a
    shortened projection cannot be mistaken for an unread source window.
    """
    return {
        "type": "text",
        "offset_basis": offset_basis,
        "index": index,
        "start_char": start_char,
        "end_char": end_char,
        "total_chars": total_chars,
        "text": text,
        "source_has_more": bool(source_has_more),
        "context_has_more": bool(context_has_more),
        "has_more": bool(source_has_more),
    }


def _head_tail_text_chunks(
    text: str,
    *,
    visible_chars: int,
    total_chars: int,
    source_has_more: bool,
    context_has_more: bool = False,
    offset_base: int = 0,
    offset_basis: str = "adapter_returned_text",
) -> list[dict[str, Any]]:
    """Keep a bounded head and tail without falsifying source offsets."""
    if not text or visible_chars <= 0:
        return []
    if isinstance(offset_base, bool) or not isinstance(offset_base, int):
        offset_base = 0
    offset_base = max(0, offset_base)
    total_chars = max(total_chars, offset_base + len(text))
    visible_chars = min(len(text), visible_chars)
    if visible_chars == len(text):
        return [
            _text_chunk(
                index=0,
                start_char=offset_base,
                end_char=offset_base + len(text),
                total_chars=total_chars,
                text=text,
                source_has_more=source_has_more,
                context_has_more=context_has_more,
                offset_basis=offset_basis,
            )
        ]
    if visible_chars == 1:
        return [
            _text_chunk(
                index=0,
                start_char=offset_base,
                end_char=offset_base + 1,
                total_chars=total_chars,
                text=text[:1],
                source_has_more=source_has_more,
                context_has_more=True,
                offset_basis=offset_basis,
            )
        ]
    head_chars = (visible_chars + 1) // 2
    tail_chars = visible_chars - head_chars
    tail_start = len(text) - tail_chars
    return [
        _text_chunk(
            index=0,
            start_char=offset_base,
            end_char=offset_base + head_chars,
            total_chars=total_chars,
            text=text[:head_chars],
            source_has_more=source_has_more,
            context_has_more=True,
            offset_basis=offset_basis,
        ),
        _text_chunk(
            index=1,
            start_char=offset_base + tail_start,
            end_char=offset_base + len(text),
            total_chars=total_chars,
            text=text[tail_start:],
            source_has_more=source_has_more,
            context_has_more=True,
            offset_basis=offset_basis,
        ),
    ]


def text_batch_context_for_model(
    value: dict[str, Any], *, max_chars: int = TEXT_BATCH_MODEL_CONTEXT_MAX_CHARS
) -> dict[str, Any]:
    """Project a PDF/OCR batch into bounded, typed model-facing observations.

    The complete extraction remains in the event trace.  The model receives
    exact handles and bounded metadata for every visible file plus bounded,
    explicitly typed text chunks per file.  ``has_more`` and offsets distinguish source
    truncation from context truncation, so a follow-up can narrow the
    model-selected pattern/page range instead of guessing a path or treating a
    prefix of a JSON serialization as a complete record.
    """
    raw_files = value.get("files")
    if not isinstance(raw_files, list):
        return value
    selected = [item for item in raw_files if isinstance(item, dict)][
        :TEXT_BATCH_CONTEXT_MAX_FILES
    ]
    omitted = max(0, len(raw_files) - len(selected))
    # ``files_omitted`` is a model-context property.  It must not be confused
    # with source pagination: the Adapter may have returned every source file
    # successfully while this projection keeps only a bounded prefix.
    source_has_more = False
    for item in raw_files:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        text_length = len(text) if isinstance(text, str) else 0
        source_start = item.get("source_start_char", 0)
        if (
            isinstance(source_start, bool)
            or not isinstance(source_start, int)
            or source_start < 0
        ):
            source_start = 0
        source_end = item.get("source_end_char")
        if isinstance(source_end, bool) or not isinstance(source_end, int):
            source_end = source_start + text_length
        source_end = max(source_end, source_start + text_length)
        source_total = item.get("source_total_chars", item.get("extracted_chars"))
        if isinstance(source_total, bool) or not isinstance(source_total, int):
            source_total = source_end
        source_total = max(source_total, source_end)
        source_has_more = source_has_more or _source_has_more_for_item(item)
    context: dict[str, Any] = {
        "observation_type": "text_batch",
        "input_directory": value.get("input_directory"),
        "input_pattern": value.get("input_pattern"),
        "start_page": value.get("start_page"),
        "page_count": value.get("page_count"),
        "max_pages_per_pdf": value.get("max_pages_per_pdf"),
        "ocr_engine": value.get("ocr_engine"),
        "ocr_language": value.get("ocr_language"),
        "matched_count": value.get("matched_count", len(raw_files)),
        "files": [],
        "files_omitted": omitted,
        "context_files_omitted": omitted,
        "context_char_budget": max_chars,
        # ``source_has_more`` describes the Adapter response, while
        # ``context_truncated`` describes only this model-facing projection.
        # Keeping them separate prevents a local context cap from scheduling
        # an unnecessary repeat of an already complete source read.
        "source_has_more": source_has_more,
        "context_truncated": bool(omitted),
        "has_more": bool(source_has_more or omitted),
    }
    for key in (
        "reader_action",
        "sibling_file_paths",
        "sibling_file_count",
        "sibling_files_omitted_from_context",
        "sibling_files_truncated",
    ):
        if key in value:
            context[key] = value[key]
    file_sources: list[dict[str, Any]] = []
    for item in selected:
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        text = item.get("text")
        text = text if isinstance(text, str) else ""
        extracted_chars = item.get("extracted_chars")
        if not isinstance(extracted_chars, int) or isinstance(extracted_chars, bool):
            extracted_chars = len(text)
        extracted_chars = max(extracted_chars, len(text))
        source_start = item.get("source_start_char", 0)
        if (
            isinstance(source_start, bool)
            or not isinstance(source_start, int)
            or source_start < 0
        ):
            source_start = 0
        source_end = item.get("source_end_char")
        if isinstance(source_end, bool) or not isinstance(source_end, int):
            source_end = source_start + len(text)
        source_end = max(source_end, source_start + len(text))
        source_total = item.get("source_total_chars", extracted_chars)
        if isinstance(source_total, bool) or not isinstance(source_total, int):
            source_total = extracted_chars
        source_total = max(source_total, source_end)
        source_truncated = bool(item.get("source_truncated", item.get("truncated")))
        source_has_more = _source_has_more_for_item(item)
        next_start = item.get("next_start_char")
        if isinstance(next_start, bool) or not isinstance(next_start, int):
            next_start = source_end if source_has_more else None
        offset_basis = item.get("offset_basis")
        if not isinstance(offset_basis, str) or not offset_basis:
            offset_basis = "adapter_returned_text"
        metadata = {
            key: item.get(key)
            for key in (
                "status",
                "source_kind",
                "pages_processed",
                "returned_chars",
                "extracted_chars",
                "raw_extracted_chars",
                "source_start_char",
                "source_end_char",
                "source_total_chars",
                "next_start_char",
                "offset_basis",
                "empty_text",
            )
            if key in item
        }
        metadata["source_truncated"] = source_truncated
        context["files"].append(
            {
                "handle": {"kind": "file", "path": path},
                "path": path,
                "metadata": metadata,
                "chunks": [],
                "chunk_count": 0,
                "table_rows": [],
                "source_start_char": source_start,
                "source_end_char": source_end,
                "source_total_chars": source_total,
                "next_start_char": next_start,
                "offset_basis": offset_basis,
                "source_has_more": source_has_more,
                "has_more": source_has_more,
                "context_truncated": False,
            }
        )
        financial_hint = _financial_amount_hint(text)
        if financial_hint is not None:
            context["files"][-1]["financial_amount_hint"] = financial_hint
        file_sources.append(item)

    # Reserve room for handles/metadata first.  Text is optional; losing a
    # chunk must never remove the exact path needed for a follow-up action.
    encoded_skeleton = json.dumps(context, ensure_ascii=False, default=str)
    available = max(0, max_chars - len(encoded_skeleton))
    text_items = [
        (item, destination)
        for item, destination in zip(file_sources, context["files"], strict=True)
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]
    capacities = [
        json_string_content_length(
            str(item.get("text", ""))[:TEXT_BATCH_MODEL_CHUNK_MAX_CHARS]
        )
        for item, _destination in text_items
    ]
    # Account for two typed chunk envelopes before fair-sharing the remaining
    # budget.  The final hard-cap pass below still measures the full object,
    # including escaping and per-chunk metadata.
    budgets = fair_encoded_text_budgets(
        capacities,
        max(0, available - 360 * len(text_items)),
    )
    for (item, destination), budget in zip(text_items, budgets, strict=True):
        text = str(item.get("text", ""))
        visible_text = json_prefix_within_budget(
            text,
            budget,
            TEXT_BATCH_MODEL_CHUNK_MAX_CHARS,
        )
        source_start = destination.get("source_start_char", 0)
        source_end = destination.get("source_end_char")
        source_total = destination.get("source_total_chars")
        if isinstance(source_start, bool) or not isinstance(source_start, int):
            source_start = 0
        if isinstance(source_end, bool) or not isinstance(source_end, int):
            source_end = source_start + len(text)
        source_end = max(source_end, source_start + len(text))
        if isinstance(source_total, bool) or not isinstance(source_total, int):
            source_total = destination["metadata"].get("extracted_chars", len(text))
        source_total = max(source_total, source_end)
        context_more = len(visible_text) < len(text)
        source_has_more = bool(destination.get("source_has_more"))
        destination["chunks"] = _head_tail_text_chunks(
            text,
            visible_chars=len(visible_text),
            total_chars=source_total,
            source_has_more=source_has_more,
            context_has_more=context_more,
            offset_base=source_start,
            offset_basis=str(
                destination.get("offset_basis") or "adapter_returned_text"
            ),
        )
        destination["chunk_count"] = len(destination["chunks"])
        excluded_spans = [
            (chunk.get("start_char", source_start), chunk.get("end_char", source_start))
            for chunk in destination["chunks"]
            if isinstance(chunk, dict)
            and isinstance(chunk.get("start_char"), int)
            and isinstance(chunk.get("end_char"), int)
        ]
        destination["table_rows"] = _table_row_windows(
            text,
            offset_base=source_start,
            total_chars=source_total,
            source_has_more=source_has_more,
            offset_basis=destination["offset_basis"],
            excluded=[
                (start - source_start, end - source_start)
                for start, end in excluded_spans
                if end >= start
            ],
        )
        destination["context_truncated"] = context_more
        destination["context_has_more"] = context_more
        destination["source_has_more"] = source_has_more
        destination["has_more"] = source_has_more or context_more

    source_more = bool(context.get("source_has_more")) or any(
        bool(item.get("source_has_more")) for item in context["files"]
    )
    truncated = bool(context.get("context_files_omitted")) or any(
        bool(item.get("context_has_more") or item.get("context_truncated"))
        for item in context["files"]
    )
    context["source_has_more"] = source_more
    context["context_truncated"] = truncated
    context["has_more"] = source_more or truncated
    context["guidance"] = (
        TEXT_FILE_READING_GUIDANCE
        if context.get("reader_action") == "file.read_text"
        else WRITER_TEXT_READING_GUIDANCE
        if context.get("reader_action") == "document.read_file"
        else TEXT_BATCH_READING_GUIDANCE
    )
    financial_hints = []
    for item in context.get("files", []):
        hint = item.get("financial_amount_hint") if isinstance(item, dict) else None
        path = item.get("path") if isinstance(item, dict) else None
        if isinstance(hint, dict) and isinstance(path, str):
            amount = hint.get("amount")
            label = hint.get("label")
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                financial_hints.append(f"{path} -> {amount:g} ({label})")
    if financial_hints:
        context["guidance"] += (
            " Observed final-payment mapping for ledger use, in source-file order: "
            + "; ".join(financial_hints)
            + ". Use one row per listed file and the mapped amount; do not infer a different number."
        )

    # Table rows add their own envelopes after the initial text allocation.
    # Fit the complete shape, releasing redundant metadata before source text.
    if len(json.dumps(context, ensure_ascii=False, default=str)) > max_chars:
        _slim_batch_optional_fields(context)
        context["context_char_budget"] = max_chars
    if len(json.dumps(context, ensure_ascii=False, default=str)) > max_chars:
        _fit_batch_text_windows(context, max_chars)
    optional_top_level = (
        "sibling_file_paths",
        "sibling_file_count",
        "sibling_files_omitted_from_context",
        "sibling_files_truncated",
        "guidance",
        "ocr_language",
        "ocr_engine",
        "max_pages_per_pdf",
        "page_count",
        "start_page",
    )
    # If unusually long handles or metadata leave no room even for the text
    # pass above, remove optional fields and whole file records from the
    # middle.  Exact handles that remain are never replaced or synthesized.
    while len(json.dumps(context, ensure_ascii=False, default=str)) > max_chars:
        removed = False
        for key in optional_top_level:
            if key in context:
                context.pop(key)
                removed = True
                break
        if removed:
            continue
        if len(context["files"]) > 1:
            context["files"].pop(len(context["files"]) // 2)
            context["files_omitted"] += 1
            context["context_files_omitted"] += 1
            context["context_truncated"] = True
            context["context_has_more"] = True
            context["has_more"] = True
            continue
        if context["files"]:
            file = context["files"][0]
            metadata = file.get("metadata")
            if isinstance(metadata, dict) and metadata:
                # Keep status and source truncation first; the other fields
                # are useful but optional under an extreme caller budget.
                removable_keys = [
                    key for key in metadata if key not in {"status", "source_truncated"}
                ]
                if removable_keys:
                    metadata.pop(removable_keys[-1])
                    continue
            chunks = file.get("chunks")
            if isinstance(chunks, list) and chunks:
                chunks.clear()
                file["chunk_count"] = 0
                file["context_truncated"] = True
                file["context_has_more"] = True
                file["has_more"] = bool(file.get("source_has_more"))
                continue
        # A caller budget smaller than one complete handle cannot preserve the
        # full path and a valid JSON envelope simultaneously.  Return a small
        # truthful batch marker rather than violating the advertised bound.
        context = {
            "observation_type": "text_batch",
            "files": [],
            "files_omitted": max(1, len(raw_files)),
            "context_files_omitted": max(1, len(raw_files)),
            "source_has_more": False,
            "context_char_budget": max_chars,
            "context_truncated": True,
            "has_more": True,
        }
        break
    for file in context["files"]:
        chunk_context_more = any(
            bool(chunk.get("context_has_more"))
            for chunk in file.get("chunks", [])
            if isinstance(chunk, dict)
        )
        file_context_more = bool(
            file.get("context_has_more")
            or file.get("context_truncated")
            or chunk_context_more
        )
        file["context_has_more"] = file_context_more
        file["context_truncated"] = file_context_more
        file["has_more"] = bool(file.get("source_has_more") or file_context_more)
    context["context_truncated"] = bool(
        context.get("context_files_omitted")
        or any(
            file.get("context_has_more") or file.get("context_truncated")
            for file in context["files"]
        )
    )
    context["source_has_more"] = bool(
        context.get("source_has_more")
        or any(bool(file.get("source_has_more")) for file in context["files"])
    )
    context["has_more"] = bool(
        context["source_has_more"] or context["context_truncated"]
    )
    return context


def spreadsheet_file_context(result: dict[str, Any]) -> dict[str, Any]:
    raw_sheets = result.get("sheets")
    sheets = [item for item in raw_sheets or [] if isinstance(item, dict)]
    context: dict[str, Any] = {
        key: result.get(key)
        for key in (
            "path",
            "url",
            "format",
            "read_mode",
            "activates_document",
            "sheet_count",
            "returned_sheet_count",
            "sheets_truncated",
            "truncated",
        )
    }
    context["sheets"] = []
    context["guidance"] = (
        "This is a read-only saved-file snapshot; it does not open or select the live "
        "Calc workbook. Before editing, use os.desktop.open_path with the observed path, "
        "then workbook.inspect to verify the live document."
    )
    context["sheets_omitted"] = len(sheets)
    for source in sheets:
        display = source.get("display_text")
        rows = display if isinstance(display, list) else []
        preview = {
            key: source.get(key)
            for key in (
                "name",
                "used_range",
                "source_range",
                "returned_range",
                "source_rows",
                "source_columns",
                "returned_rows",
                "returned_columns",
                "truncated",
            )
        }
        preview["display_text"] = []
        preview["rows_omitted_from_context"] = len(rows)
        context["sheets"].append(preview)
        context["sheets_omitted"] = len(sheets) - len(context["sheets"])
        if len(json.dumps(context, ensure_ascii=False, default=str)) > 4200:
            context["sheets"].pop()
            context["sheets_omitted"] = len(sheets) - len(context["sheets"])
            break
        for row in rows:
            preview["display_text"].append(row)
            preview["rows_omitted_from_context"] = len(rows) - len(
                preview["display_text"]
            )
            if len(json.dumps(context, ensure_ascii=False, default=str)) > 4200:
                preview["display_text"].pop()
                preview["rows_omitted_from_context"] = len(rows) - len(
                    preview["display_text"]
                )
                break
    return context


def filesystem_find_context(result: dict[str, Any]) -> dict[str, Any]:
    raw_matches = result.get("matches")
    matches = [item for item in raw_matches or [] if isinstance(item, dict)]
    context: dict[str, Any] = {
        "match_count": result.get("match_count"),
        "returned_count": result.get("returned_count"),
        "truncated": result.get("truncated"),
        "matches": [],
        "matched_directories": [],
        "suggested_actions": [],
        "guidance": "",
    }
    if "kind" in result:
        context["kind"] = result["kind"]
    suffixes: set[str] = set()
    matched_directories: list[str] = []
    # Shallow user files are easier to act on than deeply nested cache entries
    # when a broad search returns more paths than the model context can hold.
    visible_matches = sorted(
        matches,
        key=lambda item: (
            sum(part.startswith(".") for part in str(item.get("path", "")).split("/")),
            str(item.get("path", "")).count("/"),
            str(item.get("path", "")).casefold(),
        ),
    )
    for item in visible_matches[:50]:
        path = str(item.get("path", ""))
        preview = {
            "path": path,
            "name": item.get("name"),
            "kind": item.get("kind"),
            "size_bytes": item.get("size_bytes"),
            "modified_at": item.get("modified_at"),
        }
        context["matches"].append(preview)
        parent = path if item.get("kind") == "directory" else path.rsplit("/", 1)[0]
        if parent and parent not in matched_directories:
            matched_directories.append(parent)
        if item.get("kind") == "file":
            suffixes.add(path.rsplit(".", 1)[-1].casefold() if "." in path else "")
        if len(json.dumps(context, ensure_ascii=False, default=str)) > 3900:
            context["matches"].pop()
            break
    context["matches_omitted"] = len(matches) - len(context["matches"])
    context["matched_directories"] = matched_directories
    has_modification_metadata = any(
        item.get("kind") == "file" and item.get("modified_at")
        for item in context["matches"]
    )
    suggested = []
    # File discovery only advertises the split public readers. The legacy
    # workbook.read_file route accepted a whole file path and competes with
    # the structured inspect/range.read contract after a workbook is open.
    # PDF files are handled by the same batch OCR route as other images.
    if suffixes.intersection({"csv", "ods", "xlsx"}):
        suggested.extend(["workbook.inspect", "range.read"])
    readable_documents_found = bool(
        suffixes.intersection({"doc", "docx", "odt", "rtf"})
    )
    if readable_documents_found:
        suggested.append("document.read_file")
    layered_images_found = bool(suffixes.intersection({"ora", "psd", "svg", "xcf"}))
    if layered_images_found:
        suggested.extend(["image.export", "image.insert_at_cursor"])
    if matches:
        suggested.append("desktop.open_path")
        if suffixes.intersection(
            {"bmp", "jpeg", "jpg", "pdf", "png", "tif", "tiff", "webp"}
        ):
            suggested.append("image.extract_text_batch")
        context["guidance"] = (
            (
                "For a DOC, DOCX, ODT, or RTF match, use the exact returned path with "
                "libreoffice_writer.document.read_file to read its saved body before opening "
                "it in the desktop. "
                if readable_documents_found
                else ""
            )
            + "Use an exact returned path with a content reader or desktop.open_path now. "
            "For a batch action that requires a containing directory, reuse an exact "
            "matched_directories value as its explicit directory. For "
            "people, objects, scenes, layout, or other visual appearance, open the image and "
            "inspect the next screenshot; image.extract_text_batch is OCR and only reads visible "
            "text, so it cannot classify visual subjects. "
            + (
                "To place a layered image into Writer, open the exact returned path, export "
                "the current image to a supported raster path with the owning GIMP Adapter, "
                "then insert that raster with Writer image.insert_at_cursor and save. "
                if layered_images_found
                else ""
            )
            + "Repeating filesystem.find with different globs does not reveal file contents."
            + (
                " For age or date-based organization, classify each returned file from its "
                "modified_at value; filesystem.find does not decide which files are old or recent."
                if has_modification_metadata
                else ""
            )
        )
    else:
        filter_guidance = {
            "file": (
                "This search used kind=file and excluded directories. To look for a "
                "directory, choose kind=directory or kind=any. "
            ),
            "directory": (
                "This search used kind=directory and excluded files. To look for a "
                "file, choose kind=file or kind=any. "
            ),
            "any": "This search used kind=any, including files and directories. ",
        }.get(result.get("kind"), "")
        context["guidance"] = (
            "No existing path matched. "
            + filter_guidance
            + "filesystem.find is read-only and cannot create a "
            "directory or prove that the desired input is absent. When locating an existing "
            "input, retry with a broader existing root, recursive=true, or different basename "
            "globs; do not repeat an equivalent zero-match search. Use "
            "filesystem.create_directory only when the instruction explicitly asks to create "
            "an output directory, then filesystem.rename with an exact source and destination."
        )
    context["suggested_actions"] = suggested
    return context


def desktop_open_path_context(result: dict[str, Any]) -> dict[str, Any]:
    path = str(result.get("path") or "")
    suffix = path.rsplit(".", 1)[-1].casefold() if "." in path else ""
    image_suffixes = {"bmp", "gif", "jpeg", "jpg", "png", "tif", "tiff", "webp"}
    document_suffixes = {"doc", "docx", "odt", "rtf"}
    if suffix in document_suffixes:
        guidance = (
            "The document was opened successfully. Read its saved body with "
            "libreoffice_writer.document.read_file using this exact path; do not repeat "
            "desktop.open_path."
        )
    elif suffix in image_suffixes:
        guidance = (
            "The opened image is visible in the next screenshot. Inspect that screenshot "
            "directly to identify or classify people, objects, scenes, or landmarks; OCR "
            "cannot infer visual subjects. Keep this exact source path. If the task requires "
            "a content-derived filename, use filesystem.rename with this source and a full "
            "destination path that preserves the appropriate file extension. Open and "
            "inspect each distinct image before naming it."
        )
    else:
        guidance = (
            "Inspect the next screenshot for visible content, or choose a structured reader "
            "when the file type has one."
        )
    return {
        "path": result.get("path"),
        "kind": result.get("kind"),
        "opened": result.get("opened"),
        "wait_seconds": result.get("wait_seconds"),
        "guidance": guidance,
    }


def text_file_context(result: dict[str, Any]) -> dict[str, Any]:
    content = str(result.get("content", ""))
    path = str(result.get("path", ""))
    raw_siblings = result.get("sibling_file_paths")
    sibling_paths = [
        sibling[:1000]
        for sibling in raw_siblings or []
        if isinstance(sibling, str) and sibling
    ][:16]
    sibling_file_count = result.get("sibling_file_count")
    if not isinstance(sibling_file_count, int) or isinstance(sibling_file_count, bool):
        sibling_file_count = len(raw_siblings) if isinstance(raw_siblings, list) else 0
    start = result.get("source_start_char", 0)
    return text_batch_context_for_model(
        {
            "reader_action": "file.read_text",
            "matched_count": 1,
            "files": [
                {
                    "path": path,
                    "status": "ok",
                    "text": content,
                    "returned_chars": len(content),
                    "source_start_char": start,
                    "source_end_char": result.get("source_end_char", start + len(content)),
                    "source_total_chars": result.get(
                        "source_total_chars", result.get("total_chars")
                    ),
                    "next_start_char": result.get("next_start_char"),
                    "offset_basis": "unicode_characters",
                    "source_truncated": result.get(
                        "source_truncated", result.get("truncated")
                    ),
                }
            ],
            "sibling_file_paths": sibling_paths,
            "sibling_file_count": sibling_file_count,
            "sibling_files_omitted_from_context": max(
                0, sibling_file_count - len(sibling_paths)
            ),
            "sibling_files_truncated": bool(result.get("sibling_files_truncated")),
        }
    )


def command_run_context(result: dict[str, Any]) -> dict[str, Any]:
    argv = result.get("argv")
    context: dict[str, Any] = {
        "argv": argv if isinstance(argv, list) else None,
        "returncode": result.get("returncode"),
        "stdout_path": result.get("stdout_path"),
        "stdout_bytes": result.get("stdout_bytes"),
        "output_saved": isinstance(result.get("stdout_path"), str),
        "terminal_launch": isinstance(result.get("terminal"), dict),
    }
    for key in ("stdout", "stderr"):
        output = result.get(key)
        if isinstance(output, str):
            context[key] = output[:MODEL_CONTEXT_MAX_STRING_CHARS]
            context[f"{key}_chars"] = len(output)
            context[f"{key}_context_truncated"] = len(output) > len(context[key])
    if context["output_saved"]:
        context["guidance"] = (
            "The command completed and its stdout was saved at stdout_path. Do not rerun the "
            "same command unless a distinct requested artifact is still missing."
        )
        return context

    if context["terminal_launch"]:
        context["guidance"] = (
            "Visible terminal launch was verified, but child completion and output were not "
            "captured or saved. If the requested end state needs a persistent output file, do "
            "not repeat terminal mode: call command.run with terminal omitted, keep the command "
            "in argv, and explicitly set stdout_path to the requested destination."
        )
    else:
        context["guidance"] = (
            "The command completed; inspect the returned stdout and stderr. This output was "
            "captured by the Adapter, not displayed in a desktop terminal, even if a terminal "
            "was already open. For visible command output, use terminal.show_output. Stdout was not "
            "saved to a file. Only if the requested end state requires a persisted stdout "
            "artifact, rerun once with stdout_path set to the requested destination."
        )
        if context.get("stdout_context_truncated"):
            context["guidance"] += (
                " Stdout is truncated in model context; narrow it with one complete "
                "model-authored bash -c script (for example a pipe to grep), or save it "
                "with stdout_path and read the saved file."
            )
        if (
            isinstance(argv, list)
            and len(argv) >= 2
            and argv[:2]
            == [
                "gsettings",
                "list-keys",
            ]
        ):
            context["guidance"] += (
                " If the needed key is absent, this schema is not the owner; use "
                "gsettings list-relocatable-schemas and a concrete SCHEMA:/instance/path/ "
                "before trying another key."
            )
    return context


def archive_context(result: dict[str, Any]) -> dict[str, Any]:
    raw_members = result.get("members")
    members = []
    for item in raw_members or []:
        if not isinstance(item, dict):
            continue
        members.append(
            {
                "name": str(item.get("name", ""))[:1000],
                "kind": item.get("kind"),
                "size_bytes": item.get("size_bytes"),
            }
        )
    context = {
        "mode": result.get("mode"),
        "archive_path": result.get("archive_path"),
        "archive_size_bytes": result.get("archive_size_bytes"),
        "destination_directory": result.get("destination_directory"),
        "member_count": result.get("member_count"),
        "members": members[:100],
        "members_omitted": max(0, len(members) - 100),
        "integrity_verified": result.get("integrity_verified"),
    }
    context["guidance"] = (
        "The ZIP was created from the selected inputs and its persisted members passed "
        "integrity checks. Compare members with the user's requested files; integrity "
        "does not confirm correct input selection. To replace an incorrectly assembled "
        "ZIP, call archive.create_zip with corrected input_paths and "
        "overwrite=true."
        if result.get("mode") == "create"
        else "The ZIP passed integrity and path-safety checks and its files were extracted; do not repeat extraction."
    )
    return context


def pdf_outline_context(result: dict[str, Any]) -> dict[str, Any] | None:
    raw_sections = result.get("sections")
    if not isinstance(raw_sections, list):
        return None
    sections = []
    for item in raw_sections:
        if not isinstance(item, dict) or not isinstance(item.get("title"), str):
            continue
        sections.append(
            {
                "index": item.get("index"),
                "title": str(item.get("title", ""))[:500],
                "start_page": item.get("start_page"),
                "end_page": item.get("end_page"),
                "page_count": item.get("page_count"),
            }
        )
    return {
        "input_path": result.get("input_path"),
        "source_page_count": result.get("source_page_count"),
        "source_sha256": result.get("source_sha256"),
        "outline_level": result.get("outline_level"),
        "prefix_page_count": result.get("prefix_page_count"),
        "section_count": result.get("section_count"),
        "offset": result.get("offset"),
        "returned_count": result.get("returned_count"),
        "truncated": result.get("truncated"),
        "next_offset": result.get("next_offset"),
        "sections": sections,
        "guidance": (
            "This read-only result covers only the selected PDF's internal outline and page "
            "ranges; it did not inspect sibling files, surrounding filenames, external "
            "templates, or directory naming examples. When the instruction makes an "
            "output_path depend on one of those live references, select a separate read-only "
            "inspection such as filesystem.find before choosing that output_path. Otherwise, "
            "select each explicit output_path and inclusive page range yourself when calling "
            "pdf.pages.extract. Request next_offset only when truncated is true."
        ),
        "context_char_budget": 8_000,
    }


def pdf_pages_extract_context(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_path": result.get("input_path"),
        "output_path": result.get("output_path"),
        "start_page": result.get("start_page"),
        "end_page": result.get("end_page"),
        "page_count": result.get("page_count"),
        "output_backend": result.get("output_backend"),
        "status": result.get("status"),
        "output_sha256": result.get("output_sha256"),
        "verification": result.get("verification"),
        "guidance": (
            "Exactly one model-named PDF was persisted and verified. Do not repeat this exact "
            "range and output path; create any other requested outputs with separate calls."
        ),
    }


def document_extract_images_context(
    result: dict[str, Any],
) -> dict[str, Any] | None:
    raw_images = result.get("images")
    if not isinstance(raw_images, list):
        return None
    images = []
    for item in raw_images[:64]:
        if not isinstance(item, dict) or not isinstance(item.get("output_path"), str):
            continue
        images.append(
            {
                key: item.get(key)
                for key in (
                    "index",
                    "output_path",
                    "media_type",
                    "size_bytes",
                    "sha256",
                )
            }
        )
    if not images:
        return None
    return {
        key: result.get(key)
        for key in (
            "source_path",
            "source_sha256",
            "document_format",
            "selection",
            "output_directory",
            "reference_count",
            "extracted_count",
        )
    } | {
        "images": images,
        "output_paths": [item["output_path"] for item in images],
        "images_omitted": max(0, len(raw_images) - len(images)),
        "guidance": (
            "Image extraction completed. Reuse an exact images[].output_path unchanged in "
            "the next image-consuming action; for desktop.set_wallpaper, pass that file as "
            "image_path. Do not substitute source_path, output_directory, ~/ or another "
            "directory for the extracted image file."
        ),
    }


def desktop_wallpaper_context(
    result: dict[str, Any], verification: Any
) -> dict[str, Any] | None:
    if not isinstance(result.get("image_path"), str):
        return None
    return {
        key: result.get(key)
        for key in (
            "image_path",
            "image_size_bytes",
            "image_format",
            "image_sha256",
            "wallpaper_uri",
            "settings",
            "verified",
        )
    } | {
        "verification_passed": verification.get("passed")
        if isinstance(verification, dict)
        else None,
        "guidance": (
            "The selected image file is now the GNOME desktop wallpaper and the persisted "
            "settings were read back. Treat verified and verification_passed as completion "
            "evidence; do not repeat the mutation."
        ),
    }


def workbook_inspect_context(result: dict[str, Any]) -> dict[str, Any] | None:
    raw_sheets = result.get("sheets")
    if not isinstance(raw_sheets, list):
        return None
    sheets = []
    for item in raw_sheets[:32]:
        if not isinstance(item, dict):
            continue
        raw_used_range = item.get("used_range")
        used_range = raw_used_range if isinstance(raw_used_range, dict) else {}
        coordinates = tuple(
            used_range.get(key)
            for key in ("start_column", "start_row", "end_column", "end_row")
        )
        used_range_a1 = None
        if all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in coordinates
        ):
            start_column, start_row, end_column, end_row = coordinates
            if (
                start_column >= 0
                and start_row >= 0
                and end_column >= start_column
                and end_row >= start_row
            ):
                used_range_a1 = (
                    f"{column_label(start_column + 1)}{start_row + 1}:"
                    f"{column_label(end_column + 1)}{end_row + 1}"
                )
        charts = item.get("charts")
        chart_summaries = [
            {
                key: chart[key]
                for key in (
                    "name",
                    "title",
                    "type",
                    "diagram_type",
                    "source_sheet",
                    "source_ranges",
                    "column_headers",
                    "row_headers",
                    "data_series_count",
                    "data_series",
                    "category_axes",
                    "data_series_inspect_error",
                    "inspect_error",
                )
                if key in chart
            }
            for chart in (
                charts[:MODEL_CONTEXT_MAX_LIST_ITEMS]
                if isinstance(charts, list)
                else []
            )
            if isinstance(chart, dict)
        ]
        for chart in chart_summaries:
            series = chart.get("data_series")
            if isinstance(series, list) and len(series) > MODEL_CONTEXT_MAX_LIST_ITEMS:
                chart["data_series"] = series[:MODEL_CONTEXT_MAX_LIST_ITEMS]
                chart["data_series_omitted_from_context"] = (
                    len(series) - MODEL_CONTEXT_MAX_LIST_ITEMS
                )
            axes = chart.get("category_axes")
            if isinstance(axes, list):
                chart["category_axes"] = [
                    {
                        **axis,
                        "labels": axis["labels"][:MODEL_CONTEXT_MAX_LIST_ITEMS],
                        "labels_omitted_from_context": len(axis["labels"])
                        - MODEL_CONTEXT_MAX_LIST_ITEMS,
                    }
                    if isinstance(axis, dict)
                    and isinstance(axis.get("labels"), list)
                    and len(axis["labels"]) > MODEL_CONTEXT_MAX_LIST_ITEMS
                    else axis
                    for axis in axes
                ]
        sheets.append(
            {
                "name": str(item.get("name", ""))[:512],
                "used_range_a1": used_range_a1,
                "used_range": {
                    **used_range,
                    "coordinate_system": "zero-based inclusive indices; use used_range_a1 for API ranges",
                },
                "hidden_rows": item.get("hidden_rows")
                if isinstance(item.get("hidden_rows"), list)
                else [],
                "chart_count": len(charts) if isinstance(charts, list) else None,
                "charts": chart_summaries,
                "charts_omitted_from_context": len(charts) - len(chart_summaries)
                if isinstance(charts, list)
                else 0,
            }
        )
        pivots = item.get("pivot_tables")
        if isinstance(pivots, list):
            summaries = [
                {
                    key: pivot[key]
                    for key in ("name", "output_range", "inspect_error")
                    if key in pivot
                }
                for pivot in pivots[:MODEL_CONTEXT_MAX_LIST_ITEMS]
                if isinstance(pivot, dict)
            ]
            sheets[-1].update(
                pivot_table_count=len(pivots),
                pivot_tables=summaries,
                pivot_tables_omitted_from_context=len(pivots) - len(summaries),
            )
        if item.get("pivot_tables_inspect_error"):
            sheets[-1]["pivot_tables_inspect_error"] = item["pivot_tables_inspect_error"]
            sheets[-1]["pivot_table_count"] = None
    context = {
        "title": result.get("title"),
        "url": result.get("url"),
        "active_sheet": result.get("active_sheet"),
        "modified": result.get("modified"),
        "sheet_count": len(raw_sheets),
        "sheets": sheets,
        "sheets_omitted_from_context": max(0, len(raw_sheets) - len(sheets)),
        "guidance": (
            "Reuse the exact observed URL, sheet name, and used_range_a1; do not guess a "
            "different workbook path or range. Numeric start_row/end_row and column indices "
            "are zero-based and inclusive: the last spreadsheet row is end_row + 1. "
            "Use the A1 endpoint when selecting all records, including the final row. "
            "range.read reads worksheet cells. Charts "
            "are embedded objects, not cell contents: read their observed settings in "
            "sheets[].charts. Empty cells do not imply that a sheet has no charts. "
            "data_series_count and data_series describe plotted value series; "
            "category_axes contains category labels, not additional value series. "
            "sheets[].pivot_tables lists native pivot names and occupied output_range "
            "rectangles. Different names share worksheet cells; overlapping rectangles "
            "can overwrite table output. range.read reads the cells in a selected "
            "output_range. "
            "workbook.inspect does not return cell values; before editing, read the "
            "relevant observed used_range_a1 so every target and formula comes from "
            "live cells."
        ),
    }
    while sheets and len(json.dumps(context, ensure_ascii=False, default=str)) > 4200:
        if sheets[-1]["charts"]:
            sheets[-1]["charts"].pop()
            sheets[-1]["charts_omitted_from_context"] += 1
            continue
        if sheets[-1].get("pivot_tables"):
            sheets[-1]["pivot_tables"].pop()
            sheets[-1]["pivot_tables_omitted_from_context"] += 1
            continue
        sheets.pop()
        context["sheets_omitted_from_context"] = len(raw_sheets) - len(sheets)
    return context


def adapter_context_hint(domain: str, action: str, body: Any) -> dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    result = body.get("result")
    if not isinstance(result, dict):
        return None
    if domain == "libreoffice_calc" and action == "pivot.create" and (
        isinstance(result.get("readback"), dict) or "readback_error" in result
    ):
        return {
            **result,
            "context_char_budget": 16_000,
            "guidance": (
                "The pivot was created. readback contains its actual displayed cells; "
                "compare them with the intended aggregation and percentage denominator. "
                "Use range.read for omitted cells when truncated or for readback_error; "
                "output_range remains the complete occupied rectangle."
            ),
        }
    if domain == "libreoffice_calc" and action == "range.format":
        areas = result.get("range_results")
        if isinstance(areas, list):
            bounded_readback_guidance = (
                " When an area has truncated=true, its display_text and styles cover "
                "only readback_range; the full range was formatted. date_cells_truncated "
                "and background_cells_truncated mean those maps do not cover all "
                "formatted cells. An address outside the returned readback ranges "
                "is unobserved, not known to be white or non-date. Use range.read "
                "on a smaller explicit area to inspect omitted cells."
                if result.get("truncated") is True else ""
            )
            return {
                "sheet": result.get("sheet"),
                "range": result.get("range"),
                "formatted_ranges": result.get("formatted_ranges"),
                "range_results": [
                    {
                        key: area[key]
                        for key in (
                            "range", "readback_range", "truncated", "display_text", "styles"
                        )
                        if key in area
                    }
                    for area in areas
                    if isinstance(area, dict)
                ],
                **{
                    key: result[key]
                    for key in ("date_cells", "background_cells")
                    if isinstance(result.get(key), dict)
                },
                **{
                    key: result[key]
                    for key in (
                        "truncated", "date_cells_truncated", "background_cells_truncated"
                    )
                    if key in result
                },
                "guidance": (
                    "Formatting succeeded for formatted_ranges. Each range_results entry "
                    "is a separate area, not part of a combined rectangle. date_cells and "
                    "background_cells are observations after formatting; check their exact "
                    "A1 addresses and dates against your intended selection. If context is "
                    "truncated, range.read can inspect a smaller explicit area."
                ) + bounded_readback_guidance,
            }
    if domain == "libreoffice_calc" and action == "range.read":
        cell_metadata = {
            key: result[key]
            for key in ("background_cells", "date_cells")
            if isinstance(result.get(key), dict)
        }
        matrices = {
            key: result.get(key)
            for key in ("display_text", "formulas", "kinds", "cell_addresses")
            if isinstance(result.get(key), list)
        }
        if "cell_addresses" not in matrices:
            addresses = range_cell_addresses(result.get("range"))
            if addresses is not None:
                matrices["cell_addresses"] = addresses
        range_geometry = (
            a1_geometry(result.get("range"))
            if isinstance(result.get("range"), str)
            else None
        )
        narrow_read_guidance = ""
        if range_geometry is not None and range_geometry[0] == range_geometry[2]:
            narrow_read_guidance = (
                " This observation covers one column only; when the instruction asks "
                "for missing rows, period columns, or totals, read the adjacent "
                "observed columns as one larger contiguous range before writing."
            )
        summary_rows = calc_summary_row_context(
            result.get("display_text"),
            result.get("kinds"),
            matrices.get("cell_addresses"),
        )
        summary_context = {"summary_rows": summary_rows} if summary_rows else {}
        balance_guidance = ""
        displayed = result.get("display_text")
        if isinstance(displayed, list) and any(
            isinstance(row, list)
            and any(str(cell).strip().casefold() == "balance" for cell in row)
            for row in displayed
        ):
            balance_guidance = (
                " The observed sheet has a Balance column. When appending ledger rows, "
                "the first new balance must be a formula adding the prior balance cell "
                "to the new Amount cell, and each later row must continue that formula "
                "down (for example =E8+D9, then =E9+D10); write formulas, not constants."
            )
        detail_total_cells = list(
            dict.fromkeys(
                cell
                for summary in summary_rows
                for cell in summary.get("detail_total_cells", [])
                if isinstance(cell, str)
            )
        )
        if detail_total_cells:
            summary_context["detail_total_cells"] = detail_total_cells
        return {
            "sheet": result.get("sheet"),
            "range": result.get("range"),
            **matrices,
            **cell_metadata,
            **summary_context,
            "context_char_budget": 64_000,
            "guidance": (
                "Adapter-observed cells for the exact A1 range. cell_addresses is a matrix "
                "aligned one-for-one with display_text, formulas, and kinds: use "
                "cell_addresses[i][j] as the exact A1 address for the value at row i, "
                "column j. If context_truncated=true, only leading rows may remain; "
                "each visible row still contains all its columns in range order. Read a "
                "smaller explicit range for missing rows. Derive every target cell and "
                "formula from observed values; do not guess omitted rows or write "
                "calculated constants when a formula is required."
                + (
                    " background_cells maps non-white backgrounds by A1 address; "
                    "unlisted cells are white only when that map is complete. "
                    "date_cells maps native dates and weekdays to their exact A1 addresses. "
                    "If any metadata is truncated, read a smaller range to check missing cells."
                    if cell_metadata
                    else ""
                )
                + narrow_read_guidance
                + balance_guidance
                + (
                    " summary_rows lists observed Total/Subtotal rows and their blank "
                    "cells and the contiguous detail_row_range feeding each summary; "
                    "when the instruction requests totals, treat those observed "
                    "blank cells as targets and select formulas for each one. "
                    "detail_total_cells lists blank trailing Total cells on detail rows; "
                    "for each such detail row r, use a horizontal formula "
                    "=SUM(first_period_r:last_period_r). When both summary_rows and "
                    "detail_total_cells are present, the same mutation must cover the "
                    "union of both target sets. Each summary entry's period_cells are "
                    "the vertical-SUM targets and final_total_cell is the horizontal-SUM "
                    "target. For a "
                    "summary row r over detail rows s:e, use a vertical column formula "
                    "=SUM(c_s:c_e) for each period c, then a horizontal "
                    "=SUM(first_period_r:last_period_r) in its final Total cell; do not "
                    "reuse a detail-row formula in the summary."
                    if summary_rows
                    else ""
                )
            ),
        }
    if domain == "libreoffice_calc" and action == "cells.set_formulas":
        verification = body.get("verification")
        return {
            "sheet": result.get("sheet"),
            "written_cells": result.get("written_cells"),
            "cells": result.get("cells"),
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
        }
    if domain == "libreoffice_calc" and action == "chart.create":
        verification = body.get("verification")
        return {
            key: result.get(key)
            for key in (
                "name",
                "type",
                "title",
                "sheet",
                "source_sheet",
                "source_ranges",
                "data_row_source",
                "column_headers",
                "row_headers",
                "header_inspect_error",
                "data_series_count",
                "data_series",
                "category_axes",
                "data_series_inspect_error",
            )
            if key in result
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
            "guidance": (
                "Creation and verification confirm that the supplied arguments ran, "
                "not that the selected data matches the user's request. data_series "
                "and data_series_count are the plotted numeric value series; "
                "category_axes contains the category labels and is not an additional "
                "value series. The returned native header flags show the active "
                "binding: column_headers consumes the first selected row as labels; "
                "row_headers consumes the first selected column as labels. Header "
                "cells are excluded from numeric value series. If a requested data "
                "boundary became a header, correct that flag and explicitly replace "
                "the chart. Compare the observed series and categories with the "
                "requested chart. Check each chart's actual first and last category "
                "labels and any blank labels against its source table. A matching "
                "category count can still hide a missing item and an extra summary "
                "row. If they differ, read the source cells and correct "
                "your source ranges or header flags. Otherwise keep the chart, save "
                "the workbook, and use workbook.inspect before propose_done. Do not "
                "recreate solely because categories are separate from value series."
            ),
        }
    if domain == "multi_apps":
        downstream_domain = result.get("adapter")
        downstream_action = result.get("action")
        downstream = result.get("response")
        if not (
            isinstance(downstream_domain, str)
            and isinstance(downstream_action, str)
            and isinstance(downstream, dict)
        ):
            return None
        verification = downstream.get("verification")
        downstream_context = adapter_context_hint(
            downstream_domain, downstream_action, downstream
        )
        if downstream_context is None and isinstance(downstream.get("result"), dict):
            downstream_context = compact_context_hint_for_model(
                downstream["result"],
                remaining_chars=MODEL_CONTEXT_HINT_DEFAULT_MAX_CHARS,
            )
        return {
            "downstream_adapter": downstream_domain,
            "downstream_action": downstream_action,
            "downstream_status": downstream.get("status"),
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
            "downstream_context": downstream_context,
        }
    if domain == "vlc" and action == "playback.find_local":
        return filesystem_find_context(result) if isinstance(result.get("matches"), list) else None
    if domain == "vlc" and action == "media.extract_audio":
        probe = result.get("probe")
        streams = probe.get("streams") if isinstance(probe, dict) else None
        return {
            key: result.get(key)
            for key in ("input_path", "output_path", "strategy", "output_sha256")
        } | {
            "audio_stream_count": len(
                [
                    stream
                    for stream in streams
                    if isinstance(stream, dict) and stream.get("codec_type") == "audio"
                ]
            )
            if isinstance(streams, list)
            else None,
            "guidance": (
                "Audio extraction completed. If the task only requested this output file, "
                "propose completion now. Only when the instruction explicitly requires a "
                "follow-up action, reuse output_path unchanged."
            ),
        }
    if domain == "os" and action == "pdf.tables.inspect":
        context = {key: value for key, value in result.items() if key != "bbox"}
        context["context_char_budget"] = 12_000
        context["observation_type"] = "pdf_table"
        context["merged_cells"] = [
            [cell[key] for key in ("row", "column", "row_span", "column_span")]
            for cell in result.get("merged_cells", [])
        ]
        context["guidance"] = (
            "rows[i][j] is table row row_offset+i, column j (zero-based). "
            "merged_cells entries are [row, column, row_span, column_span] in the full table; "
            "covered positions remain null. Empty strings are empty cells; newlines stay inside "
            "one cell and are not separate table rows. Read all header levels to identify columns. "
            "If context_truncated=true, only leading complete rows may be visible: repeat the "
            "same row_offset with smaller max_rows before using next_row_offset. Otherwise "
            "next_row_offset continues the source window when truncated=true."
        )
        return context
    if domain == "os" and action == "pdf.extract_text_batch":
        if not isinstance(result.get("files"), list):
            return None
        return pdf_text_batch_context(result)
    if domain == "os" and action in {"pdf.form.inspect", "pdf.form.fill"}:
        context = dict(result)
        context["context_char_budget"] = 24_000
        if action == "pdf.form.inspect" and isinstance(result.get("fields"), list):
            context["fields"] = [
                {
                    key: value
                    for key, value in field.items()
                    if not (
                        (key == "field_type" and value == "/Tx")
                        or (key == "writable" and value is True)
                        or (key == "value" and value is None)
                        or (
                            key == "label"
                            and value in ("", field.get("field_name"))
                        )
                    )
                }
                if isinstance(field, dict)
                else field
                for field in result["fields"]
            ]
        context["guidance"] = (
            "In compact field records, omitted field_type means /Tx, omitted writable "
            "means true, and omitted value means null. Empty labels and labels identical "
            "to field_name are omitted. "
            "These are the PDF's real form fields. Copy exact field_name values into "
            "pdf.form.fill, assigning each value from the requested source. Omitted "
            "fields stay unchanged: already blank fields need no empty-string entry. Only "
            "writable /Tx fields accept text. If context_truncated=true, some returned "
            "fields are hidden: repeat the current field_offset with a smaller "
            "max_fields (for example 8); do not jump to next_offset yet. Otherwise, "
            "use next_offset as field_offset when truncated=true."
            if action == "pdf.form.inspect"
            else "This one output PDF was saved and the selected field values were read back. "
            "Check field_values against your intended data. Continue any remaining "
            "requested documents separately; this call did not create other outputs."
        )
        return context
    if domain == "os" and action == "pdf.outline.inspect":
        context = pdf_outline_context(result)
        if context is None:
            return None
        verification = body.get("verification")
        if isinstance(verification, dict):
            context["verification_passed"] = verification.get("passed")
        return context
    if domain == "os" and action == "pdf.pages.extract":
        context = pdf_pages_extract_context(result)
        verification = body.get("verification")
        if isinstance(verification, dict):
            context["verification_passed"] = verification.get("passed")
        return context
    if domain == "os" and action == "image.extract_text_batch":
        if not isinstance(result.get("files"), list):
            return None
        return pdf_text_batch_context(result)
    if domain == "os" and action == "document.convert":
        verification = body.get("verification")
        return {
            key: result.get(key)
            for key in (
                "source",
                "destination",
                "output_format",
                "size_bytes",
                "replaced",
                "isolated_profile",
            )
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
            "guidance": (
                "One explicit document was converted and the destination is available. "
                "Continue with any remaining observed source files, or reuse destination "
                "unchanged for the next requested operation."
            ),
        }
    if domain == "os" and action in {"archive.create_zip", "archive.extract_zip"}:
        context = archive_context(result)
        verification = body.get("verification")
        context["verification_passed"] = (
            verification.get("passed") if isinstance(verification, dict) else None
        )
        return context
    if domain == "os" and action == "filesystem.find":
        if not isinstance(result.get("matches"), list):
            return None
        return filesystem_find_context(result)
    if domain == "os" and action == "trash.list":
        entries = result.get("entries")
        if not isinstance(entries, list):
            return None
        return {
            key: result.get(key)
            for key in (
                "entries",
                "entry_count",
                "offset",
                "max_results",
                "returned_count",
                "truncated",
                "next_offset",
            )
        } | {
            "guidance": (
                "Select one exact trash_uri/original_path pair from this read-only result "
                "before calling trash.restore."
            )
        }
    if domain == "os" and action == "trash.restore":
        verification = body.get("verification")
        return {
            key: result.get(key)
            for key in ("trash_uri", "original_path", "already_restored")
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None
        }
    if domain == "os" and action == "filesystem.copy":
        return {
            "source": result.get("source"),
            "destination": result.get("destination"),
            "size_bytes": result.get("size_bytes"),
            "guidance": "One explicit file copy completed; continue with any remaining observed files.",
        }
    if domain == "os" and action == "filesystem.rename":
        return filesystem_rename_context(result, body.get("verification"))
    if domain == "os" and action == "filesystem.set_permissions":
        verification = body.get("verification")
        return {
            key: result.get(key) for key in ("path", "mode", "mode_value", "changed")
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
            "guidance": (
                "The permission mode was read back for this one explicit regular file. "
                "Continue with each remaining file returned by filesystem.find."
            ),
        }
    if domain == "os" and action == "filesystem.create_directory":
        return {
            "path": result.get("path"),
            "created": result.get("created"),
            "directory_ready": bool(result.get("path")),
            "guidance": "The directory is ready; continue with the requested file operation.",
        }
    if domain == "os" and action == "archive.compress_file":
        return {
            "source": result.get("source"),
            "destination": result.get("destination"),
            "remove_source": result.get("remove_source"),
            "source_exists": result.get("source_exists"),
            "guidance": "One explicit file was compressed; continue with any remaining observed files.",
        }
    if domain == "os" and action == "command.run":
        return command_run_context(result)
    if domain == "os" and action == "desktop.open_path":
        return desktop_open_path_context(result)
    if domain == "os" and action == "desktop.set_wallpaper":
        return desktop_wallpaper_context(result, body.get("verification"))
    if domain == "os" and action == "desktop.favorites.list":
        favorites = result.get("favorites")
        if not isinstance(favorites, list):
            return None
        return {
            key: result.get(key)
            for key in (
                "favorites",
                "favorite_count",
                "offset",
                "max_results",
                "returned_count",
                "truncated",
                "next_offset",
            )
        } | {
            "guidance": (
                "Select one exact desktop_id from this read-only result before calling "
                "desktop.remove_favorite."
            )
        }
    if domain == "os" and action == "desktop.remove_favorite":
        verification = body.get("verification")
        return {
            "removed": result.get("removed"),
            "before": result.get("before"),
            "after": result.get("after"),
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
        }
    if domain == "os" and action == "desktop.applications.inspect":
        applications = result.get("applications")
        if not isinstance(applications, list):
            return None
        return {
            "query": result.get("query"),
            "mime_type_prefixes": result.get("mime_type_prefixes"),
            "match_count": result.get("match_count"),
            "truncated": result.get("truncated"),
            "max_results": result.get("max_results"),
            "mime_offset": result.get("mime_offset"),
            "max_mime_types_per_application": result.get(
                "max_mime_types_per_application"
            ),
            "applications": applications,
            "guidance": (
                "Choose an exact desktop_id and a bounded batch of exact advertised "
                "mime_types from this read-only result before calling "
                "desktop.mime_associations.set. When an application reports a non-null "
                "next_mime_offset, inspect that next page explicitly before deciding "
                "whether the requested category is complete."
            ),
        }
    if domain == "os" and action == "desktop.mime_associations.set":
        mime_types = result.get("mime_types")
        observed = result.get("observed")
        desktop_id = result.get("desktop_id")
        before = result.get("before")
        if not isinstance(mime_types, list) or not isinstance(observed, dict):
            return None
        verification = body.get("verification")
        return {
            "application": result.get("application"),
            "desktop_id": desktop_id,
            "mime_type_count": len(mime_types),
            "mime_types": mime_types,
            "changed_count": (
                sum(value != desktop_id for value in before.values())
                if isinstance(before, dict)
                else None
            ),
            "all_associations_match": bool(observed)
            and set(observed) == set(mime_types)
            and set(observed.values()) == {desktop_id},
            "verification_passed": (
                verification.get("passed") if isinstance(verification, dict) else None
            ),
        }
    if domain == "vs_code" and action == "extension.install":
        return {key: result[key] for key in (
            "extension_id", "source_type", "already_installed", "changed", "guidance",
        ) if key in result}
    if domain == "vs_code" and action == "debug.variables.read":
        variables = result.get("variables")
        if not isinstance(variables, dict) or not isinstance(
            variables.get("item_names"), list
        ):
            return None
        session = variables.get("session")
        return {
            key: variables.get(key)
            for key in (
                "window_id",
                "window_title",
                "item_names",
                "item_count",
                "truncated",
            )
        } | {
            "session": (
                {key: session.get(key) for key in ("phase", "active", "paused")}
                if isinstance(session, dict)
                else None
            ),
            "guidance": (
                "These are currently visible VARIABLES items, not every variable "
                "declared in the source. Reading or raising max_items does not "
                "expand a scope or execute code. A breakpoint pauses before its "
                "line executes; later assignments have not run yet. Inspect the "
                "current source and choose a separate execution/GUI step when "
                "needed; repeated reads without a state change show the same items."
            ),
        }
    if domain == "vs_code" and action == "workspace.inspect":
        roots = result.get("workspace_roots")
        if not isinstance(roots, list) or not all(
            isinstance(root, str) for root in roots
        ):
            return None
        return {
            key: result.get(key)
            for key in (
                "window_id",
                "window_title",
                "window_classes",
                "workspace_name",
                "workspace_roots",
                "workspace_file",
                "resolution_source",
            )
        } | {
            "guidance": (
                "This is a read-only observation of the active workspace. Reuse exact "
                "workspace_roots as explicit workspace.write folders only when the "
                "instruction requires saving a workspace. When workspace_file is present, "
                "reuse that exact path with workspace.add_folders to update the saved "
                "workspace; do not assume this inspection wrote anything."
            )
        }
    if domain == "libreoffice_writer" and action == "document.create":
        return {key: result.get(key) for key in (
            "created", "blank", "activates_document", "identity", "path", "exists", "valid",
        )} | {"guidance": (
            "This is a new empty saved document, now active. Reuse its returned identity "
            "for separate text/table edits. Creating it alone does not copy source content."
        )}
    if domain == "libreoffice_writer" and action in {"document.export_pdf", "document.export_file_pdf"}:
        return {
            key: result[key]
            for key in (
                "source_path", "source_url", "path", "exists", "valid", "size", "pdf_header",
                "export_mode", "activates_document", "soft_wrap_space_preservation",
                "output_path", "output_bytes", "output_sha256",
            )
            if key in result
        }
    if domain == "libreoffice_writer" and action == "document.read_file":
        if not isinstance(result.get("text"), str):
            return None
        return {
            "observation_type": "text_batch", "reader_action": action,
            "read_mode": "saved_file_snapshot", "activates_document": False,
            "guidance": (
                "This read does not activate the document. For PDF export of a saved "
                "file, use document.export_file_pdf with its observed source_path and "
                "a separate output_path. Before editing the open document or exporting "
                "unsaved changes, use os.desktop.open_path with the observed path, then "
                "document.inspect to verify the active source."
            ),
            "matched_count": 1, "files": [result],
        }
    if domain == "vs_code" and action == "file.read_text":
        if not isinstance(result.get("content"), str):
            return None
        return text_file_context(result)
    if domain == "vs_code" and action == "workspace.find_files":
        if not isinstance(result.get("matches"), list):
            return None
        context = filesystem_find_context(result)
        context.update(
            {
                key: result.get(key)
                for key in (
                    "workspace_name",
                    "workspace_roots",
                    "resolution_source",
                )
            }
        )
        context["guidance"] = (
            "Use the exact returned paths in the next consuming action; do not infer, "
            "shorten, or change their directories. For a batch operation, pass every "
            "relevant returned file exactly once and explicitly choose its order."
        )
        return context
    if domain == "vs_code":
        context = workspace_mutation_context(action, result, body.get("verification"))
        if context is not None:
            return context
    if domain == "thunderbird" and action == "messages.query":
        if not isinstance(result.get("messages"), list):
            return None
        return thunderbird_message_query_context(result)
    if domain == "thunderbird" and action == "attachments.save":
        return {
            key: result.get(key)
            for key in (
                "folder",
                "mailbox_index",
                "message_id",
                "subject",
                "attachment_index",
                "attachment_name",
                "content_type",
                "output_path",
                "size_bytes",
                "sha256",
                "overwritten",
            )
        } | {
            "saved": bool(
                result.get("output_path") and result.get("size_bytes") is not None
            ),
            "guidance": (
                "The selected mailbox attachment was written atomically and verified by size and SHA-256. "
                "Continue with content extraction or the remaining requested application update."
            ),
        }
    if domain == "thunderbird" and action == "compose.set_recipients":
        return {
            key: result.get(key)
            for key in (
                "compose_title",
                "mode",
                "recipients_before",
                "requested_recipients",
                "added_recipients",
                "observed_recipients",
                "verified",
                "compose_open",
            )
        }
    if domain == "libreoffice_calc" and action == "workbook.create_new":
        return {
            key: result.get(key)
            for key in (
                "path",
                "url",
                "format",
                "sheet",
                "sheet_names",
                "data_range",
                "header_count",
                "row_count",
                "written_cells",
                "table_state",
                "saved",
            )
        } | {
            "guidance": (
                "The header row was saved. Continue with a model-selected range.write "
                "for the data rows, then call workbook.save."
                if result.get("table_state") == "header_only"
                else "The workbook was created and saved with the selected table state."
            )
        }
    if domain == "libreoffice_calc" and action == "workbook.inspect":
        return workbook_inspect_context(result)
    if domain == "libreoffice_calc" and action == "workbook.read_file":
        if not isinstance(result.get("sheets"), list):
            return None
        return spreadsheet_file_context(result)
    if domain == "libreoffice_calc" and action == "table.reorder_columns":
        return column_reorder_context(result)
    if domain == "libreoffice_writer" and action == "document.extract_images":
        return document_extract_images_context(result)
    if domain == "libreoffice_writer" and action == "document.remove_highlighting":
        before = result.get("highlighting_before")
        after = result.get("highlighting_after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            return None
        verification = body.get("verification")
        return {
            "highlighting_before": before,
            "highlighting_after": after,
            "paragraphs_changed": result.get("paragraphs_changed"),
            "saved": result.get("saved"),
            "adapter_verified": result.get("verified") is True,
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
            "guidance": (
                "highlighting_after.highlighted_run_count equal to zero is verified mutation "
                "evidence. Do not repeat document.remove_highlighting or use GUI. Perform one "
                "document.inspect structural read-back, then call propose_done when the saved "
                "file is valid and the read-back still reports zero highlighted runs."
            ),
        }
    if domain == "libreoffice_writer" and action == "image.insert_at_cursor":
        verification = body.get("verification")
        return {
            key: result.get(key)
            for key in (
                "path",
                "anchor",
                "inserted",
                "graphic_object_count_before",
                "graphic_object_count_after",
                "graphic_objects_added",
                "count_verified",
                "saved",
            )
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
            "guidance": (
                "A successful call inserts one additional graphic object at the current "
                "Writer cursor and persists the document. The before/after counts and "
                "graphic_objects_added are structural mutation evidence. Repeating this "
                "action inserts another copy, so repeat it only when the instruction "
                "explicitly requests another copy. When the requested insertion count is "
                "satisfied and the saved file is valid, call propose_done; document.inspect "
                "can be used once for structural read-back."
            ),
        }
    if domain == "libreoffice_writer" and action == "text.find":
        matches = result.get("matches")
        return {
            "scope": result.get("scope"),
            "literal": result.get("literal"),
            "case_sensitive": result.get("case_sensitive"),
            **({"format": result["format"]} if "format" in result else {}),
            **{
                key: result[key]
                for key in ("format_counts", "format_counts_scope")
                if key in result
            },
            "max_results": result.get("max_results"),
            "returned_count": result.get("returned_count"),
            "has_more": result.get("has_more"),
            "matches": matches if isinstance(matches, list) else [],
        }
    if domain == "libreoffice_writer" and action in {
        "paragraph.apply_numbering",
        "bookmark.create",
        "cross_reference.insert",
    }:
        verification = body.get("verification")
        return {
            key: result.get(key)
            for key in (
                "source_index",
                "target_index",
                "source_list_label",
                "numbering_type",
                "style_name",
                "level",
                "restart",
                "start_value",
                "list_label",
                "is_numbered",
                "name",
                "paragraph_index",
                "start_offset",
                "end_offset",
                "anchor_text",
                "bookmark_name",
                "display",
                "presentation",
                "field_service",
                "saved",
            )
            if key in result
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
        }
    if domain == "libreoffice_writer" and action == "document.inspect":
        if not isinstance(result.get("paragraphs"), list):
            return None
        context: dict[str, Any] = {}
        identity = result.get("identity")
        if isinstance(identity, dict):
            context["identity"] = {key: identity.get(key) for key in ("title", "url")}
        if isinstance(result.get("page_layouts"), list):
            context["page_layouts"] = result["page_layouts"]
            context["page_layout_guidance"] = (
                "Native page dimensions and margins in mm. body_width_mm is page width "
                "minus left/right page margins, before paragraph indents or text columns. "
                "Use the observed layout when choosing positions instead of guessing a width."
            )
        if isinstance(result.get("footers"), list):
            context["footers"] = result["footers"]
        if isinstance(result.get("fonts"), dict):
            context["fonts"] = result["fonts"]
        highlighting = result.get("highlighting")
        if isinstance(highlighting, dict):
            context["highlighting"] = {
                key: highlighting.get(key)
                for key in (
                    "highlighted_run_count",
                    "highlighted_paragraph_count",
                    "colors",
                )
            }
            context["highlighting_guidance"] = (
                "Use highlighting.highlighted_run_count as the structural read-back. Zero "
                "means no highlighted text run remains; after a successful relevant mutation "
                "and valid save evidence, call propose_done instead of repeating tools or GUI."
            )
        if "graphic_object_count" in result or "embedded_images" in result:
            context["images"] = {
                "graphic_object_count": result.get("graphic_object_count"),
                "embedded_media_count": result.get("embedded_images"),
            }
            context["image_readback_guidance"] = (
                "graphic_object_count is the number of image placements in the Writer "
                "document; embedded_media_count may be lower when placements reuse media. "
                "After a successful image insertion and valid save, use this structural "
                "read-back and call propose_done instead of inserting another copy."
            )
        tables = result.get("tables")
        if isinstance(tables, list):
            context["tables"] = [
                {
                    key: table.get(key)
                    for key in ("name", "rows", "columns")
                    if key in table
                }
                for table in tables
                if isinstance(table, dict)
            ]
            context["table_guidance"] = (
                "Use only table names listed in tables. If tables is empty, the document "
                "has no tables: do not guess table_1 or another name; use paragraph/text "
                "actions instead."
            )
        context.update(writer_paragraph_context(result))
        return context
    if domain == "libreoffice_writer" and action in {
        "table.insert_after_text",
        "table.convert_text",
    }:
        verification = body.get("verification")
        return {
            key: result.get(key)
            for key in (
                "name",
                "rows",
                "columns",
                "anchor_text",
                "anchor_paragraph_number",
                "match_mode",
                "case_sensitive",
                "display_text",
                "changed",
                "duplicate",
                "source_selection",
                "start_index",
                "end_index",
                "delimiter",
                "source_text_char_count",
                "text_preserved",
                "saved",
            )
            if key in result
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None
        }
    if domain == "libreoffice_writer" and action == "text.set_format":
        verification = body.get("verification")
        return {
            key: result[key]
            for key in (
                "paragraph_index",
                "start_offset",
                "end_offset",
                "text",
                "format",
                "text_unchanged",
                "saved",
            )
            if key in result
        } | {
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None
        }
    if domain == "libreoffice_writer" and action in {
        "paragraph.set_format",
    }:
        verification = body.get("verification")
        paragraph_context = writer_paragraph_context(result)
        tab_observation = result.get("tab_stop_observation")
        return {
            **{
                key: tab_observation[key]
                for key in (
                    "selected_paragraph_count",
                    "paragraphs_with_tabs_count",
                    "paragraphs_without_tabs_count",
                    "guidance",
                )
                if isinstance(tab_observation, dict) and key in tab_observation
            },
            "formatted_paragraphs": paragraph_context.get("paragraph_details", []),
            "groups": result.get("groups"),
            "formats": result.get("formats"),
            "verification_passed": verification.get("passed")
            if isinstance(verification, dict)
            else None,
        }
    if domain == "libreoffice_writer" and action == "table.read":
        cell_fields = ["name", "text", "font_color", "row_index", "column_index"]
        return {
            "name": result.get("name"),
            "rows": result.get("rows"),
            "columns": result.get("columns"),
            "cell_fields": cell_fields,
            "cells": [
                [cell.get(field) for field in cell_fields]
                for cell in result.get("cells", [])
            ],
            "context_char_budget": 8_000,
            "guidance": (
                "Each cells entry lists values in cell_fields order: "
                "[name, text, font_color, row_index, column_index]. "
                "These are observed text and font_color, not requested colors. "
                "font_color is #RRGGBB, automatic, mixed, or null (unavailable); "
                "null is not evidence of a specific color. row_index increases "
                "top-to-bottom and column_index left-to-right (A1 is column 1, row 1; "
                "A2 is column 1, row 2). For a rule about what a word starts with, "
                "compare only the first character of its observed text. Select explicit "
                "cell names yourself; the "
                "Adapter does not classify or expand them."
            ),
        }
    if domain == "libreoffice_writer" and action == "paragraph.split":
        return {
            key: result[key]
            for key in (
                "paragraph_index",
                "right_paragraph_index",
                "split_offset",
                "boundaries",
                "after_text",
                "blank_paragraphs_between",
                "text_unchanged",
                "paragraphs",
            )
            if key in result
        }
    if domain == "libreoffice_writer" and action == "paragraph.clear_text":
        verification = body.get("verification") or {}
        return {
            key: result[key]
            for key in (
                "indices", "paragraph_count_before", "paragraph_count_after",
                "paragraph_details", "saved",
            )
            if key in result
        } | {"verification_passed": verification.get("passed")}
    if domain == "libreoffice_writer" and action in {
        "table.set_cell_text_color",
        "paragraph.replace_text",
        "text.find_replace",
        "document.append_paragraphs",
    }:
        return {
            key: result.get(key)
            for key in (
                "name",
                "cells",
                "color",
                "paragraph_index",
                "paragraphs",
                "replacement_count",
                "appended_count",
                "blank_paragraphs_before",
                "blank_paragraphs_between",
                "find",
                "replacement",
                "replace_all",
                "case_sensitive",
            )
            if key in result
        }
    if domain == "libreoffice_impress" and action == "shape.format_text":
        verification = body.get("verification") or {}
        return {
            "paragraphs": result.get("paragraphs"),
            "properties": result.get("properties"),
            "alignment": result.get("alignment"),
            "verification_passed": verification.get("passed"),
        }
    if domain == "libreoffice_impress" and action == "presentation.set_page_size":
        after = result.get("after")
        if not isinstance(after, dict):
            return None
        verification = body.get("verification") or {}
        return {
            "unit": result.get("unit"),
            "slides": after.get("slides"),
            "masters": after.get("masters"),
            "verification_passed": verification.get("passed"),
        }
    if domain == "libreoffice_impress" and action == "presentation.inspect":
        slides = result.get("slides")
        if not isinstance(slides, list):
            return None
        raw_identity = result.get("identity")
        identity = raw_identity if isinstance(raw_identity, dict) else {}
        return {
            "identity": {
                "url": identity.get("url"),
                "title": identity.get("title"),
            },
            "url": identity.get("url"),
            "title": identity.get("title"),
            "slide_count": result.get("slide_count"),
            **(
                {"inspected_slides": result["inspected_slides"]}
                if "inspected_slides" in result
                else {}
            ),
            "slides": [
                {
                    "slide": slide.get("index"),
                    "width": slide.get("width"),
                    "height": slide.get("height"),
                    "orientation": slide.get("orientation"),
                    "background": slide.get("background"),
                    **(
                        {"notes": slide["notes"]}
                        if isinstance(slide.get("notes"), str)
                        else {}
                    ),
                    "shape_count": len(slide.get("shapes", [])),
                    "all_shapes": [
                        {
                            key: shape.get(key)
                            for key in (
                                "index",
                                "path",
                                "name",
                                "kind",
                                "is_text",
                                "fill_style",
                                "text_style",
                                "x",
                                "y",
                                "width",
                                "height",
                            )
                        }
                        for shape in slide.get("shapes", [])
                        if isinstance(shape, dict)
                    ],
                    "graphic_shapes": [
                        {
                            key: shape.get(key)
                            for key in (
                                "index",
                                "path",
                                "name",
                                "kind",
                                "graphic_url",
                                "x",
                                "y",
                                "width",
                                "height",
                                "visible",
                            )
                        }
                        for shape in slide.get("shapes", [])
                        if isinstance(shape, dict)
                        and "graphicobjectshape"
                        in str(shape.get("kind", "")).casefold()
                    ],
                    "picture_containers": picture_container_summaries(
                        slide.get("shapes")
                    ),
                    "media_shapes": [
                        {
                            key: shape.get(key)
                            for key in (
                                "index",
                                "path",
                                "name",
                                "kind",
                                "media_url",
                                "x",
                                "y",
                                "width",
                                "height",
                                "visible",
                            )
                        }
                        for shape in slide.get("shapes", [])
                        if isinstance(shape, dict)
                        and (
                            "mediashape" in str(shape.get("kind", "")).casefold()
                            or bool(shape.get("media_url"))
                        )
                    ],
                    "table_shapes": [
                        {
                            key: shape.get(key)
                            for key in (
                                "index",
                                "path",
                                "name",
                                "kind",
                                "x",
                                "y",
                                "width",
                                "height",
                            )
                        }
                        | {
                            "rows": shape["table"].get("rows"),
                            "columns": shape["table"].get("columns"),
                            "cells": shape["table"].get("cells"),
                        }
                        for shape in slide.get("shapes", [])
                        if isinstance(shape, dict)
                        and "tableshape" in str(shape.get("kind", "")).casefold()
                        and isinstance(shape.get("table"), dict)
                    ],
                    "text_shapes": [
                        {
                            "index": shape.get("index"),
                            "path": shape.get("path"),
                            "name": shape.get("name"),
                            "kind": shape.get("kind"),
                            **{
                                key: shape[key]
                                for key in ("x", "y", "width", "height")
                                if shape.get(key) is not None
                            },
                            **(
                                {"text_style": shape["text_style"]}
                                if isinstance(shape.get("text_style"), dict)
                                else {}
                            ),
                            "lines": [
                                str(line)[:240]
                                for line in str(shape.get("text", "")).splitlines()
                            ],
                            **(
                                {
                                    "paragraphs": [
                                        {
                                            key: paragraph.get(key)
                                            for key in (
                                                "index",
                                                "text",
                                                "bullet",
                                                "level",
                                                "left_margin",
                                                "first_line_indent",
                                            )
                                        }
                                        for paragraph in shape["paragraphs"]
                                        if isinstance(paragraph, dict)
                                    ]
                                }
                                if isinstance(shape.get("paragraphs"), list)
                                else {}
                            ),
                        }
                        for shape in flattened_shape_summaries(slide.get("shapes"))
                        if isinstance(shape, dict)
                        and (
                            bool(str(shape.get("text", "")).strip())
                            or (
                                shape.get("is_text") is True
                                and "com.sun.star.presentation."
                                in str(shape.get("kind", ""))
                            )
                        )
                    ],
                    "recursive_text_shapes": [
                        {
                            "index": shape.get("index"),
                            "path": shape.get("path"),
                            "name": shape.get("name"),
                            "kind": shape.get("kind"),
                            **{
                                key: shape[key]
                                for key in ("x", "y", "width", "height")
                                if shape.get(key) is not None
                            },
                            **(
                                {"text_style": shape["text_style"]}
                                if isinstance(shape.get("text_style"), dict)
                                else {}
                            ),
                            "lines": [
                                str(line)[:240]
                                for line in str(shape.get("text", "")).splitlines()
                            ],
                        }
                        for shape in flattened_shape_summaries(slide.get("shapes"))
                        if bool(str(shape.get("text", "")).strip())
                    ],
                }
                for slide in slides
                if isinstance(slide, dict)
            ],
            "guidance": (
                "Reuse the exact observed presentation URL when another action needs the "
                "source path; do not guess a filename or extension. Text and table selectors "
                "must be copied exactly from this inspection. If text_shapes_omitted is "
                "greater than zero, do not construct a selector from instruction text; "
                "request a fresh observation that exposes the needed index, path, or name."
            ),
        }
    if domain == "libreoffice_impress" and action == "table.format_text":
        cells = result.get("cells")
        if not isinstance(cells, list):
            return None
        return {
            "rows": result.get("rows"),
            "columns": result.get("columns"),
            "cells": [
                {
                    "row": cell.get("row"),
                    "column": cell.get("column"),
                    "properties": cell.get("properties"),
                }
                for cell in cells
                if isinstance(cell, dict)
            ],
        }
    if domain == "libreoffice_impress" and action == "table.replace_row":
        return {
            key: result.get(key)
            for key in (
                "slide",
                "display_slide_number",
                "path",
                "name",
                "kind",
                "rows",
                "columns",
                "row_number",
                "values",
                "actual_values",
                "verification_passed",
            )
        } | {
            "guidance": (
                "The Adapter resolved exactly one live table, replaced the complete "
                "model-selected row, and read it back. Save and structurally inspect "
                "the presentation before completion; do not repeat the mutation."
            )
        }
    if domain == "libreoffice_impress" and action == "shape.fit_to_slide":
        return {
            key: result.get(key)
            for key in (
                "slide",
                "display_slide_number",
                "requested_selector",
                "requested_selection",
                "resolved_selector",
                "selection_basis",
                "mode",
                "name",
                "kind",
                "path",
                "x",
                "y",
                "width",
                "height",
                "slide_width",
                "slide_height",
                "verification_passed",
            )
        } | {
            "guidance": (
                "The model-selected graphic selector was resolved against live slide "
                "geometry and fitted as requested. Save, then call presentation.inspect "
                "to confirm the same resolved_selector geometry before completion. For "
                "mode=cover, aspect ratio is preserved by centered cropping, so negative "
                "x/y or a size beyond the slide bounds is expected and is not a failure; "
                "do not retry solely because of that geometry."
            )
        }
    if domain == "libreoffice_impress" and action == "shape.insert_image":
        return {
            key: result.get(key)
            for key in (
                "slide",
                "display_slide_number",
                "path",
                "name",
                "kind",
                "x",
                "y",
                "width",
                "height",
                "requested_path",
                "source_path",
                "source_loaded",
                "requested_measurements",
                "resolved_geometry",
                "verification_passed",
            )
        } | {
            "guidance": (
                "The Adapter converted the model-selected physical measurements and read "
                "back the inserted image. Save and inspect the presentation before completion; "
                "do not insert or resize another image as verification."
            )
        }
    return None
