"""Strict generic semantics for formatting one observed Impress title."""

from __future__ import annotations

import copy
from typing import Any

from .adapter_results import flattened_shape_summaries
from .completion_policy import action_is_save
from .impress_colors import normalize_impress_color
from .impress_role_formatting import parse_multislide_role_format_intent
from .instruction_semantics import requested_slide_title_formatting
from .result_envelopes import iter_result_mappings


ACTION = "shape.format_text"
INSPECT_ACTION = "presentation.inspect"
_FORMAT_FIELDS = ("font_size", "bold", "underline", "italic", "strike", "color")


def single_title_format_intent(instruction: str) -> dict[str, Any] | None:
    """Return one explicit title-format request for an observed title."""
    if parse_multislide_role_format_intent(instruction) is not None:
        return None
    request = requested_slide_title_formatting(instruction)
    if not isinstance(request, dict) or len(request.get("slides", [])) != 1:
        return None
    requested_fields = {key: request[key] for key in _FORMAT_FIELDS if key in request}
    if not requested_fields:
        return None
    return {
        "slide": request["slides"][0],
        "role": "title",
        **requested_fields,
    }


def _shape_text(shape: dict[str, Any]) -> str:
    lines = shape.get("lines")
    if isinstance(lines, list):
        text = "\n".join(str(line) for line in lines).strip()
        if text:
            return text
    text = shape.get("text")
    return text.strip() if isinstance(text, str) else ""


def _inspection_slides(event: Any) -> list[dict[str, Any]] | None:
    result = event.result if isinstance(event.result, dict) else None
    hint = result.get("context_hint") if isinstance(result, dict) else None
    slides = hint.get("slides") if isinstance(hint, dict) else None
    if not isinstance(slides, list):
        return None
    typed = [slide for slide in slides if isinstance(slide, dict)]
    return typed if len(typed) == len(slides) else None


def _text_shapes(slide: dict[str, Any]) -> list[dict[str, Any]]:
    values = slide.get("recursive_text_shapes")
    if not isinstance(values, list):
        values = slide.get("text_shapes")
    if not isinstance(values, list):
        return []
    shapes: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for shape in values:
        if not isinstance(shape, dict) or not _shape_text(shape):
            continue
        path = shape.get("path")
        identity = (
            ("path", tuple(path))
            if isinstance(path, list)
            else ("name", shape.get("name"), shape.get("x"), shape.get("y"))
        )
        if identity in seen:
            continue
        seen.add(identity)
        shapes.append(shape)
    return shapes


def _coordinate(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return float("inf")
    return float(value)


def _observed_title(
    slides: list[dict[str, Any]], slide_index: int
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    slide = next(
        (
            item
            for item in slides
            if item.get("slide", item.get("index")) == slide_index
        ),
        None,
    )
    if not isinstance(slide, dict):
        return None
    candidates = _text_shapes(slide)
    if not candidates:
        return None
    native = [
        shape
        for shape in candidates
        if str(shape.get("kind", "")).casefold().endswith(".titletextshape")
    ]
    title = (
        native[0]
        if len(native) == 1
        else min(
            candidates,
            key=lambda shape: (
                _coordinate(shape.get("y")),
                _coordinate(shape.get("x")),
                tuple(shape.get("path", [])),
            ),
        )
    )
    return title, candidates


def _selector_matches_shape(selector: Any, shape: dict[str, Any]) -> bool:
    if not isinstance(selector, dict) or not selector:
        return False
    for key, value in selector.items():
        if key == "path":
            matches = isinstance(value, list) and shape.get("path") == value
        elif key == "name":
            matches = isinstance(value, str) and shape.get("name") == value
        elif key == "index":
            path = shape.get("path")
            matches = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and shape.get("index") == value
                and (
                    "path" in selector
                    or not isinstance(path, list)
                    or path == [value]
                )
            )
        elif key == "text":
            text = shape.get("text")
            if not isinstance(text, str):
                lines = shape.get("lines")
                text = "\n".join(str(line) for line in lines) if isinstance(lines, list) else None
            matches = isinstance(value, str) and text == value
        elif key == "kind":
            matches = (
                isinstance(value, str)
                and value.lower() in str(shape.get("kind", "")).lower()
            )
        else:
            return False
        if not matches:
            return False
    return True


def _selector_identifies_title(
    selector: Any, title: dict[str, Any], candidates: list[dict[str, Any]]
) -> bool:
    matches = [
        shape for shape in candidates if _selector_matches_shape(selector, shape)
    ]
    return len(matches) == 1 and matches[0] is title


def _values_equal(field: str, actual: Any, expected: Any) -> bool:
    if field == "font_size":
        return bool(
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and abs(float(actual) - float(expected)) < 1e-6
        )
    if field == "color":
        return normalize_impress_color(actual) == normalize_impress_color(expected)
    return actual is expected


def _arguments_match_intent(state: Any, arguments: Any, intent: dict[str, Any]) -> bool:
    requested = {key: intent[key] for key in _FORMAT_FIELDS if key in intent}
    if (
        not isinstance(arguments, dict)
        or set(arguments) != {"slide", "selector", *requested}
        or arguments.get("slide") != intent["slide"]
        or any(
            not _values_equal(field, arguments.get(field), expected)
            for field, expected in requested.items()
        )
    ):
        return False
    inspections = state.successful_action_events(INSPECT_ACTION)
    if not inspections:
        return False
    slides = _inspection_slides(inspections[-1])
    observed = _observed_title(slides, intent["slide"]) if slides is not None else None
    if observed is None:
        return False
    title, candidates = observed
    # Match against the complete native observation when available: the model
    # context's display lines can omit trailing newlines or truncate long text.
    for result in iter_result_mappings(inspections[-1].result):
        raw_slides = result.get("slides")
        if not isinstance(raw_slides, list):
            continue
        for slide in raw_slides:
            if (
                not isinstance(slide, dict)
                or slide.get("index") != intent["slide"]
                or not isinstance(slide.get("shapes"), list)
            ):
                continue
            candidates = flattened_shape_summaries(slide["shapes"])
            native_title = next(
                (shape for shape in candidates if shape.get("path") == title.get("path")),
                None,
            )
            return bool(
                native_title is not None
                and _selector_identifies_title(
                    arguments.get("selector"), native_title, candidates
                )
            )
    return _selector_identifies_title(arguments.get("selector"), title, candidates)


def title_format_argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject incomplete model calls without creating or replacing arguments."""
    intent = single_title_format_intent(str(state.instruction))
    if intent is None or action != ACTION:
        return []
    if not state.successful_action_events(INSPECT_ACTION):
        return ["inspect the presentation before selecting the live title shape"]
    if _arguments_match_intent(state, arguments, intent):
        return []
    fields = [field for field in _FORMAT_FIELDS if field in intent]
    return [
        "shape.format_text must use the instruction-stated zero-based slide, one selector "
        "that uniquely identifies the observed native or visually topmost title, and every "
        f"explicitly requested formatting field with no extras: {fields!r}"
    ]


def constrain_tool_schema(function: dict[str, Any], instruction: str) -> None:
    """Require model-selected title fields while leaving all values unconstrained."""
    intent = single_title_format_intent(instruction)
    if function.get("name") != "adapter__shape_format_text" or intent is None:
        return
    parameters = function.get("parameters")
    properties = parameters.get("properties") if isinstance(parameters, dict) else None
    fields = [field for field in _FORMAT_FIELDS if field in intent]
    keep = ["slide", "selector", *fields]
    if not isinstance(properties, dict) or any(key not in properties for key in keep):
        return
    parameters["properties"] = {key: copy.deepcopy(properties[key]) for key in keep}
    parameters["required"] = keep
    parameters["additionalProperties"] = False
    parameters.pop("anyOf", None)
    parameters["properties"]["slide"]["description"] = (
        "Zero-based slide selected from the instruction. Supply the value yourself."
    )
    parameters["properties"]["selector"]["description"] = (
        "Use name, path, index, text, or kind copied from the latest "
        "presentation.inspect result for the native title, or the visually topmost "
        "nonempty text shape when no unique native title exists. Combined fields "
        "must all match that same title and identify it uniquely. Name and text "
        "match exactly; kind is a case-insensitive substring. Use a full path for "
        "grouped shapes; index alone addresses a top-level shape."
    )
    function["description"] += (
        " For this single-slide title request, include every explicitly requested title "
        f"format field ({', '.join(fields)}) in one model-selected call. The Runner neither "
        "fills nor rewrites slide, selector, or formatting values."
    )


def _property_matches(field: str, properties: dict[str, Any], expected: Any) -> bool:
    if field == "font_size":
        raw = properties.get("CharHeight")
        try:
            return abs(float(raw) - float(expected)) < 1e-6
        except (TypeError, ValueError):
            return False
    if field == "bold":
        try:
            observed = float(properties.get("CharWeight")) >= 150
        except (TypeError, ValueError):
            return False
        return observed is expected
    if field == "underline":
        observed = str(properties.get("CharUnderline", "")).casefold() not in {
            "",
            "0",
            "false",
            "none",
        }
        return observed is expected
    if field == "italic":
        observed = str(properties.get("CharPosture", "")).casefold() not in {
            "",
            "0",
            "false",
            "none",
        }
        return observed is expected
    if field == "strike":
        observed = str(properties.get("CharStrikeout", "")).casefold() not in {
            "",
            "0",
            "false",
            "none",
        }
        return observed is expected
    if field == "color":
        return normalize_impress_color(properties.get("CharColor")) == (
            normalize_impress_color(expected)
        )
    return False


def _result_confirms(event: Any, intent: dict[str, Any]) -> bool:
    requested = {key: intent[key] for key in _FORMAT_FIELDS if key in intent}
    return any(
        isinstance(properties := candidate.get("properties"), dict)
        and all(
            _property_matches(field, properties, expected)
            for field, expected in requested.items()
        )
        for candidate in iter_result_mappings(event.result)
    )


def _confirmed_mutations(state: Any, intent: dict[str, Any]) -> list[Any]:
    return [
        event
        for event in state.successful_action_events(ACTION)
        if _arguments_match_intent(state, event.proposed.get("arguments"), intent)
        and _result_confirms(event, intent)
    ]


def _style_matches(style: dict[str, Any], intent: dict[str, Any]) -> bool:
    if "font_size" in intent:
        value = style.get("font_size")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if abs(float(value) - float(intent["font_size"])) >= 1e-6:
            return False
    if "bold" in intent:
        try:
            observed = float(style.get("bold_weight")) >= 150
        except (TypeError, ValueError):
            return False
        if observed is not intent["bold"]:
            return False
    if "underline" in intent:
        observed = str(style.get("underline", "")).casefold() not in {
            "",
            "0",
            "false",
            "none",
        }
        if observed is not intent["underline"]:
            return False
    if "italic" in intent:
        observed = str(style.get("italic", "")).casefold() not in {
            "",
            "0",
            "false",
            "none",
        }
        if observed is not intent["italic"]:
            return False
    if "strike" in intent:
        observed = str(style.get("strike", "")).casefold() not in {
            "",
            "0",
            "false",
            "none",
        }
        if observed is not intent["strike"]:
            return False
    if "color" in intent and normalize_impress_color(style.get("color")) != (
        normalize_impress_color(intent["color"])
    ):
        return False
    return True


def _readback_matches(event: Any, intent: dict[str, Any]) -> bool:
    slides = _inspection_slides(event)
    observed = _observed_title(slides, intent["slide"]) if slides is not None else None
    if observed is None:
        return False
    style = observed[0].get("text_style")
    return isinstance(style, dict) and _style_matches(style, intent)


def title_format_requirement_errors(state: Any) -> list[str]:
    """Require Adapter-confirmed mutation, persistence, and structural read-back."""
    intent = single_title_format_intent(str(state.instruction))
    if intent is None:
        return []
    inspections = state.successful_action_events(INSPECT_ACTION)
    if not inspections or _inspection_slides(inspections[-1]) is None:
        return ["inspect the requested slide and resolve its live title shape"]
    mutations = _confirmed_mutations(state, intent)
    if not mutations:
        fields = [field for field in _FORMAT_FIELDS if field in intent]
        return [
            "shape.format_text lacks Adapter-confirmed coverage of every explicit title "
            f"format property selected by the model: {fields!r}"
        ]
    saves = [
        event
        for event in state.successful_adapter_events()
        if event.step > mutations[-1].step
        and action_is_save(str(event.proposed.get("action", "")))
    ]
    if not saves:
        return ["save the presentation after formatting the observed title"]
    readbacks = [
        event
        for event in state.successful_action_events(INSPECT_ACTION)
        if event.step > saves[-1].step
    ]
    if not readbacks:
        return ["read back the observed title formatting after saving the presentation"]
    if not _readback_matches(readbacks[-1], intent):
        return [
            "the final structural read-back does not show every requested title format "
            "property on the observed title shape"
        ]
    return []


def stage_actions(state: Any, actions: list[str]) -> list[str]:
    """Expose discovery or the pending public mutation without deriving arguments."""
    intent = single_title_format_intent(str(state.instruction))
    if intent is None:
        return actions
    if not state.successful_action_events(INSPECT_ACTION):
        return [action for action in actions if action == INSPECT_ACTION]
    if not _confirmed_mutations(state, intent):
        return [action for action in actions if action == ACTION]
    return actions


__all__ = [
    "ACTION",
    "constrain_tool_schema",
    "single_title_format_intent",
    "stage_actions",
    "title_format_argument_contract_errors",
    "title_format_requirement_errors",
]
