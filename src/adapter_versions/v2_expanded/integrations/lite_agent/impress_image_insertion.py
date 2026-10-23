"""Strict generic orchestration contract for physically sized Impress images."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from impress_adapter.geometry_contract import measurement_to_hundredth_mm
from impress_adapter.slide_reference import slide_index_from_reference

from .completion_policy import action_is_save


ACTION = "shape.insert_image"
INSPECT_ACTION = "presentation.inspect"
_INSERT_RE = re.compile(
    r"(?is)\b(?:add|insert|place|put|embed)\b.{0,100}"
    r"\b(?:image|photo|picture|graphic)\b|"
    r"\b(?:image|photo|picture|graphic)\b.{0,100}"
    r"\b(?:add|insert|place|put|embed)\b"
)
_PHYSICAL_SIZE_PAIR_RE = re.compile(
    r"(?i)\b\d+(?:\.\d+)?\s*(?:mm|cm|in(?:ch(?:es)?)?)\s*"
    r"(?:\*|x|by|×)\s*\d+(?:\.\d+)?\s*(?:mm|cm|in(?:ch(?:es)?)?)\b"
)


def is_sized_image_insertion_instruction(instruction: str) -> bool:
    """Classify an application-semantic intent without extracting answer values."""
    return bool(
        _INSERT_RE.search(instruction) and _PHYSICAL_SIZE_PAIR_RE.search(instruction)
    )


def stage_actions(state: Any, actions: list[str]) -> list[str]:
    """Focus the next public action without constructing any of its arguments."""
    if (
        state.domain != "libreoffice_impress"
        or not is_sized_image_insertion_instruction(str(state.instruction))
    ):
        return actions
    successful_insertions = state.successful_action_events(ACTION)
    if successful_insertions:
        # Once an insertion has executed, its semantic job is done.  Drive the
        # existing persistence/read-back sequence without exposing a second
        # equivalent insertion (which could create duplicate image shapes).
        latest_insertion = successful_insertions[-1]
        saves = [
            event
            for event in state.successful_adapter_events()
            if event.step > latest_insertion.step
            and action_is_save(str(event.proposed.get("action", "")))
        ]
        if not saves:
            if "presentation.save" in actions:
                return ["presentation.save"]
            return [INSPECT_ACTION] if INSPECT_ACTION in actions else actions
        if not any(
            event.step > saves[-1].step
            for event in state.successful_action_events(INSPECT_ACTION)
        ):
            return [INSPECT_ACTION] if INSPECT_ACTION in actions else actions
        return [action for action in actions if action != ACTION]
    if not state.successful_action_events(INSPECT_ACTION):
        # Keep the inspection as the first, preferred choice, but do not hide
        # the dependent mutation.  A model must see the complete public
        # contract (including its path and physical-measurement schema) before
        # it chooses a call; the normal prompt still tells it to inspect first.
        return [
            action
            for action in (INSPECT_ACTION, ACTION)
            if action in actions
        ] or actions
    if not state.successful_action_events(ACTION):
        return [ACTION] if ACTION in actions else actions
    return actions


def constrain_image_insertion_tool_schema(function: dict[str, Any], state: Any) -> None:
    """Require explicit semantic parameters while leaving every value model-selected."""
    if (
        function.get("name") != "adapter__shape_insert_image"
        or state.domain != "libreoffice_impress"
        or not is_sized_image_insertion_instruction(str(state.instruction))
    ):
        return
    source = function["parameters"]["properties"]
    fields = (
        "slide",
        "slide_number",
        "path",
        "width_measurement",
        "height_measurement",
    )
    function["parameters"] = {
        "type": "object",
        "properties": {field: source[field] for field in fields},
        "required": ["path", "width_measurement", "height_measurement"],
        "additionalProperties": False,
        "allOf": [
            {
                "anyOf": [
                    {"required": ["slide"]},
                    {"required": ["slide_number"]},
                ]
            }
        ],
    }
    function["description"] += (
        " Call presentation.inspect first when it is available, then select a "
        "slide reference, the exact local image path, and both "
        "physical measurements from the instruction. Preserve each stated value and unit "
        "in its measurement object; the Adapter performs unit conversion. The Runner does "
        "not infer, inject, or repair any argument. You may supply slide, slide_number, or "
        "both only when slide_number equals slide plus one."
    )


def image_insertion_argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject incomplete semantic calls without comparing against extracted answers."""
    if (
        action != ACTION
        or state.domain != "libreoffice_impress"
        or not is_sized_image_insertion_instruction(str(state.instruction))
    ):
        return []
    required_body = {"path", "width_measurement", "height_measurement"}
    slide_fields = {field for field in ("slide", "slide_number") if field in arguments}
    if set(arguments).difference(required_body | {"slide", "slide_number"}):
        return [
            "shape.insert_image accepts only slide references, path, "
            "width_measurement, and height_measurement for a physical-size insertion"
        ]
    if not required_body.issubset(arguments) or not slide_fields:
        return [
            "shape.insert_image requires a model-selected slide reference plus "
            "path, width_measurement, and height_measurement"
        ]
    if slide_index_from_reference(arguments, allow_consistent_pair=True) is None:
        return [
            "shape.insert_image slide and slide_number must identify the same slide when "
            "both are supplied"
        ]
    return []


def _mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mappings(child)


def _confirmed_result(event: Any) -> dict[str, Any] | None:
    arguments = event.proposed.get("arguments")
    if not isinstance(arguments, dict):
        return None
    slide_index = slide_index_from_reference(arguments, allow_consistent_pair=True)
    if slide_index is None:
        return None
    measurements = {
        field: arguments[field]
        for field in ("width_measurement", "height_measurement")
        if field in arguments
    }
    if set(measurements) != {"width_measurement", "height_measurement"}:
        return None
    resolved = {
        axis: measurement_to_hundredth_mm(measurements[f"{axis}_measurement"])
        for axis in ("width", "height")
    }
    return next(
        (
            candidate
            for candidate in _mappings(event.result)
            if candidate.get("slide") == slide_index
            and candidate.get("requested_path") == arguments.get("path")
            and candidate.get("requested_measurements") == measurements
            and candidate.get("resolved_geometry") == resolved
            and isinstance(candidate.get("path"), list)
            and candidate.get("source_loaded") is True
            and candidate.get("verification_passed") is True
        ),
        None,
    )


def _inspection_confirms(event: Any, result: dict[str, Any]) -> bool:
    target_slide = result["slide"]
    target_path = result["path"]
    resolved = result["resolved_geometry"]
    source_name = Path(str(result.get("source_path", ""))).name
    for candidate in _mappings(event.result):
        slides = candidate.get("slides")
        if not isinstance(slides, list):
            continue
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == target_slide
            ),
            None,
        )
        if not isinstance(slide, dict):
            continue
        graphics = slide.get("graphic_shapes")
        if not isinstance(graphics, list):
            continue
        if any(
            isinstance(shape, dict)
            and shape.get("path") == target_path
            and (not source_name or shape.get("name") == source_name)
            and all(shape.get(axis) == value for axis, value in resolved.items())
            for shape in graphics
        ):
            return True
    return False


def image_insertion_requirement_errors(state: Any) -> list[str]:
    """Require Adapter confirmation, persistence, and structural post-save read-back."""
    if (
        state.domain != "libreoffice_impress"
        or not is_sized_image_insertion_instruction(str(state.instruction))
    ):
        return []
    confirmations = [
        (event, result)
        for event in state.successful_action_events(ACTION)
        if (result := _confirmed_result(event)) is not None
    ]
    if not confirmations:
        return [
            "shape.insert_image lacks Adapter-confirmed coverage for the model-selected "
            "slide, local path, and physical width and height"
        ]
    mutation, result = confirmations[-1]
    saves = [
        event
        for event in state.successful_adapter_events()
        if event.step > mutation.step
        and action_is_save(str(event.proposed.get("action", "")))
    ]
    if not saves:
        return ["save the presentation after shape.insert_image before completion"]
    inspections = [
        event
        for event in state.successful_action_events(INSPECT_ACTION)
        if event.step > saves[-1].step
    ]
    if not inspections:
        return [
            "inspect the presentation after saving to read back the inserted image geometry"
        ]
    if not _inspection_confirms(inspections[-1], result):
        return [
            "the post-save presentation inspection does not confirm the inserted image at "
            "the Adapter-resolved physical width and height"
        ]
    return []


__all__ = [
    "ACTION",
    "constrain_image_insertion_tool_schema",
    "image_insertion_argument_contract_errors",
    "image_insertion_requirement_errors",
    "is_sized_image_insertion_instruction",
    "stage_actions",
]
