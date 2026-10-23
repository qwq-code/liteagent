"""Generic completion evidence for fitting a model-selected Impress graphic."""

from __future__ import annotations

import re
from typing import Any

from .completion_policy import action_is_save
from .instruction_semantics import requested_cover_image_slide


def _preserves_proportion(instruction: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b(?:keep|keeping|preserve|preserving|maintain|maintaining)\b"
            r"[^.]{0,40}\b(?:proportion|proportions|aspect ratio)\b",
            instruction,
        )
    )


def _requested_fit_mode(instruction: str) -> str | None:
    if re.search(
        r"(?i)\b(?:without|avoid|prevent)\b[^.]{0,30}\b(?:crop|cropping|cropped)\b",
        instruction,
    ) or re.search(r"(?i)\bfit\b[^.]{0,30}\binside\b", instruction):
        return "contain"
    if re.search(
        r"(?i)\b(?:distortion|distort|distorting)\b[^.]{0,30}"
        r"\b(?:required|acceptable|allowed|permit(?:ted)?)\b",
        instruction,
    ) or re.search(
        r"(?i)\b(?:exact|entire|whole|full)[ -]?(?:slide|page)?\b[^.]{0,40}"
        r"\b(?:width|height|dimensions?)\b[^.]{0,50}\b(?:stretch|distort)",
        instruction,
    ):
        return "stretch"
    if _preserves_proportion(instruction) and re.search(
        r"(?i)\b(?:fill|cover)\b[^.]{0,80}\b(?:entire|whole|full)\b"
        r"|\b(?:entire|whole|full)\b[^.]{0,80}\b(?:fill|cover)\b",
        instruction,
    ):
        return "cover"
    return None


def _inspected_graphics(state: Any, slide_index: int) -> list[dict[str, Any]]:
    slides = state.latest_context_hint("presentation.inspect").get("slides", [])
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == slide_index
        ),
        None,
    )
    if not isinstance(slide, dict):
        return []
    return [
        item
        for item in slide.get("graphic_shapes", [])
        if isinstance(item, dict)
        and isinstance(item.get("width"), int)
        and isinstance(item.get("height"), int)
    ]


def _observed_shape(
    state: Any, slide_index: int, selector: dict[str, Any]
) -> dict[str, Any] | None:
    graphics = _inspected_graphics(state, slide_index)
    if "path" in selector:
        return next(
            (item for item in graphics if item.get("path") == selector["path"]),
            None,
        )
    if "index" in selector:
        return next(
            (item for item in graphics if item.get("index") == selector["index"]),
            None,
        )
    return None


def _model_selected_slide_index(arguments: dict[str, Any]) -> int | None:
    slide = arguments.get("slide")
    if isinstance(slide, bool) or not isinstance(slide, int) or slide < 0:
        return None
    return slide


def validate_fit_arguments(
    state: Any, action: str, arguments: dict[str, Any]
) -> str | None:
    """Return a contradiction without choosing or rewriting any model argument."""
    requested_slide = requested_cover_image_slide(state.instruction)
    selected_slide = _model_selected_slide_index(arguments)
    if requested_slide is not None and selected_slide != requested_slide:
        return (
            f"{action} slide must be {requested_slide}, the zero-based slide reference "
            "explicitly named in the instruction"
        )
    requested_mode = _requested_fit_mode(state.instruction)
    if requested_mode is not None and arguments.get("mode") != requested_mode:
        return (
            f"{action} mode must be {requested_mode} for the instruction's requested "
            "fit semantics"
        )

    describes_landscape = bool(
        re.search(r"(?i)\b(?:wide|landscape|horizontal)\b", state.instruction)
    )
    selector = arguments.get("selector")
    if not isinstance(selector, dict):
        return None
    if not describes_landscape:
        return None
    observed = _observed_shape(state, int(arguments.get("slide", -1)), selector)
    if observed is not None and observed["width"] <= observed["height"]:
        return (
            "the exact selector points to a portrait or square graphic, which contradicts "
            "the instruction's wide/landscape/horizontal target; choose another observed selector"
        )
    return None


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    if state.domain != "libreoffice_impress" or action != "shape.fit_to_slide":
        return []
    contradiction = validate_fit_arguments(state, action, arguments)
    return [contradiction] if contradiction is not None else []


def _fit_evidence(state: Any) -> tuple[Any, dict[str, Any]] | None:
    requested_slide = requested_cover_image_slide(state.instruction)
    events = state.successful_action_events("shape.fit_to_slide")
    for event in sorted(events, key=lambda item: item.step, reverse=True):
        arguments = event.proposed.get("arguments")
        if not isinstance(arguments, dict):
            continue
        selected_slide = _model_selected_slide_index(arguments)
        if requested_slide is not None and selected_slide != requested_slide:
            continue
        requested_mode = _requested_fit_mode(state.instruction)
        if requested_mode is not None and arguments.get("mode") != requested_mode:
            continue
        for result in state._result_mappings(event.result):
            resolved = result.get("resolved_selector")
            request_echo_matches = result.get("requested_selector") == arguments.get(
                "selector"
            )
            if (
                request_echo_matches
                and isinstance(resolved, dict)
                and set(resolved).issubset({"path", "index"})
                and len(resolved) == 1
                and result.get("verification_passed") is True
                and result.get("mode") == arguments.get("mode")
                and result.get("slide") == selected_slide
            ):
                return event, result
    return None


def mutation_applied(state: Any) -> bool:
    return _fit_evidence(state) is not None


def readback_satisfied(state: Any) -> bool:
    evidence = _fit_evidence(state)
    if evidence is None:
        return False
    mutation, result = evidence
    saves = [
        event
        for event in state.successful_adapter_events()
        if action_is_save(str(event.proposed.get("action", "")))
        and event.step > mutation.step
    ]
    if not saves:
        return False
    readbacks = [
        event
        for event in state.successful_action_events("presentation.inspect")
        if event.step > saves[-1].step
        and isinstance(event.result, dict)
        and isinstance(event.result.get("context_hint"), dict)
    ]
    if not readbacks:
        return False

    hint = readbacks[-1].result["context_hint"]
    slide = next(
        (
            item
            for item in hint.get("slides", [])
            if isinstance(item, dict) and item.get("slide") == result["slide"]
        ),
        None,
    )
    if not isinstance(slide, dict):
        return False
    selector = result["resolved_selector"]
    shape = _observed_shape_from_slide(slide, selector)
    if shape is None:
        return False
    if not all(
        isinstance(result.get(field), int)
        and abs(int(shape.get(field, 0)) - result[field]) <= 2
        for field in ("x", "y", "width", "height")
    ):
        return False

    slide_width = slide.get("width")
    slide_height = slide.get("height")
    if not isinstance(slide_width, int) or not isinstance(slide_height, int):
        return False
    centered = (
        abs(shape["x"] - round((slide_width - shape["width"]) / 2)) <= 2
        and abs(shape["y"] - round((slide_height - shape["height"]) / 2)) <= 2
    )
    if not centered:
        return False
    if result["mode"] == "stretch":
        return (
            abs(shape["width"] - slide_width) <= 2
            and abs(shape["height"] - slide_height) <= 2
        )
    if result["mode"] == "contain":
        return (
            shape["width"] <= slide_width + 2
            and shape["height"] <= slide_height + 2
            and (
                abs(shape["width"] - slide_width) <= 2
                or abs(shape["height"] - slide_height) <= 2
            )
        )
    return shape["width"] >= slide_width - 2 and shape["height"] >= slide_height - 2


def _observed_shape_from_slide(
    slide: dict[str, Any], selector: dict[str, Any]
) -> dict[str, Any] | None:
    graphics = [
        item for item in slide.get("graphic_shapes", []) if isinstance(item, dict)
    ]
    if "path" in selector:
        return next(
            (item for item in graphics if item.get("path") == selector["path"]),
            None,
        )
    return next(
        (item for item in graphics if item.get("index") == selector.get("index")),
        None,
    )
