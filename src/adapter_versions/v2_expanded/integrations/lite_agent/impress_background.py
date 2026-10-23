"""Generic Impress background intent and structural completion evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .completion_policy import action_is_save
from .impress_colors import IMPRESS_NAMED_COLORS, normalize_impress_color


_ALL_SLIDE_SCOPE_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"\b(?:all|every|each)\b.{0,30}\b(?:slides?|pages?)\b"
    r"|"
    r"\bthroughout\s+(?:(?:the|this|entire|whole)\s+)*(?:presentation|deck)\b"
    r")"
)


@dataclass(frozen=True)
class BackgroundIntent:
    color: str | None
    slide: int | None = None
    all_slides: bool = False
    source_role: str | None = None


def requests_all_slide_scope(instruction: str) -> bool:
    """Recognize generic language that targets every slide in a deck."""
    return _ALL_SLIDE_SCOPE_RE.search(instruction) is not None


def parse_background_intent(instruction: str) -> BackgroundIntent | None:
    """Parse reusable background color language without using dataset identity."""
    if not re.search(r"(?i)\bbackground(?:\s+colou?r)?\b", instruction):
        return None
    all_slides = requests_all_slide_scope(instruction)
    slide_matches = list(
        re.finditer(
            r"(?i)\b(?:slide|page)\s*(?:number\s*)?([1-9][0-9]*)\b", instruction
        )
    )
    slide = int(slide_matches[-1].group(1)) - 1 if len(slide_matches) == 1 else None
    names = "|".join(
        sorted(
            (re.escape(name) for name in IMPRESS_NAMED_COLORS), key=len, reverse=True
        )
    )
    color_match = re.search(
        rf"(?i)(?:\b(?P<before>{names})\b|(?P<before_hex>#[0-9a-f]{{6}}))"
        rf"\s+background(?:\s+colou?r)?\b|"
        rf"\bbackground(?:\s+colou?r)?\b.{{0,40}}?"
        rf"(?:\b(?P<after>{names})\b|(?P<after_hex>#[0-9a-f]{{6}}))",
        instruction,
    )
    if color_match is not None:
        color = normalize_impress_color(
            next(
                value for value in color_match.groupdict().values() if value is not None
            )
        )
        if color is not None:
            return BackgroundIntent(color=color, slide=slide, all_slides=all_slides)
    matches_title_color = bool(
        slide is not None
        and not all_slides
        and re.search(r"(?is)\b(?:same\b.{0,40}\bas\b|match(?:es|ing)?\b)", instruction)
        and re.search(r"(?i)\btitle(?:['’]s)?\b", instruction)
        and re.search(r"(?i)\bcolou?r\b", instruction)
    )
    if matches_title_color:
        return BackgroundIntent(
            color=None,
            slide=slide,
            source_role="title",
        )
    return None


def _arguments(event: Any) -> dict[str, Any]:
    arguments = event.proposed.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def _matching_mutations(
    state: Any, intent: BackgroundIntent, expected_color: str
) -> list[Any]:
    matches = []
    for event in state.successful_action_events("slide.set_background"):
        arguments = _arguments(event)
        if normalize_impress_color(arguments.get("color")) != expected_color:
            continue
        if intent.all_slides:
            target_matches = arguments.get("all_slides") is True
        elif intent.slide is not None:
            target_matches = arguments.get("slide") == intent.slide
        else:
            target_matches = arguments.get("all_slides") is True or isinstance(
                arguments.get("slide"), int
            )
        if target_matches:
            matches.append(event)
    return matches


def _mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mappings(child)


def _inspection_slides(event: Any) -> tuple[list[dict[str, Any]], int | None]:
    candidates = list(_mappings(event.result))
    for candidate in candidates:
        slides = candidate.get("slides")
        if isinstance(slides, list) and all(isinstance(item, dict) for item in slides):
            count = candidate.get("slide_count")
            return slides, count if isinstance(count, int) and not isinstance(
                count, bool
            ) else None
    return [], None


def _slide_index(slide: dict[str, Any]) -> int | None:
    for key in ("slide", "index"):
        value = slide.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _background_matches(slide: dict[str, Any], expected: str) -> bool:
    background = slide.get("background")
    return bool(
        isinstance(background, dict)
        and str(background.get("style", "")).casefold() == "solid"
        and normalize_impress_color(background.get("color")) == expected
    )


def _title_color(slides: list[dict[str, Any]], target_slide: int) -> str | None:
    slide = next(
        (item for item in slides if _slide_index(item) == target_slide),
        None,
    )
    if not isinstance(slide, dict):
        return None
    colors = {
        color
        for collection_name in ("all_shapes", "text_shapes", "recursive_text_shapes")
        for shape in slide.get(collection_name, [])
        if isinstance(shape, dict)
        and (
            "titletextshape" in str(shape.get("kind", "")).casefold()
            or str(shape.get("role", "")).casefold() == "title"
        )
        and isinstance(shape.get("text_style"), dict)
        and (color := normalize_impress_color(shape["text_style"].get("color")))
        is not None
    }
    return colors.pop() if len(colors) == 1 else None


def expected_background_color(state: Any, intent: BackgroundIntent) -> str | None:
    """Resolve a literal color or one observed public semantic role."""
    if intent.color is not None:
        return intent.color
    if intent.source_role != "title" or intent.slide is None:
        return None
    mutation_steps = [
        event.step for event in state.successful_action_events("slide.set_background")
    ]
    first_mutation_step = min(mutation_steps, default=None)
    inspections = [
        event
        for event in state.successful_action_events("presentation.inspect")
        if first_mutation_step is None or event.step < first_mutation_step
    ]
    for event in reversed(inspections):
        slides, _slide_count = _inspection_slides(event)
        color = _title_color(slides, intent.slide)
        if color is not None:
            return color
    return None


def background_argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject overbroad or semantically wrong model calls without rewriting them."""
    if action != "slide.set_background":
        return []
    intent = parse_background_intent(str(state.instruction))
    if intent is None:
        return []
    if intent.all_slides and arguments.get("all_slides") is not True:
        return [
            "the instruction explicitly targets every slide; the model must select "
            "all_slides=true"
        ]
    if intent.slide is not None and arguments.get("slide") != intent.slide:
        return [
            "the instruction targets one numbered slide; the model must select "
            f"slide={intent.slide} using the zero-based slide index and must not use all_slides"
        ]
    expected_color = expected_background_color(state, intent)
    if expected_color is None:
        return [
            "inspect the target slide and read its unique title color before selecting "
            "slide.set_background"
        ]
    if normalize_impress_color(arguments.get("color")) != expected_color:
        return [
            "the model-selected background color does not match the instruction color "
            f"or the structurally observed source color {expected_color}"
        ]
    return []


def background_requirement_errors(state: Any) -> list[str]:
    """Require model-selected semantic color, persistence, and structural read-back."""
    intent = parse_background_intent(str(state.instruction))
    if intent is None:
        return []
    expected_color = expected_background_color(state, intent)
    if expected_color is None:
        return [
            "inspect the target slide and read its unique title color before selecting "
            "slide.set_background"
        ]
    if intent.slide is not None and any(
        _arguments(event).get("all_slides") is True
        for event in state.successful_action_events("slide.set_background")
    ):
        return [
            "an all_slides background mutation changed slides outside the single requested "
            "target; the task requires a model-selected call scoped only to that slide"
        ]
    mutations = _matching_mutations(state, intent, expected_color)
    if not mutations:
        return [
            "slide.set_background has not succeeded with the instruction-requested "
            "target and semantic color; pass an instruction-named color verbatim instead "
            "of guessing an RGB value"
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
            "save the LibreOffice document after slide.set_background and read back the "
            "final slide background"
        ]
    inspections = [
        event
        for event in state.successful_action_events("presentation.inspect")
        if event.step > saves[-1].step
    ]
    if not inspections:
        return ["read back the final slide background after saving the presentation"]
    slides, slide_count = _inspection_slides(inspections[-1])
    # An unnumbered instruction leaves scope to the model.  When the model
    # explicitly selects ``all_slides=true``, the successful mutation itself
    # establishes that scope; validate every inspected slide rather than
    # trying to compare the absent single-slide index (``None``).
    arguments = _arguments(mutation)
    mutation_targets_all_slides = arguments.get("all_slides") is True
    if intent.all_slides or mutation_targets_all_slides:
        matches = bool(slides) and all(
            _background_matches(slide, expected_color) for slide in slides
        )
        if slide_count is not None:
            if matches and len(slides) < slide_count:
                return [
                    f"background read-back is incomplete: {len(slides)} of {slide_count} "
                    "slides inspected, and their colors match. Run presentation.inspect "
                    "without slides to read the whole presentation; no new background "
                    "mutation is needed for the matching inspected slides"
                ]
            matches = matches and len(slides) == slide_count
    else:
        target = intent.slide
        if target is None:
            target = arguments.get("slide")
        observed = next(
            (slide for slide in slides if _slide_index(slide) == target),
            None,
        )
        matches = isinstance(observed, dict) and _background_matches(
            observed, expected_color
        )
    if not matches:
        return [
            "the inspected final slide background does not match the requested semantic "
            "color and target; correct it with a new model-selected slide.set_background call"
        ]
    return []
