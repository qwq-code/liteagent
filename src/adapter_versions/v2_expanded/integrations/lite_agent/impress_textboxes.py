"""Generic Impress textbox-color intent and structural completion evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .completion_policy import action_is_save
from .impress_background import parse_background_intent
from .impress_colors import IMPRESS_NAMED_COLORS, normalize_impress_color


@dataclass(frozen=True)
class AllTextboxColorIntent:
    slide: int
    color: str
    color_token: str


def parse_all_textbox_color_intent(
    instruction: str,
) -> AllTextboxColorIntent | None:
    """Parse one-slide, all-textbox font-color requests from public language."""
    if not re.search(
        r"(?i)\b(?:all|every|each)\b.{0,24}\b(?:text\s*box(?:es)?|textbox(?:es)?)\b",
        instruction,
    ):
        return None
    if not re.search(
        r"(?i)\b(?:font|text)\s+colou?r\b|\bcolou?r\b.{0,24}\b(?:font|text)\b",
        instruction,
    ):
        return None
    slide_matches = list(
        re.finditer(
            r"(?i)\b(?:slide|page)\s*(?:number\s*)?([1-9][0-9]*)\b",
            instruction,
        )
    )
    if len(slide_matches) != 1:
        return None

    names = "|".join(
        sorted(
            (re.escape(name) for name in IMPRESS_NAMED_COLORS), key=len, reverse=True
        )
    )
    color_match = re.search(
        rf"(?i)\b(?:font|text)\s+colou?r\b.{{0,100}}?"
        rf"(?:['\"`]?(?P<after>{names})['\"`]?|(?P<after_hex>#[0-9a-f]{{6}}))\b|"
        rf"(?:['\"`]?(?P<before>{names})['\"`]?|(?P<before_hex>#[0-9a-f]{{6}}))\b"
        rf".{{0,48}}?\b(?:font|text)\s+colou?r\b",
        instruction,
    )
    if color_match is None:
        return None
    token = next(
        value for value in color_match.groupdict().values() if value is not None
    )
    color = normalize_impress_color(token)
    if color is None:
        return None
    return AllTextboxColorIntent(
        slide=int(slide_matches[0].group(1)) - 1,
        color=color,
        color_token=" ".join(token.casefold().split()),
    )


def textbox_color_argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject semantically wrong model calls without changing their arguments."""
    intent = parse_all_textbox_color_intent(str(state.instruction))
    if intent is None:
        return []
    if action == "slide.set_background":
        if parse_background_intent(str(state.instruction)) is not None:
            return []
        return [
            "the instruction requests the font color of text boxes, not the slide "
            "background; select slide.format_text_roles"
        ]
    if action == "shape.format_text":
        return [
            "the instruction targets every text box on one slide; select the reusable "
            "slide.format_text_roles action with roles=['all'] instead of one shape selector"
        ]
    if action != "slide.format_text_roles":
        return []
    if "color" not in arguments:
        return []
    if arguments.get("slide") != intent.slide:
        return [
            "the instruction targets one numbered slide; the model must pass "
            f"slide={intent.slide} using the zero-based slide index"
        ]
    roles = arguments.get("roles")
    if not isinstance(roles, list) or "all" not in roles:
        return [
            "the instruction targets every text box; the model must pass roles=['all']"
        ]
    if normalize_impress_color(arguments.get("color")) != intent.color:
        return [
            "the model-selected text color does not match the instruction color "
            f"{intent.color_token!r}"
        ]
    return []


def _arguments(event: Any) -> dict[str, Any]:
    arguments = event.proposed.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def _mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mappings(child)


def _inspection_slides(event: Any) -> list[dict[str, Any]]:
    for candidate in _mappings(event.result):
        slides = candidate.get("slides")
        if isinstance(slides, list) and all(isinstance(item, dict) for item in slides):
            return slides
    return []


def _slide_index(slide: dict[str, Any]) -> int | None:
    value = slide.get("slide", slide.get("index"))
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def _live_text_shapes(slide: dict[str, Any]) -> list[dict[str, Any]]:
    collection = slide.get("recursive_text_shapes")
    if not isinstance(collection, list):
        collection = slide.get("text_shapes", [])
    return [
        shape
        for shape in collection
        if isinstance(shape, dict)
        and isinstance(shape.get("text_style"), dict)
        and any(str(line).strip() for line in shape.get("lines", []))
    ]


def all_textbox_color_requirement_errors(state: Any) -> list[str]:
    """Require a model-selected all-text rule, save, and structural read-back."""
    intent = parse_all_textbox_color_intent(str(state.instruction))
    if intent is None:
        return []
    mutations = []
    for event in state.successful_action_events("slide.format_text_roles"):
        arguments = _arguments(event)
        roles = arguments.get("roles")
        if (
            arguments.get("slide") == intent.slide
            and isinstance(roles, list)
            and "all" in roles
            and normalize_impress_color(arguments.get("color")) == intent.color
        ):
            mutations.append(event)
    if not mutations:
        return [
            "slide.format_text_roles has not succeeded for the requested zero-based slide, "
            "roles=['all'], and exact text color"
        ]
    mutation = mutations[-1]
    saves = [
        event
        for event in state.successful_adapter_events()
        if event.step > mutation.step
        and action_is_save(str(event.proposed.get("action", "")))
    ]
    if not saves:
        return [
            "save the presentation after formatting every text box, then inspect the "
            "persisted text colors"
        ]
    inspections = [
        event
        for event in state.successful_action_events("presentation.inspect")
        if event.step > saves[-1].step
    ]
    if not inspections:
        return [
            "inspect the presentation after saving to read back every text-box color"
        ]
    slide = next(
        (
            item
            for item in _inspection_slides(inspections[-1])
            if _slide_index(item) == intent.slide
        ),
        None,
    )
    if not isinstance(slide, dict):
        return ["the final inspection does not contain the requested slide"]
    shapes = _live_text_shapes(slide)
    if not shapes:
        return [
            "the final inspection does not expose any nonempty text boxes on the slide"
        ]
    mismatches = [
        shape
        for shape in shapes
        if normalize_impress_color(shape["text_style"].get("color")) != intent.color
    ]
    if mismatches:
        return [
            f"the final inspection shows {len(mismatches)} of {len(shapes)} nonempty "
            "text boxes with a different font color"
        ]
    return []
