from __future__ import annotations

import math
import re
from copy import copy
from dataclasses import dataclass
from typing import Any

from impress_adapter.geometry_contract import order_shapes_by_position
from impress_adapter.slide_reference import (
    slide_index_from_reference,
    slide_referenced_arguments_equal,
)

from .completion_policy import (
    action_is_read_only,
    action_is_save,
    effective_canonical_action,
)
from .impress_colors import normalize_impress_color
from .impress_role_formatting import ROLE_ACTIONS, action_slide_indices
from .result_envelopes import iter_result_mappings


@dataclass(frozen=True)
class NoteIntent:
    """Presentation-note meaning derived only from application language."""

    target_slide: int | None
    copies_title: bool
    literal_text: str | None


@dataclass(frozen=True)
class PictureHeightIntent:
    """Picture-height targets expressed in zero-based slide coordinates."""

    targets: tuple[tuple[int, int], ...]
    tolerances: tuple[int, ...]

    def as_request(self) -> dict[str, Any]:
        return {
            "role": "picture",
            "targets": [
                {"slide": slide, "height": height} for slide, height in self.targets
            ],
        }


@dataclass(frozen=True)
class TextBoxFontSizeIntent:
    """Font-size assignments for ordered or all text boxes on one slide."""

    slide: int
    scope: str
    sizes: tuple[int | float, ...]

    def as_request(self) -> dict[str, Any]:
        request: dict[str, Any] = {"slide": self.slide, "sizes": list(self.sizes)}
        if self.scope == "all":
            request["scope"] = "all"
        return request


@dataclass(frozen=True)
class TextBoxColorSequenceIntent:
    """Assign colors to text boxes in an explicit visual order."""

    slide: int
    order: str
    colors: tuple[str, ...]

    def as_request(self) -> dict[str, Any]:
        return {
            "slide": self.slide,
            "scope": "nonempty_textboxes",
            "order": self.order,
            "colors": list(self.colors),
        }


@dataclass(frozen=True)
class PictureEdgeIntent:
    """Place one observed picture at a vertical slide edge."""

    slide: int
    edge: str

    def as_request(self) -> dict[str, Any]:
        return {"slide": self.slide, "role": "picture", "edge": self.edge}


@dataclass(frozen=True)
class TextBoxUnderlineIntent:
    """Apply one underline state to every text box on selected slides."""

    slides: tuple[int, ...]
    underline: bool

    def as_request(self) -> dict[str, Any]:
        return {
            "slides": list(self.slides),
            "scope": "all_textboxes",
            "underline": self.underline,
        }


_NOTE_TERM_RE = re.compile(
    r"(?i)\b(?:(?:speaker|presenter)\s+notes?|notes?|remarks?|comments?)\b"
)
_NOTE_CHANGE_RE = re.compile(
    r"(?i)\b(?:add|copy|create|insert|make|overwrite|place|put|replace|set|update|write)\b"
)
_TITLE_TERM = r"(?:title|heading)"
_NOTE_TERM = r"(?:(?:speaker|presenter)\s+notes?|notes?|remarks?|comments?)"
_TITLE_NOTE_RELATIONSHIPS = (
    re.compile(
        rf"(?is)\b(?:copy|duplicate|mirror|repeat|use)\b.{{0,80}}\b{_TITLE_TERM}\b"
    ),
    re.compile(
        rf"(?is)\b{_NOTE_TERM}\b.{{0,80}}"
        rf"\b(?:equal|identical|match(?:ing)?|same)\b.{{0,40}}\b{_TITLE_TERM}\b"
    ),
    re.compile(
        rf"(?is)\b{_TITLE_TERM}\b.{{0,80}}\b(?:as|in|into|to)\b.{{0,40}}"
        rf"\b{_NOTE_TERM}\b"
    ),
    re.compile(
        rf"(?is)\b(?:add|place|put|set|write)\b.{{0,80}}\b{_TITLE_TERM}\b"
        rf".{{0,80}}\b{_NOTE_TERM}\b"
    ),
    re.compile(
        rf"(?is)\b{_NOTE_TERM}\b.{{0,80}}\b(?:from|with)\b.{{0,40}}"
        rf"\b{_TITLE_TERM}\b"
    ),
)
_SLIDE_NUMBER_RE = re.compile(
    r"(?i)\b(?:page|slide)\s*(?:number\s*)?(?P<number>[1-9][0-9]*)\b"
)
_LITERAL_NOTE_RE = re.compile(
    r"(?i)\b(?:add|set|write)\s+(?:a\s+)?note\s*[\"'“‘]([^\"'”’]*)[\"'”’]"
)
_PICTURE_TERM_RE = re.compile(r"(?i)\b(?:image|picture|photo)(?:s)?\b")
_PICTURE_CHANGE_RE = re.compile(
    r"(?i)\b(?:adjust|change|ensure|make|resize|set)\b|"
    r"\b(?:must|needs?\s+to|should)\s+be\b"
)
_TEXTBOX_ALL_RE = re.compile(
    r"(?i)\b(?:all|every)\s+(?:of\s+the\s+)?"
    r"(?:text\s*box(?:es)?|textbox(?:es)?)\b"
)
_FONT_SIZE_CHANGE_RE = re.compile(
    r"(?i)\b(?:adjust|apply|change|ensure|format|make|resize|set)\b|"
    r"\b(?:must|needs?\s+to|should)\s+be\b|^\s*(?:please\s+)?use\b"
)
_POINT_SIZE_RE = re.compile(r"(?i)\b(\d+(?:\.\d+)?)\s*(?:pt|points?)\b")
_PICTURE_POSITION_CHANGE_RE = re.compile(r"(?i)\b(?:move|place|position|put)\b")
_TEXTBOX_COLLECTION_RE = re.compile(
    r"(?i)\b(?:(?:all|every)\s+(?:of\s+the\s+)?"
    r"(?:text\s*box(?:es)?|textbox(?:es)?)|(?:text\s*boxes|textboxes))\b"
)
_UNDERLINE_RE = re.compile(r"(?i)\b(?:underline|underlined|underlining)\b")
_TEXT_COLOR_CHANGE_RE = re.compile(
    r"(?i)\b(?:change|set|apply|format|make|use)\b.{0,100}"
    r"\b(?:font|text)\s+colou?r\b|"
    r"\b(?:font|text)\s+colou?r\b.{0,100}"
    r"\b(?:change|set|apply|format|make|use)\b"
)
_COLOR_TOKEN_RE = re.compile(
    r"(?i)#[0-9a-f]{6}\b|\b(?:black|white|red|green|blue|yellow|orange|"
    r"purple|gr[ae]y|cyan|magenta)\b"
)
_LENGTH_VALUE_PATTERN = (
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>cm|mm|in(?:ch(?:es)?)?)\b"
)


def _number(value: str) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def _to_hundredth_mm(value: str, unit: str) -> int:
    normalized = unit.casefold()
    factor = 1000.0 if normalized == "cm" else 100.0
    if normalized.startswith("in"):
        factor = 2540.0
    return round(float(value) * factor)


def _measurement_tolerance(value: str, unit: str) -> int:
    """Use half of the instruction's expressed unit precision for idempotence."""
    decimal_places = len(value.partition(".")[2]) if "." in value else 0
    resolution = 10 ** (-decimal_places)
    normalized = unit.casefold()
    factor = 1000.0 if normalized == "cm" else 100.0
    if normalized.startswith("in"):
        factor = 2540.0
    return max(1, round(resolution * factor / 2))


def _instruction_clauses(instruction: str) -> list[str]:
    text = re.sub(r"\s+", " ", instruction).strip()
    return [
        clause.strip()
        for clause in re.split(
            r"(?i)\b(?:while|whereas)\b|[;\n]|(?<!\d)\.(?!\d)|"
            r"\s+\band\b\s+(?=(?:on\s+(?:slide|page)\b|"
            r"(?:adjust|change|ensure|format|make|resize|set)\b))",
            text,
        )
        if clause.strip()
    ]


def _listed_slide_indices(text: str) -> tuple[int, ...]:
    """Expand application-language slide lists into zero-based indices."""
    values: set[int] = set()
    token_re = re.compile(r"(?i)\s*(\d+|,|&|-|\band\b|\bto\b|\bthrough\b)")
    for term in re.finditer(r"(?i)\b(?:slides?|pages?)\b", text):
        cursor = term.end()
        tokens: list[str] = []
        while match := token_re.match(text, cursor):
            tokens.append(match.group(1))
            cursor = match.end()
        spec = " ".join(tokens)
        if not spec:
            continue
        numbers = [int(value) for value in re.findall(r"\d+", spec)]
        values.update(value for value in numbers if value >= 1)
        for start, end in re.findall(r"(?i)(\d+)\s*(?:-|to|through)\s*(\d+)", spec):
            first, last = int(start), int(end)
            if first >= 1 and last >= first:
                values.update(range(first, last + 1))
    return tuple(value - 1 for value in sorted(values))


def _single_clause_picture_height(clause: str) -> tuple[int, int] | None:
    if not _PICTURE_TERM_RE.search(clause) or not _PICTURE_CHANGE_RE.search(clause):
        return None
    patterns = (
        re.compile(rf"(?is)\bheight\b.{{0,55}}?{_LENGTH_VALUE_PATTERN}"),
        re.compile(
            rf"(?is)\b(?:image|picture|photo)(?:s)?\b.{{0,90}}?"
            rf"{_LENGTH_VALUE_PATTERN}\s*(?:high|in\s+height)\b"
        ),
    )
    values = {
        (
            _to_hundredth_mm(match.group("value"), match.group("unit")),
            _measurement_tolerance(match.group("value"), match.group("unit")),
        )
        for pattern in patterns
        for match in pattern.finditer(clause)
    }
    if len(values) != 1:
        return None
    height, tolerance = values.pop()
    return (height, tolerance) if height > 0 else None


def parse_picture_height_intent(instruction: str) -> PictureHeightIntent | None:
    """Parse reusable picture-height requests without consulting task identity."""
    respectively = re.search(
        r"(?is)\b(?:image|picture|photo)(?:['’]s)?\s+height\b\s*"
        r"(?:to|as|of)?\s*(?P<heights>.+?)\b(?:on|for)\s+slides?\s+"
        r"(?P<slides>.+?)\s+respectively\b",
        instruction,
    )
    if respectively is not None:
        height_tokens = re.findall(
            r"(\d+(?:\.\d+)?)\s*(cm|mm|in(?:ch(?:es)?)?)?",
            respectively.group("heights"),
            flags=re.IGNORECASE,
        )
        slide_numbers = [
            int(value) for value in re.findall(r"\d+", respectively.group("slides"))
        ]
        explicit_units = {
            unit.casefold() for _value, unit in height_tokens if unit.strip()
        }
        if (
            height_tokens
            and len(height_tokens) == len(slide_numbers)
            and len(explicit_units) == 1
            and all(slide >= 1 for slide in slide_numbers)
        ):
            common_unit = next(iter(explicit_units))
            normalized = [
                (slide - 1, value, unit.casefold() if unit else common_unit)
                for slide, (value, unit) in zip(
                    slide_numbers, height_tokens, strict=True
                )
            ]
            targets = tuple(
                (slide, _to_hundredth_mm(value, unit))
                for slide, value, unit in normalized
            )
            if all(height > 0 for _slide, height in targets):
                return PictureHeightIntent(
                    targets,
                    tuple(
                        _measurement_tolerance(value, unit)
                        for _slide, value, unit in normalized
                    ),
                )

    targets: dict[int, tuple[int, int]] = {}
    for clause in _instruction_clauses(instruction):
        measurement = _single_clause_picture_height(clause)
        slide_numbers = [
            int(match.group("number")) for match in _SLIDE_NUMBER_RE.finditer(clause)
        ]
        if measurement is None or not slide_numbers:
            continue
        height, tolerance = measurement
        for slide_number in slide_numbers:
            slide = slide_number - 1
            previous = targets.get(slide)
            if previous is not None and previous != measurement:
                return None
            targets[slide] = (height, tolerance)
    return (
        PictureHeightIntent(
            tuple((slide, measurement[0]) for slide, measurement in targets.items()),
            tuple(measurement[1] for measurement in targets.values()),
        )
        if targets
        else None
    )


def parse_textbox_font_size_intent(
    instruction: str,
) -> TextBoxFontSizeIntent | None:
    """Parse ordered or all-textbox font-size requests from application language."""
    slide_matches = list(_SLIDE_NUMBER_RE.finditer(instruction))
    if (
        len(slide_matches) == 1
        and re.search(r"(?i)\b(?:text\s*box|textbox)", instruction)
        and _FONT_SIZE_CHANGE_RE.search(instruction)
    ):
        ordinal_values = {
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
            "sixth": 6,
            "seventh": 7,
            "eighth": 8,
            "ninth": 9,
            "tenth": 10,
        }
        assignments: dict[int, int | float] = {}
        conflict = False
        for match in re.finditer(
            r"(?is)\b(?P<ordinal>first|second|third|fourth|fifth|sixth|"
            r"seventh|eighth|ninth|tenth)\b"
            r"(?:\s+(?:text\s*box|textbox))?"
            r"(?:(?!\b(?:first|second|third|fourth|fifth|sixth|seventh|"
            r"eighth|ninth|tenth)\b)[^.;]){0,80}?"
            r"(?P<size>\d+(?:\.\d+)?)\s*(?:pt|points?)\b",
            instruction,
        ):
            position = ordinal_values[match.group("ordinal").casefold()]
            size = _number(match.group("size"))
            if size <= 0 or (position in assignments and assignments[position] != size):
                conflict = True
                break
            assignments[position] = size
        positions = set(assignments)
        if (
            not conflict
            and len(assignments) >= 2
            and positions == set(range(1, len(assignments) + 1))
        ):
            return TextBoxFontSizeIntent(
                slide=int(slide_matches[0].group("number")) - 1,
                scope="ordered",
                sizes=tuple(assignments[position] for position in sorted(assignments)),
            )

    for clause in _instruction_clauses(instruction):
        if not _TEXTBOX_ALL_RE.search(clause) or not _FONT_SIZE_CHANGE_RE.search(
            clause
        ):
            continue
        slide_numbers = [
            int(match.group("number")) for match in _SLIDE_NUMBER_RE.finditer(clause)
        ]
        point_sizes = [_number(value) for value in _POINT_SIZE_RE.findall(clause)]
        if len(slide_numbers) != 1 or len(point_sizes) != 1 or point_sizes[0] <= 0:
            continue
        return TextBoxFontSizeIntent(
            slide=slide_numbers[0] - 1,
            scope="all",
            sizes=(point_sizes[0],),
        )
    return None


def _textbox_visual_order(instruction: str) -> str | None:
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    normalized = re.sub(r"\s+", " ", normalized)
    candidates = {
        order
        for order, pattern in {
            "top_to_bottom": r"\b(?:from )?top to bottom\b",
            "bottom_to_top": r"\b(?:from )?bottom to top\b",
            "left_to_right": r"\b(?:from )?left to right\b",
            "right_to_left": r"\b(?:from )?right to left\b",
        }.items()
        if re.search(pattern, normalized)
    }
    return candidates.pop() if len(candidates) == 1 else None


def _ordered_color_tokens(text: str) -> tuple[str, ...]:
    colors = []
    for match in _COLOR_TOKEN_RE.finditer(text):
        value = match.group(0)
        colors.append(value.upper() if value.startswith("#") else value.casefold())
    return tuple(colors)


def parse_textbox_color_sequence_intent(
    instruction: str,
) -> TextBoxColorSequenceIntent | None:
    """Parse colors paired with text boxes by an explicit geometric order."""
    if not _TEXTBOX_COLLECTION_RE.search(
        instruction
    ) or not _TEXT_COLOR_CHANGE_RE.search(instruction):
        return None
    respectively = re.search(r"(?i)\brespectively\b", instruction)
    order = _textbox_visual_order(instruction)
    slide_matches = list(_SLIDE_NUMBER_RE.finditer(instruction))
    if respectively is None or order is None or len(slide_matches) != 1:
        return None

    prefix = instruction[: respectively.start()]
    slide_match = slide_matches[0]
    if slide_match.start() < respectively.start():
        color_region = prefix[slide_match.end() :]
    else:
        color_region = prefix
    colors = _ordered_color_tokens(color_region)
    if len(colors) < 2:
        to_matches = list(re.finditer(r"(?i)\bto\b", prefix))
        colors = _ordered_color_tokens(
            prefix[to_matches[-1].end() :] if to_matches else prefix
        )
    if len(colors) < 2:
        return None
    return TextBoxColorSequenceIntent(
        slide=int(slide_match.group("number")) - 1,
        order=order,
        colors=colors,
    )


def parse_picture_edge_intent(instruction: str) -> PictureEdgeIntent | None:
    """Parse reusable vertical picture-edge placement language."""
    intents: set[tuple[int, str]] = set()
    for clause in _instruction_clauses(instruction):
        if not _PICTURE_TERM_RE.search(
            clause
        ) or not _PICTURE_POSITION_CHANGE_RE.search(clause):
            continue
        edge_match = re.search(
            r"(?i)\b(?:to|at|along|on)\s+(?:(?:the|slide)\s+)?"
            r"(?P<edge>top|bottom)(?:\s+(?:edge|of\s+the\s+slide))?\b",
            clause,
        )
        slides = _listed_slide_indices(clause)
        if edge_match is None or len(slides) != 1:
            continue
        intents.add((slides[0], edge_match.group("edge").casefold()))
    if len(intents) != 1:
        return None
    slide, edge = intents.pop()
    return PictureEdgeIntent(slide=slide, edge=edge)


def parse_textbox_underline_intent(
    instruction: str,
) -> TextBoxUnderlineIntent | None:
    """Parse all-textbox underline state across an arbitrary slide list."""
    requested: dict[int, bool] = {}
    for clause in _instruction_clauses(instruction):
        if not _TEXTBOX_COLLECTION_RE.search(clause) or not _UNDERLINE_RE.search(
            clause
        ):
            continue
        slides = _listed_slide_indices(clause)
        if not slides:
            continue
        underline = not bool(
            re.search(
                r"(?i)\b(?:remove|clear|disable)\b.{0,40}\bunderlin|"
                r"\b(?:not|without|no)\s+underlin|\bunderlin(?:e|ed|ing)?\b"
                r".{0,40}\b(?:off|false)\b",
                clause,
            )
        )
        for slide in slides:
            previous = requested.get(slide)
            if previous is not None and previous is not underline:
                return None
            requested[slide] = underline
    states = set(requested.values())
    if not requested or len(states) != 1:
        return None
    return TextBoxUnderlineIntent(
        slides=tuple(sorted(requested)),
        underline=states.pop(),
    )


def parse_note_intent(instruction: str) -> NoteIntent | None:
    """Parse a note-writing request without relying on task identity or answer data."""
    text = re.sub(r"\s+", " ", instruction).strip()
    if not _NOTE_TERM_RE.search(text) or not _NOTE_CHANGE_RE.search(text):
        return None
    if re.search(r"(?i)\b(?:comments?|remarks?)\b", text) and not re.search(
        r"(?i)\b(?:deck|page|presentation|slide|speaker|presenter|notes?)\b",
        text,
    ):
        return None
    slide_numbers = {
        int(match.group("number")) - 1 for match in _SLIDE_NUMBER_RE.finditer(text)
    }
    target_slide = slide_numbers.pop() if len(slide_numbers) == 1 else None
    copies_title = any(pattern.search(text) for pattern in _TITLE_NOTE_RELATIONSHIPS)
    literal_match = _LITERAL_NOTE_RE.search(text)
    return NoteIntent(
        target_slide=target_slide,
        copies_title=copies_title,
        literal_text=literal_match.group(1) if literal_match else None,
    )


def literal_note_text(instruction: str) -> str | None:
    intent = parse_note_intent(instruction)
    return intent.literal_text if intent is not None else None


def required_actions(
    domain: str, instruction: str, *, strict_generic: bool = False
) -> list[str]:
    if domain != "libreoffice_impress":
        return []
    actions: list[str] = []
    if strict_generic and re.search(
        r"(?is)\b(?:one|1)\s+images?\s+per\s+slide\b|"
        r"\bimages?\b.{0,100}\b(?:each|every)\s+(?:new\s+)?slide\b|"
        r"\b(?:series|sequence)\b.{0,80}\bimages?\b.{0,80}\bslides?\b",
        instruction,
    ):
        # A slide/image sequence is composed from explicit, independently
        # selected primitives.  Do not expose a batch creator that chooses
        # slide count, ordering, or paths on the model's behalf.
        actions.extend(["presentation.inspect", "slide.create", "shape.insert_image"])
    note_intent = parse_note_intent(instruction)
    if note_intent is not None:
        if note_intent.copies_title:
            actions.extend(["presentation.inspect", "slide.set_notes"])
        else:
            actions.append("slide.set_notes")
    if parse_picture_height_intent(instruction) is not None:
        actions.extend(["presentation.inspect", "shape.set_geometry"])
    if parse_picture_edge_intent(instruction) is not None:
        actions.extend(["presentation.inspect", "shape.set_geometry"])
    textbox_font_size = parse_textbox_font_size_intent(instruction)
    if textbox_font_size is not None:
        if strict_generic and textbox_font_size.scope == "all":
            actions.extend(["presentation.inspect", "slide.format_text_roles"])
        else:
            actions.extend(["presentation.inspect", "shape.format_text"])
    if parse_textbox_color_sequence_intent(instruction) is not None:
        actions.extend(["presentation.inspect", "shape.format_text"])
    if parse_textbox_underline_intent(instruction) is not None:
        # Underline targets are resolved to one live shape at a time.  Keeping
        # the atomic action public lets the model select each observation-
        # derived selector and preserves the model-authored argument payload.
        actions.extend(["presentation.inspect", "shape.format_text"])
    return list(dict.fromkeys(actions))


def _inspection_slides(event: Any) -> list[dict[str, Any]] | None:
    result = event.result if isinstance(event.result, dict) else None
    hint = result.get("context_hint") if isinstance(result, dict) else None
    slides = hint.get("slides") if isinstance(hint, dict) else None
    if not isinstance(slides, list) or not slides:
        return None
    typed = [slide for slide in slides if isinstance(slide, dict)]
    return typed if len(typed) == len(slides) else None


def _shape_text(shape: dict[str, Any]) -> str:
    text = shape.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    lines = shape.get("lines")
    if isinstance(lines, list) and all(isinstance(line, str) for line in lines):
        joined = "\n".join(line for line in lines if line.strip()).strip()
        if joined:
            return joined
    paragraphs = shape.get("paragraphs")
    if isinstance(paragraphs, list):
        joined = "\n".join(
            str(paragraph.get("text", ""))
            for paragraph in paragraphs
            if isinstance(paragraph, dict) and str(paragraph.get("text", "")).strip()
        ).strip()
        if joined:
            return joined
    return ""


def _observed_slide_title(slide: dict[str, Any]) -> str | None:
    titles: list[str] = []
    for collection_name in ("text_shapes", "all_shapes", "shapes"):
        collection = slide.get(collection_name)
        if not isinstance(collection, list):
            continue
        for shape in collection:
            if (
                not isinstance(shape, dict)
                or "titletextshape" not in str(shape.get("kind", "")).casefold()
            ):
                continue
            text = _shape_text(shape)
            if text:
                titles.append(text)
    unique = list(dict.fromkeys(titles))
    return unique[0] if len(unique) == 1 else None


def title_note_arguments(state: Any) -> dict[str, Any] | None:
    intent = parse_note_intent(state.instruction)
    if (
        state.domain != "libreoffice_impress"
        or intent is None
        or not intent.copies_title
    ):
        return None
    for event in reversed(state.successful_action_events("presentation.inspect")):
        slides = _inspection_slides(event)
        if slides is None:
            continue
        target_slide = intent.target_slide
        if target_slide is None:
            if len(slides) != 1 or not isinstance(slides[0].get("slide"), int):
                continue
            target_slide = slides[0]["slide"]
        observed = next(
            (slide for slide in slides if slide.get("slide") == target_slide),
            None,
        )
        if observed is None:
            continue
        title = _observed_slide_title(observed)
        if title is not None:
            return {"slide": target_slide, "text": title}
    return None


def picture_height_request(instruction: str) -> dict[str, Any] | None:
    intent = parse_picture_height_intent(instruction)
    return intent.as_request() if intent is not None else None


def textbox_font_size_request(instruction: str) -> dict[str, Any] | None:
    intent = parse_textbox_font_size_intent(instruction)
    return intent.as_request() if intent is not None else None


def _shape_selector(shape: dict[str, Any]) -> dict[str, Any] | None:
    path = shape.get("path")
    if (
        isinstance(path, list)
        and path
        and all(
            isinstance(index, int) and not isinstance(index, bool) and index >= 0
            for index in path
        )
    ):
        return {"path": path}
    index = shape.get("index")
    if isinstance(index, int) and not isinstance(index, bool) and index >= 0:
        return {"index": index}
    return None


def _observed_shape(
    slide: dict[str, Any], selector: dict[str, Any], collections: tuple[str, ...]
) -> dict[str, Any] | None:
    for collection_name in collections:
        collection = slide.get(collection_name)
        if not isinstance(collection, list):
            continue
        for shape in collection:
            if not isinstance(shape, dict):
                continue
            if "path" in selector and shape.get("path") == selector["path"]:
                return shape
            if "index" in selector and shape.get("index") == selector["index"]:
                return shape
    return None


def _latest_post_save_inspection(state: Any, after_step: int) -> Any | None:
    events = state.successful_adapter_events()
    saves = [
        event
        for event in events
        if action_is_save(str(event.proposed.get("action", "")))
        and event.step > after_step
    ]
    if not saves:
        return None
    latest = None
    pages: dict[int, dict[str, Any]] = {}
    # Focused reads describe separate pages of the same saved document.
    for event in events:
        if event.step <= saves[-1].step:
            continue
        domain, action, _ = effective_canonical_action(event, state.domain)
        if domain != "libreoffice_impress" or action != "presentation.inspect":
            if not action_is_read_only(action):
                pages.clear()
                latest = None
            continue
        slides = _inspection_slides(event)
        if slides is None:
            continue
        hint = event.result["context_hint"]
        if latest is not None and any(
            hint.get(key) != latest.result["context_hint"].get(key)
            for key in ("identity", "slide_count")
        ):
            pages.clear()
        latest = event
        for page in slides:
            if type(page.get("slide")) is int:
                pages[page["slide"]] = page
    if latest is None or len(pages) <= len(_inspection_slides(latest) or []):
        return latest
    merged = copy(latest)
    merged.result = {
        **latest.result,
        "context_hint": {
            **latest.result["context_hint"],
            "slides": [pages[index] for index in sorted(pages)],
            "inspected_slides": sorted(pages),
        },
    }
    return merged


def _is_likely_background_picture(shape: dict[str, Any], slide: dict[str, Any]) -> bool:
    """Identify slide-covering images while retaining them as a fallback target."""
    slide_width = slide.get("width")
    slide_height = slide.get("height")
    x = shape.get("x")
    y = shape.get("y")
    width = shape.get("width")
    height = shape.get("height")
    values = (slide_width, slide_height, x, y, width, height)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return False
    if slide_width <= 0 or slide_height <= 0 or width <= 0 or height <= 0:
        return False
    near_origin = x <= slide_width * 0.05 and y <= slide_height * 0.05
    spans_slide = width >= slide_width * 0.9 and height >= slide_height * 0.6
    return near_origin and spans_slide


def _observed_picture_candidates(slide: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unique, non-text picture-like containers from structural inspection."""
    nonempty_text_paths = {
        tuple(shape["path"])
        for shape in slide.get("text_shapes", [])
        if isinstance(shape, dict)
        and isinstance(shape.get("path"), list)
        and any(str(line).strip() for line in shape.get("lines", []))
    }
    picture_containers = slide.get("picture_containers")
    all_shapes = slide.get("all_shapes")
    candidate_source = [
        *(picture_containers if isinstance(picture_containers, list) else []),
        *(all_shapes if isinstance(all_shapes, list) else []),
    ]
    candidates: list[dict[str, Any]] = []
    candidate_paths: set[tuple[int, ...]] = set()
    for shape in candidate_source:
        if not isinstance(shape, dict):
            continue
        selector = _shape_selector(shape)
        if selector is None or "path" not in selector:
            continue
        selector_path = tuple(selector["path"])
        if selector_path in candidate_paths:
            continue
        kind = str(shape.get("kind", "")).casefold()
        contains_graphic = (
            isinstance(shape.get("graphic_count"), int)
            and not isinstance(shape.get("graphic_count"), bool)
            and shape["graphic_count"] > 0
        )
        if not contains_graphic and not (
            "graphic" in kind
            or "customshape" in kind
            or kind in {"image", "picture", "photo"}
        ):
            continue
        if selector_path in nonempty_text_paths:
            continue
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
            continue
        candidate_paths.add(selector_path)
        candidates.append(shape)
    return candidates


def _primary_picture(slide: dict[str, Any]) -> dict[str, Any] | None:
    candidates = _observed_picture_candidates(slide)
    if not candidates:
        return None
    foreground = [
        shape for shape in candidates if not _is_likely_background_picture(shape, slide)
    ]
    return max(
        foreground or candidates,
        key=lambda candidate: candidate["width"] * candidate["height"],
    )


def picture_height_plan(state: Any) -> dict[str, Any] | None:
    intent = parse_picture_height_intent(state.instruction)
    request = intent.as_request() if intent is not None else None
    initial = state.initial_presentation_context_hint()
    slides = initial.get("slides") if isinstance(initial, dict) else None
    if request is None or not isinstance(slides, list):
        return None
    resolved_targets: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    for target_index, requested in enumerate(request["targets"]):
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == requested["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        shape = _primary_picture(slide)
        if shape is None:
            return None
        selector = _shape_selector(shape)
        assert selector is not None
        target = {
            "slide": requested["slide"],
            "selector": selector,
            "shape_name": shape.get("name"),
            "shape_kind": shape.get("kind"),
            "source_width": shape["width"],
            "source_height": shape["height"],
            "target_height": requested["height"],
            "tolerance": intent.tolerances[target_index],
        }
        arguments = {
            "slide": requested["slide"],
            "selector": selector,
            "height": requested["height"],
        }
        step = {"action": "shape.set_geometry", "arguments": arguments}
        target["step"] = step
        target["already_within_precision"] = (
            abs(shape["height"] - requested["height"])
            <= intent.tolerances[target_index]
        )
        resolved_targets.append(target)
        if not target["already_within_precision"]:
            steps.append(step)
    return {**request, "resolved_targets": resolved_targets, "steps": steps}


def _selector_argument_matches(observed: Any, expected: Any) -> bool:
    """Compare model-selected selectors without relying on Adapter result paths.

    ``shape.set_geometry`` returns a compact shape summary whose path can be
    unavailable (the worker uses ``[-1]`` for an index-less selector).  The
    model proposal is therefore the authoritative selector identity for this
    event, while the Adapter result supplies the verified geometry.
    """
    if not isinstance(observed, dict) or not isinstance(expected, dict):
        return False
    # The selector is model-authored identity, so an extra or conflicting key
    # must not be discarded when deciding whether an event matched the plan.
    # Public schemas normally expose one selector key; exact comparison also
    # keeps malformed combined selectors fail-closed at this boundary.
    return observed == expected


def _single_textbox_selector(selector: Any) -> tuple[str, Any] | None:
    """Return one safe identity key from a model-selected textbox selector."""
    if not isinstance(selector, dict) or len(selector) != 1:
        return None
    key, value = next(iter(selector.items()))
    if key == "index":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return key, value
    if key == "path":
        if (
            not isinstance(value, list)
            or not value
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0
                for item in value
            )
        ):
            return None
        return key, tuple(value)
    # Name, kind, and text are useful search hints, but are not stable enough
    # to bridge the two canonical structural identities here.
    return None


def _textbox_plan_shape(state: Any, step: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the one initial observed shape represented by a textbox step."""
    expected = step.get("arguments")
    if not isinstance(expected, dict):
        return None
    slide_index = slide_index_from_reference(expected, allow_consistent_pair=True)
    expected_selector = _single_textbox_selector(expected.get("selector"))
    if slide_index is None or expected_selector is None:
        return None
    initial = state.initial_presentation_context_hint()
    slides = initial.get("slides") if isinstance(initial, dict) else None
    if not isinstance(slides, list):
        return None
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == slide_index
        ),
        None,
    )
    if not isinstance(slide, dict):
        return None
    collection = slide.get("recursive_text_shapes")
    if not isinstance(collection, list):
        collection = slide.get("text_shapes")
    if not isinstance(collection, list):
        return None
    key, value = expected_selector
    matches = [
        shape
        for shape in collection
        if isinstance(shape, dict)
        and shape.get(key) == (list(value) if key == "path" else value)
    ]
    return matches[0] if len(matches) == 1 else None


def _textbox_selector_matches_shape(
    selector: Any, shape: dict[str, Any] | None
) -> bool:
    """Accept index/path aliases only when they identify the observed shape."""
    identity = _single_textbox_selector(selector)
    if identity is None or not isinstance(shape, dict):
        return False
    key, value = identity
    if key == "path":
        return shape.get("path") == list(value)
    observed_index = shape.get("index")
    return (
        isinstance(observed_index, int)
        and not isinstance(observed_index, bool)
        and observed_index == value
    )


def _textbox_arguments_match(state: Any, observed: Any, step: dict[str, Any]) -> bool:
    """Match model arguments while normalizing slide and selector forms."""
    expected = step.get("arguments")
    if not isinstance(observed, dict) or not isinstance(expected, dict):
        return False
    if slide_index_from_reference(
        observed, allow_consistent_pair=True
    ) != slide_index_from_reference(expected, allow_consistent_pair=True):
        return False
    shape = _textbox_plan_shape(state, step)
    if shape is None:
        return False
    body_keys = (set(observed) | set(expected)) - {"slide", "slide_number", "selector"}
    if any(observed.get(key) != expected.get(key) for key in body_keys):
        return False
    return _textbox_selector_matches_shape(observed.get("selector"), shape)


def _textbox_step_event_matches(state: Any, event: Any, step: dict[str, Any]) -> bool:
    """Match a successful textbox mutation against an observed plan step."""
    return _textbox_arguments_match(state, event.proposed.get("arguments"), step)


def _role_underline_step_event_matches(
    state: Any, event: Any, step: dict[str, Any]
) -> bool:
    """Recognize the native role-format receipt for one observed textbox."""
    expected = step["arguments"]
    if not isinstance(expected.get("underline"), bool):
        return False
    arguments = event.proposed.get("arguments")
    requested_slides = (
        action_slide_indices(arguments) if isinstance(arguments, dict) else None
    )
    slide = expected.get("slide")
    shape = _textbox_plan_shape(state, step)
    if not requested_slides or slide not in requested_slides or shape is None:
        return False
    path = shape.get("path", [shape.get("index")])
    observed = None
    for result in iter_result_mappings(event.result):
        pages = [result] if "slide" in result else result.get("slides", [])
        if not isinstance(pages, list):
            continue
        for page in pages:
            if not isinstance(page, dict) or page.get("slide") != slide:
                continue
            for rule in page.get("rules", []):
                for formatted in rule.get("formatted", []):
                    properties = formatted.get("properties", {})
                    if formatted.get("path") == path and "CharUnderline" in properties:
                        # Later role overrides can change the same shape again.
                        observed = _is_underlined(properties["CharUnderline"])
    return observed is expected["underline"]


def _verified_edge_result_matches(
    event: Any,
    result: dict[str, Any],
    step: dict[str, Any],
    expected_edge: str,
) -> bool:
    """Match an edge-form call to its observation-derived numeric geometry.

    Edge mode deliberately leaves coordinate resolution to the Adapter.  Only
    an explicitly verified result containing the resolved slide geometry can
    establish that the model-selected edge call performed this planned
    mutation.  No arguments are synthesized or rewritten here.
    """
    arguments = event.proposed.get("arguments")
    expected = step.get("arguments")
    if not isinstance(arguments, dict) or not isinstance(expected, dict):
        return False
    if arguments.get("edge") != expected_edge:
        return False
    if any(
        field in arguments
        for field in (
            "x",
            "y",
            "width",
            "height",
            "width_measurement",
            "height_measurement",
        )
    ):
        return False
    expected_slide = slide_index_from_reference(expected, allow_consistent_pair=True)
    observed_slide = slide_index_from_reference(arguments, allow_consistent_pair=True)
    if expected_slide is None or observed_slide != expected_slide:
        return False
    if not _selector_argument_matches(
        arguments.get("selector"), expected.get("selector")
    ):
        return False

    geometry_fields = ("x", "y", "width", "height")
    if any(
        isinstance(expected.get(field), bool)
        or not isinstance(expected.get(field), int)
        for field in geometry_fields
    ):
        return False
    if result.get("edge") != expected_edge:
        return False
    result_slide = result.get("slide")
    display_slide = result.get("display_slide_number")
    slide_matches = (
        isinstance(result_slide, int)
        and not isinstance(result_slide, bool)
        and result_slide == expected_slide
    ) or (
        isinstance(display_slide, int)
        and not isinstance(display_slide, bool)
        and display_slide - 1 == expected_slide
    )
    if not slide_matches:
        return False
    if not (
        result.get("verification_passed") is True
        or (
            isinstance(result.get("verification"), dict)
            and result["verification"].get("passed") is True
        )
    ):
        return False
    for field in geometry_fields:
        observed = result.get(field)
        if isinstance(observed, bool) or not isinstance(observed, (int, float)):
            return False
        if isinstance(observed, float) and not math.isfinite(observed):
            return False
        if observed != expected[field]:
            return False
    return True


def _edge_arguments_match_plan(state: Any, arguments: Any) -> bool:
    """Validate a model-selected edge form against the observed target.

    The internal plan retains numeric geometry for read-back, while the public
    Adapter contract allows the model to request ``edge`` and let the Adapter
    resolve coordinates.  This predicate bridges those representations at the
    validation boundary without constructing a replacement argument mapping.
    """
    plan = picture_edge_plan(state)
    if plan is None or not isinstance(arguments, dict):
        return False
    pending = next_picture_edge_action(state)
    if pending is None or pending.get("action") != "shape.set_geometry":
        return False
    if arguments.get("edge") != plan["edge"]:
        return False
    if any(
        field in arguments
        for field in (
            "x",
            "y",
            "width",
            "height",
            "width_measurement",
            "height_measurement",
        )
    ):
        return False
    if (
        slide_index_from_reference(arguments, allow_consistent_pair=True)
        != plan["slide"]
    ):
        return False
    return arguments.get("selector") == plan["selector"]


def _matching_step_events(
    state: Any,
    step: dict[str, Any],
    *,
    expected_edge: str | None = None,
    allow_textbox_selector_aliases: bool = False,
) -> list[Any]:
    if step["action"] == "shape.set_geometry":
        matches = [
            event
            for event in state.successful_action_events(step["action"])
            if slide_referenced_arguments_equal(
                event.proposed.get("arguments"), step["arguments"]
            )
        ]
        if expected_edge is None:
            return matches
        for event in state.successful_action_events(step["action"]):
            if event in matches:
                continue
            if any(
                _verified_edge_result_matches(event, result, step, expected_edge)
                for result in iter_result_mappings(event.result)
            ):
                matches.append(event)
        return matches
    if allow_textbox_selector_aliases and step.get("action") == "shape.format_text":
        matches = [
            event
            for event in state.successful_action_events(step["action"])
            if _textbox_step_event_matches(state, event, step)
        ]
        matches.extend(
            event
            for action in ROLE_ACTIONS
            for event in state.successful_action_events(action)
            if _role_underline_step_event_matches(state, event, step)
        )
        return sorted(matches, key=lambda event: event.step)
    return [
        event
        for event in state.successful_action_events(step["action"])
        if event.proposed.get("arguments") == step["arguments"]
    ]


def _selector_matches_shape(
    selector: dict[str, Any], shape: dict[str, Any] | None
) -> bool:
    if not isinstance(shape, dict):
        return False
    if "path" in selector:
        return shape.get("path") == selector["path"]
    if "index" in selector:
        return shape.get("index") == selector["index"]
    return False


def _result_matches_picture_height_target(
    event: Any,
    result: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    arguments = event.proposed.get("arguments")
    if not isinstance(arguments, dict):
        return False
    echoed = result.get("arguments")
    echoed = echoed if isinstance(echoed, dict) else {}

    observed_slide = result.get("slide")
    if isinstance(observed_slide, int) and not isinstance(observed_slide, bool):
        if observed_slide != target["slide"]:
            return False
    observed_display_slide = result.get("display_slide_number")
    if isinstance(observed_display_slide, int) and not isinstance(
        observed_display_slide, bool
    ):
        if observed_display_slide - 1 != target["slide"]:
            return False
    if slide_index_from_reference(arguments) != target["slide"]:
        return False

    target_selector = target["selector"]
    selectors = [
        arguments.get("selector"),
        echoed.get("selector"),
        result.get("resolved_selector"),
        result.get("selector"),
    ]
    selector_matches = any(
        isinstance(selector, dict) and selector == target_selector
        for selector in selectors
    ) or _selector_matches_shape(target_selector, result)
    if not selector_matches:
        return False

    observed_height = result.get("height")
    geometry = result.get("resolved_geometry")
    if not isinstance(observed_height, (int, float)) or isinstance(
        observed_height, bool
    ):
        observed_height = geometry.get("height") if isinstance(geometry, dict) else None
    if not isinstance(observed_height, (int, float)) or isinstance(
        observed_height, bool
    ):
        observed_height = echoed.get("height")

    if not isinstance(observed_height, (int, float)) or isinstance(
        observed_height, bool
    ):
        observed_height = arguments.get("height")
    return bool(
        isinstance(observed_height, (int, float))
        and not isinstance(observed_height, bool)
        and abs(float(observed_height) - float(target["target_height"]))
        <= float(target["tolerance"])
    )


def _matching_picture_height_events(state: Any, target: dict[str, Any]) -> list[Any]:
    matches: list[Any] = []
    for event in state.successful_action_events("shape.set_geometry"):
        arguments = event.proposed.get("arguments")
        if not isinstance(arguments, dict):
            continue
        if slide_index_from_reference(arguments) != target["slide"]:
            continue
        if any(
            _result_matches_picture_height_target(event, result, target)
            for result in iter_result_mappings(event.result)
        ):
            matches.append(event)
    return matches


def _picture_height_observed(
    slides: list[dict[str, Any]], target: dict[str, Any]
) -> bool:
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == target["slide"]
        ),
        None,
    )
    if not isinstance(slide, dict):
        return False
    shape = _observed_shape(
        slide,
        target["selector"],
        ("picture_containers", "graphic_shapes", "all_shapes"),
    )
    return bool(
        isinstance(shape, dict)
        and isinstance(shape.get("height"), int)
        and abs(shape["height"] - target["target_height"]) <= target["tolerance"]
    )


def next_picture_height_action(state: Any) -> dict[str, Any] | None:
    if parse_picture_height_intent(state.instruction) is None:
        return None
    if not state.successful_action_events("presentation.inspect"):
        return {"action": "presentation.inspect", "arguments": {}}
    plan = picture_height_plan(state)
    if plan is None:
        return None
    mutations: list[Any] = []
    for target in plan["resolved_targets"]:
        if target["already_within_precision"]:
            continue
        matches = _matching_picture_height_events(state, target)
        if not matches:
            return target["step"]
        mutations.append(matches[-1])
    initial_inspection_step = state.successful_action_events("presentation.inspect")[
        0
    ].step
    after_step = (
        max(event.step for event in mutations) if mutations else initial_inspection_step
    )
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return None
    slides = _inspection_slides(readback)
    assert slides is not None
    for target in plan["resolved_targets"]:
        if _picture_height_observed(slides, target):
            continue
        if not any(
            event.step > readback.step
            for event in _matching_picture_height_events(state, target)
        ):
            return target["step"]
    return None


def picture_height_mutations_satisfied(state: Any) -> bool:
    return bool(
        picture_height_plan(state) is not None
        and next_picture_height_action(state) is None
    )


def satisfies_unexecuted_mutation(state: Any, action: str) -> bool:
    """Allow a semantic mutation to be a no-op when observed state already satisfies it."""
    if state.domain != "libreoffice_impress":
        return False
    if action == "shape.set_geometry":
        return bool(
            (
                parse_picture_height_intent(state.instruction) is not None
                and picture_height_mutations_satisfied(state)
            )
            or (
                parse_picture_edge_intent(state.instruction) is not None
                and picture_edge_mutations_satisfied(state)
            )
        )
    if action == "shape.format_text":
        return bool(
            (
                parse_textbox_color_sequence_intent(state.instruction) is not None
                and textbox_color_sequence_mutations_satisfied(state)
            )
            or (
                parse_textbox_underline_intent(state.instruction) is not None
                and textbox_underline_mutations_satisfied(state)
            )
        )
    return False


def picture_height_readback_satisfied(state: Any) -> bool:
    plan = picture_height_plan(state)
    if plan is None:
        return False
    mutations = []
    for target in plan["resolved_targets"]:
        if target["already_within_precision"]:
            continue
        matches = _matching_picture_height_events(state, target)
        if not matches:
            return False
        mutations.append(matches[-1])
    if len(mutations) != len(plan["steps"]):
        return False
    inspections = state.successful_action_events("presentation.inspect")
    if not inspections:
        return False
    after_step = (
        max(event.step for event in mutations) if mutations else inspections[0].step
    )
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return False
    slides = _inspection_slides(readback)
    return bool(
        slides is not None
        and all(
            _picture_height_observed(slides, target)
            for target in plan["resolved_targets"]
        )
    )


def picture_edge_plan(state: Any) -> dict[str, Any] | None:
    intent = parse_picture_edge_intent(state.instruction)
    initial = state.initial_presentation_context_hint()
    slides = initial.get("slides") if isinstance(initial, dict) else None
    if intent is None or not isinstance(slides, list):
        return None
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == intent.slide
        ),
        None,
    )
    if not isinstance(slide, dict):
        return None
    shape = _primary_picture(slide)
    if shape is None:
        return None
    geometry = {key: shape.get(key) for key in ("x", "y", "width", "height")}
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in geometry.values()
    ):
        return None
    if geometry["width"] <= 0 or geometry["height"] <= 0:
        return None
    slide_height = slide.get("height")
    if isinstance(slide_height, bool) or not isinstance(slide_height, int):
        return None
    target_y = 0 if intent.edge == "top" else slide_height - geometry["height"]
    if target_y < 0:
        return None
    selector = _shape_selector(shape)
    if selector is None:
        return None
    target_geometry = {**geometry, "y": target_y}
    step = {
        "action": "shape.set_geometry",
        "arguments": {
            "slide": intent.slide,
            "selector": selector,
            **target_geometry,
        },
    }
    already_at_edge = geometry == target_geometry
    return {
        **intent.as_request(),
        "selector": selector,
        "shape_name": shape.get("name"),
        "shape_kind": shape.get("kind"),
        "source_geometry": geometry,
        "target_geometry": target_geometry,
        "already_at_edge": already_at_edge,
        "step": step,
        "steps": [] if already_at_edge else [step],
    }


def _picture_edge_observed(slides: list[dict[str, Any]], plan: dict[str, Any]) -> bool:
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == plan["slide"]
        ),
        None,
    )
    if not isinstance(slide, dict):
        return False
    shape = _observed_shape(
        slide,
        plan["selector"],
        ("picture_containers", "graphic_shapes", "all_shapes"),
    )
    return bool(
        isinstance(shape, dict)
        and all(
            shape.get(key) == value for key, value in plan["target_geometry"].items()
        )
    )


def next_picture_edge_action(state: Any) -> dict[str, Any] | None:
    if parse_picture_edge_intent(state.instruction) is None:
        return None
    inspections = state.successful_action_events("presentation.inspect")
    if not inspections:
        return {"action": "presentation.inspect", "arguments": {}}
    plan = picture_edge_plan(state)
    if plan is None:
        return None
    matches = _matching_step_events(state, plan["step"], expected_edge=plan["edge"])
    if plan["steps"] and not matches:
        return plan["step"]
    after_step = matches[-1].step if matches else inspections[0].step
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return None
    slides = _inspection_slides(readback)
    assert slides is not None
    if not any(slide.get("slide") == plan["slide"] for slide in slides):
        return None
    if _picture_edge_observed(slides, plan):
        return None
    if not any(event.step > readback.step for event in matches):
        return plan["step"]
    return None


def picture_edge_mutations_satisfied(state: Any) -> bool:
    plan = picture_edge_plan(state)
    return bool(plan is not None and next_picture_edge_action(state) is None)


def picture_edge_readback_satisfied(state: Any) -> bool:
    plan = picture_edge_plan(state)
    inspections = state.successful_action_events("presentation.inspect")
    if plan is None or not inspections:
        return False
    matches = _matching_step_events(state, plan["step"], expected_edge=plan["edge"])
    if plan["steps"] and not matches:
        return False
    after_step = matches[-1].step if matches else inspections[0].step
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return False
    slides = _inspection_slides(readback)
    return bool(slides is not None and _picture_edge_observed(slides, plan))


def _is_underlined(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return str(value or "").strip().casefold() not in {"", "0", "false", "none", "off"}


def textbox_underline_plan(state: Any) -> dict[str, Any] | None:
    intent = parse_textbox_underline_intent(state.instruction)
    initial = state.initial_presentation_context_hint()
    slides = initial.get("slides") if isinstance(initial, dict) else None
    if intent is None or not isinstance(slides, list):
        return None
    targets: list[dict[str, Any]] = []
    seen: set[tuple[int, str, Any]] = set()
    for slide_index in intent.slides:
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == slide_index
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        collection = slide.get("recursive_text_shapes")
        if not isinstance(collection, list):
            collection = slide.get("text_shapes")
        if not isinstance(collection, list):
            return None
        slide_targets = 0
        for shape in collection:
            if not isinstance(shape, dict) or not any(
                str(line).strip() for line in shape.get("lines", [])
            ):
                continue
            selector = _shape_selector(shape)
            if selector is None:
                continue
            key_name, key_value = next(iter(selector.items()))
            key = (
                slide_index,
                key_name,
                tuple(key_value) if isinstance(key_value, list) else key_value,
            )
            if key in seen:
                continue
            seen.add(key)
            style = shape.get("text_style")
            observed = style.get("underline") if isinstance(style, dict) else None
            step = {
                "action": "shape.format_text",
                "arguments": {
                    "slide": slide_index,
                    "selector": selector,
                    "underline": intent.underline,
                },
            }
            targets.append(
                {
                    "slide": slide_index,
                    "selector": selector,
                    "shape_name": shape.get("name"),
                    "underline": intent.underline,
                    "already_satisfied": _is_underlined(observed) is intent.underline,
                    "step": step,
                }
            )
            slide_targets += 1
        if slide_targets == 0:
            return None
    for sequence, target in enumerate(targets, start=1):
        target["sequence"] = sequence
        target["required"] = len(targets)
    return {
        **intent.as_request(),
        "resolved_targets": targets,
        "steps": [
            target["step"] for target in targets if not target["already_satisfied"]
        ],
    }


def _textbox_underline_observed(
    slides: list[dict[str, Any]], target: dict[str, Any]
) -> bool:
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == target["slide"]
        ),
        None,
    )
    if not isinstance(slide, dict):
        return False
    shape = _observed_shape(
        slide,
        target["selector"],
        ("recursive_text_shapes", "text_shapes", "all_shapes"),
    )
    style = shape.get("text_style") if isinstance(shape, dict) else None
    observed = style.get("underline") if isinstance(style, dict) else None
    return _is_underlined(observed) is target["underline"]


def next_textbox_underline_spec(state: Any) -> dict[str, Any] | None:
    if parse_textbox_underline_intent(state.instruction) is None:
        return None
    inspections = state.successful_action_events("presentation.inspect")
    if not inspections:
        return None
    plan = textbox_underline_plan(state)
    if plan is None:
        return None
    mutations: list[Any] = []
    for target in plan["resolved_targets"]:
        matches = _matching_step_events(
            state, target["step"], allow_textbox_selector_aliases=True
        )
        if not target["already_satisfied"] and not matches:
            return target
        if matches:
            mutations.append(matches[-1])
    after_step = max((event.step for event in mutations), default=inspections[0].step)
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return None
    slides = _inspection_slides(readback)
    assert slides is not None
    for target in plan["resolved_targets"]:
        if not any(slide.get("slide") == target["slide"] for slide in slides):
            continue
        if _textbox_underline_observed(slides, target):
            continue
        matches = _matching_step_events(
            state, target["step"], allow_textbox_selector_aliases=True
        )
        if not any(event.step > readback.step for event in matches):
            return target
    return None


def textbox_underline_mutations_satisfied(state: Any) -> bool:
    plan = textbox_underline_plan(state)
    return bool(plan is not None and next_textbox_underline_spec(state) is None)


def textbox_underline_readback_satisfied(state: Any) -> bool:
    plan = textbox_underline_plan(state)
    inspections = state.successful_action_events("presentation.inspect")
    if plan is None or not inspections:
        return False
    mutations = [
        matches[-1]
        for target in plan["resolved_targets"]
        if (
            matches := _matching_step_events(
                state, target["step"], allow_textbox_selector_aliases=True
            )
        )
    ]
    if any(
        not target["already_satisfied"]
        and not _matching_step_events(
            state, target["step"], allow_textbox_selector_aliases=True
        )
        for target in plan["resolved_targets"]
    ):
        return False
    after_step = max((event.step for event in mutations), default=inspections[0].step)
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return False
    slides = _inspection_slides(readback)
    return bool(
        slides is not None
        and all(
            _textbox_underline_observed(slides, target)
            for target in plan["resolved_targets"]
        )
    )


def _impress_color_value(value: str) -> int | None:
    normalized = normalize_impress_color(value)
    return int(normalized[1:], 16) if normalized is not None else None


def _ordered_textbox_shapes(
    slide: dict[str, Any], order: str
) -> list[dict[str, Any]] | None:
    collection = slide.get("recursive_text_shapes")
    if not isinstance(collection, list):
        collection = slide.get("text_shapes")
    if not isinstance(collection, list):
        return None
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()
    for shape in collection:
        if (
            not isinstance(shape, dict)
            or _shape_selector(shape) is None
            or not any(str(line).strip() for line in shape.get("lines", []))
        ):
            continue
        x, y = shape.get("x"), shape.get("y")
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in (x, y)
        ):
            return None
        selector = _shape_selector(shape)
        assert selector is not None
        key_name, key_value = next(iter(selector.items()))
        key = (key_name, tuple(key_value) if isinstance(key_value, list) else key_value)
        if key not in seen:
            unique.append(shape)
            seen.add(key)
    return order_shapes_by_position(unique, order)


def textbox_color_sequence_plan(state: Any) -> dict[str, Any] | None:
    intent = parse_textbox_color_sequence_intent(state.instruction)
    initial = state.initial_presentation_context_hint()
    slides = initial.get("slides") if isinstance(initial, dict) else None
    if intent is None or not isinstance(slides, list):
        return None
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == intent.slide
        ),
        None,
    )
    if not isinstance(slide, dict):
        return None
    ordered = _ordered_textbox_shapes(slide, intent.order)
    if ordered is None or len(ordered) != len(intent.colors):
        return None
    targets: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    for sequence, (shape, color) in enumerate(
        zip(ordered, intent.colors, strict=True), start=1
    ):
        expected_color = _impress_color_value(color)
        selector = _shape_selector(shape)
        if expected_color is None or selector is None:
            return None
        style = shape.get("text_style")
        observed_color = style.get("color") if isinstance(style, dict) else None
        step = {
            "action": "shape.format_text",
            "arguments": {
                "slide": intent.slide,
                "selector": selector,
                "color": color,
            },
        }
        target = {
            "sequence": sequence,
            "required": len(ordered),
            "scope": "nonempty_textboxes",
            "order": intent.order,
            "slide": intent.slide,
            "selector": selector,
            "shape_name": shape.get("name"),
            "color": color,
            "expected_color": expected_color,
            "already_satisfied": observed_color == expected_color,
            "step": step,
        }
        targets.append(target)
        if not target["already_satisfied"]:
            steps.append(step)
    return {
        **intent.as_request(),
        "resolved_targets": targets,
        "steps": steps,
    }


def _textbox_color_sequence_observed(
    slides: list[dict[str, Any]], target: dict[str, Any]
) -> bool:
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == target["slide"]
        ),
        None,
    )
    if not isinstance(slide, dict):
        return False
    shape = _observed_shape(
        slide,
        target["selector"],
        ("recursive_text_shapes", "text_shapes", "all_shapes"),
    )
    style = shape.get("text_style") if isinstance(shape, dict) else None
    return bool(
        isinstance(style, dict) and style.get("color") == target["expected_color"]
    )


def next_textbox_color_sequence_spec(state: Any) -> dict[str, Any] | None:
    if parse_textbox_color_sequence_intent(state.instruction) is None:
        return None
    inspections = state.successful_action_events("presentation.inspect")
    if not inspections:
        return None
    plan = textbox_color_sequence_plan(state)
    if plan is None:
        return None
    mutations: list[Any] = []
    for target in plan["resolved_targets"]:
        matches = _matching_step_events(state, target["step"])
        if not target["already_satisfied"] and not matches:
            return target
        if matches:
            mutations.append(matches[-1])
    after_step = max((event.step for event in mutations), default=inspections[0].step)
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return None
    slides = _inspection_slides(readback)
    assert slides is not None
    for target in plan["resolved_targets"]:
        if _textbox_color_sequence_observed(slides, target):
            continue
        matches = _matching_step_events(state, target["step"])
        if not any(event.step > readback.step for event in matches):
            return target
    return None


def textbox_color_sequence_mutations_satisfied(state: Any) -> bool:
    plan = textbox_color_sequence_plan(state)
    return bool(plan is not None and next_textbox_color_sequence_spec(state) is None)


def textbox_color_sequence_readback_satisfied(state: Any) -> bool:
    plan = textbox_color_sequence_plan(state)
    inspections = state.successful_action_events("presentation.inspect")
    if plan is None or not inspections:
        return False
    mutations = [
        matches[-1]
        for target in plan["resolved_targets"]
        if (matches := _matching_step_events(state, target["step"]))
    ]
    if any(
        not target["already_satisfied"]
        and not _matching_step_events(state, target["step"])
        for target in plan["resolved_targets"]
    ):
        return False
    after_step = max((event.step for event in mutations), default=inspections[0].step)
    readback = _latest_post_save_inspection(state, after_step)
    if readback is None:
        return False
    slides = _inspection_slides(readback)
    return bool(
        slides is not None
        and all(
            _textbox_color_sequence_observed(slides, target)
            for target in plan["resolved_targets"]
        )
    )


def textbox_font_size_plan(state: Any) -> dict[str, Any] | None:
    intent = parse_textbox_font_size_intent(state.instruction)
    initial = state.initial_presentation_context_hint()
    slides = initial.get("slides") if isinstance(initial, dict) else None
    if intent is None or not isinstance(slides, list):
        return None
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == intent.slide
        ),
        None,
    )
    if not isinstance(slide, dict):
        return None
    collection_name = "text_shapes"
    if intent.scope == "all" and isinstance(slide.get("recursive_text_shapes"), list):
        collection_name = "recursive_text_shapes"
    observed = [
        shape
        for shape in slide.get(collection_name, [])
        if isinstance(shape, dict)
        and _shape_selector(shape) is not None
        and any(str(line).strip() for line in shape.get("lines", []))
    ]
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()
    for shape in observed:
        selector = _shape_selector(shape)
        assert selector is not None
        key_name, key_value = next(iter(selector.items()))
        key = (key_name, tuple(key_value) if isinstance(key_value, list) else key_value)
        if key not in seen:
            unique.append(shape)
            seen.add(key)
    if intent.scope == "ordered":
        if len(unique) < len(intent.sizes):
            return None
        assignments = list(zip(unique[: len(intent.sizes)], intent.sizes, strict=True))
    else:
        if not unique:
            return None
        assignments = [(shape, intent.sizes[0]) for shape in unique]
    targets: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    for sequence, (shape, font_size) in enumerate(assignments, start=1):
        selector = _shape_selector(shape)
        assert selector is not None
        target = {
            "sequence": sequence,
            "required": len(assignments),
            "scope": intent.scope,
            "slide": intent.slide,
            "selector": selector,
            "shape_name": shape.get("name"),
            "font_size": font_size,
        }
        targets.append(target)
        steps.append(
            {
                "action": "shape.format_text",
                "arguments": {
                    "slide": intent.slide,
                    "selector": selector,
                    "font_size": font_size,
                },
            }
        )
    return {
        **intent.as_request(),
        "resolved_targets": targets,
        "steps": steps,
    }


def _textbox_font_size_observed(
    slides: list[dict[str, Any]], target: dict[str, Any]
) -> bool:
    slide = next(
        (
            item
            for item in slides
            if isinstance(item, dict) and item.get("slide") == target["slide"]
        ),
        None,
    )
    if not isinstance(slide, dict):
        return False
    shape = _observed_shape(
        slide,
        target["selector"],
        ("recursive_text_shapes", "text_shapes", "all_shapes"),
    )
    style = shape.get("text_style") if isinstance(shape, dict) else None
    observed = style.get("font_size") if isinstance(style, dict) else None
    return bool(
        isinstance(observed, (int, float))
        and not isinstance(observed, bool)
        and abs(float(observed) - float(target["font_size"])) < 1e-6
    )


def _all_textbox_role_arguments(intent: TextBoxFontSizeIntent) -> dict[str, Any]:
    return {
        "slide": intent.slide,
        "roles": ["all"],
        "font_size": intent.sizes[0],
    }


def _matching_all_textbox_role_mutation(state: Any) -> Any | None:
    intent = parse_textbox_font_size_intent(state.instruction)
    if intent is None or intent.scope != "all":
        return None
    expected = _all_textbox_role_arguments(intent)
    return next(
        (
            event
            for event in reversed(
                state.successful_action_events("slide.format_text_roles")
            )
            if event.proposed.get("arguments") == expected
        ),
        None,
    )


def next_textbox_font_size_spec(state: Any) -> dict[str, Any] | None:
    intent = parse_textbox_font_size_intent(state.instruction)
    if intent is None:
        return None
    plan = textbox_font_size_plan(state)
    if plan is None:
        return None
    mutations: list[Any] = []
    for target, step in zip(plan["resolved_targets"], plan["steps"], strict=True):
        matches = _matching_step_events(state, step)
        if not matches:
            return target
        mutations.append(matches[-1])
    readback = _latest_post_save_inspection(
        state, max(event.step for event in mutations)
    )
    if readback is None:
        return None
    slides = _inspection_slides(readback)
    assert slides is not None
    for target, step in zip(plan["resolved_targets"], plan["steps"], strict=True):
        if _textbox_font_size_observed(slides, target):
            continue
        if not any(
            event.step > readback.step for event in _matching_step_events(state, step)
        ):
            return target
    return None


def textbox_font_size_mutations_satisfied(state: Any) -> bool:
    plan = textbox_font_size_plan(state)
    intent = parse_textbox_font_size_intent(state.instruction)
    if (
        intent is not None
        and intent.scope == "all"
        and _matching_all_textbox_role_mutation(state) is not None
    ):
        return plan is not None
    return bool(plan is not None and next_textbox_font_size_spec(state) is None)


def textbox_font_size_readback_satisfied(state: Any) -> bool:
    plan = textbox_font_size_plan(state)
    if plan is None:
        return False
    intent = parse_textbox_font_size_intent(state.instruction)
    if (
        intent is not None
        and intent.scope == "all"
        and _matching_all_textbox_role_mutation(state) is not None
    ):
        mutation = _matching_all_textbox_role_mutation(state)
        assert mutation is not None
        mutations = [mutation]
    else:
        mutations = [
            matches[-1]
            for step in plan["steps"]
            if (matches := _matching_step_events(state, step))
        ]
        if len(mutations) != len(plan["steps"]):
            return False
    readback = _latest_post_save_inspection(
        state, max(event.step for event in mutations)
    )
    if readback is None:
        return False
    slides = _inspection_slides(readback)
    return bool(
        slides is not None
        and all(
            _textbox_font_size_observed(slides, target)
            for target in plan["resolved_targets"]
        )
    )


def _matching_title_note_mutation(state: Any) -> Any | None:
    expected = title_note_arguments(state)
    if expected is None:
        return None
    return next(
        (
            event
            for event in reversed(state.successful_action_events("slide.set_notes"))
            if event.proposed.get("arguments") == expected
        ),
        None,
    )


def title_note_readback_satisfied(state: Any) -> bool:
    expected = title_note_arguments(state)
    mutation = _matching_title_note_mutation(state)
    if expected is None or mutation is None:
        return False
    saves = [
        event
        for event in state.successful_adapter_events()
        if action_is_save(str(event.proposed.get("action", "")))
        and event.step > mutation.step
    ]
    if not saves:
        return False
    for event in reversed(state.successful_action_events("presentation.inspect")):
        if event.step <= saves[-1].step:
            continue
        slides = _inspection_slides(event)
        if slides is None:
            continue
        observed = next(
            (slide for slide in slides if slide.get("slide") == expected["slide"]),
            None,
        )
        return bool(observed is not None and observed.get("notes") == expected["text"])
    return False


def _next_title_note_action(state: Any) -> str | None:
    intent = parse_note_intent(state.instruction)
    if intent is None or not intent.copies_title:
        return None
    if title_note_arguments(state) is None:
        return "presentation.inspect"
    mutation = _matching_title_note_mutation(state)
    if mutation is None:
        pending_other_mutations = {
            action
            for action in state.required_mutation_actions()
            if action != "slide.set_notes"
            and not state.successful_action_events(action)
        }
        if pending_other_mutations:
            return None
        return "slide.set_notes"
    saves = [
        event
        for event in state.successful_adapter_events()
        if action_is_save(str(event.proposed.get("action", "")))
        and event.step > mutation.step
    ]
    has_post_save_readback = bool(
        saves
        and any(
            event.step > saves[-1].step
            for event in state.successful_action_events("presentation.inspect")
        )
    )
    if has_post_save_readback and not title_note_readback_satisfied(state):
        return "slide.set_notes"
    return None


def _next_picture_height_action_name(state: Any) -> str | None:
    step = next_picture_height_action(state)
    return str(step["action"]) if step is not None else None


def _next_textbox_font_size_action(state: Any) -> str | None:
    intent = parse_textbox_font_size_intent(state.instruction)
    if intent is None:
        return None
    if intent.scope == "all":
        role_mutation = _matching_all_textbox_role_mutation(state)
        legacy_shape_mutations_complete = bool(
            textbox_font_size_plan(state) is not None
            and next_textbox_font_size_spec(state) is None
        )
        return (
            None
            if role_mutation is not None or legacy_shape_mutations_complete
            else "slide.format_text_roles"
        )
    if not state.successful_action_events("presentation.inspect"):
        return "presentation.inspect"
    return (
        "shape.format_text" if next_textbox_font_size_spec(state) is not None else None
    )


def _next_textbox_color_sequence_action(state: Any) -> str | None:
    if parse_textbox_color_sequence_intent(state.instruction) is None:
        return None
    if not state.successful_action_events("presentation.inspect"):
        return "presentation.inspect"
    return (
        "shape.format_text"
        if next_textbox_color_sequence_spec(state) is not None
        else None
    )


def _next_picture_edge_action_name(state: Any) -> str | None:
    step = next_picture_edge_action(state)
    return str(step["action"]) if step is not None else None


def _next_textbox_underline_action(state: Any) -> str | None:
    if parse_textbox_underline_intent(state.instruction) is None:
        return None
    if not state.successful_action_events("presentation.inspect"):
        return "presentation.inspect"
    return (
        "shape.format_text" if next_textbox_underline_spec(state) is not None else None
    )


def next_structured_action(state: Any) -> dict[str, Any] | None:
    """Return a model-callable step whose arguments are fully observation-derived."""
    if next_picture_height_action(state) is not None:
        return None
    if edge_step := next_picture_edge_action(state):
        return edge_step
    underline = next_textbox_underline_spec(state)
    return underline["step"] if underline is not None else None


def next_action(state: Any) -> str | None:
    return (
        _next_picture_height_action_name(state)
        or _next_picture_edge_action_name(state)
        or _next_textbox_underline_action(state)
    )


def stage_actions(
    state: Any, actions: list[str], *, prefer_role_api: bool = False
) -> list[str]:
    pending = next_action(state)
    if (
        pending == "slide.format_text_roles"
        and not prefer_role_api
        and "shape.format_text" in actions
    ):
        pending = "shape.format_text"
    if pending is None:
        return actions
    # Pending edits still need fresh observations of their targets.
    return [action for action in actions if action in {pending, "presentation.inspect"}]


def filter_tools(
    state: Any, tools: list[dict[str, Any]], *, prefer_role_api: bool = False
) -> list[dict[str, Any]]:
    pending = next_action(state)
    if pending is None:
        return tools
    name = "adapter__" + pending.replace(".", "_")
    available_names = {tool["function"]["name"] for tool in tools}
    if (
        pending == "slide.format_text_roles"
        and "adapter__shape_format_text" in available_names
    ):
        name = "adapter__shape_format_text"
    return [
        tool
        for tool in tools
        if tool["function"]["name"] in {name, "adapter__presentation_inspect"}
    ]


def constrain_tool_schema(
    function: dict[str, Any], state: Any, *, prefer_role_api: bool = False
) -> None:
    name = function.get("name")
    structured = next_structured_action(state)
    if (
        structured is not None
        and structured["action"] in {"shape.set_geometry", "shape.format_text"}
        and name == "adapter__" + structured["action"].replace(".", "_")
    ):
        function["parameters"] = {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
        function["description"] += (
            " Execute the next instruction- and structural-observation-derived step. "
            "Call with no arguments; the Runner injects and logs the exact generic action "
            f"arguments {structured['arguments']!r}."
        )
        return


def validate_arguments(
    state: Any,
    action: str,
    arguments: dict[str, Any],
) -> bool:
    structured = next_structured_action(state)
    structured_actions = {
        "presentation.inspect",
        "shape.set_geometry",
        "shape.format_text",
    }
    if structured is not None and action in structured_actions:
        if action == "shape.set_geometry" and _edge_arguments_match_plan(
            state, arguments
        ):
            return True
        if (
            action == "shape.format_text"
            and "underline" in structured.get("arguments", {})
            and _textbox_arguments_match(state, arguments, structured)
        ):
            return True
        if action != structured["action"] or arguments != structured["arguments"]:
            raise ValueError(
                "Impress semantic action must match the next instruction- and "
                f"structural-observation-derived step: {structured!r}"
            )
        return True
    new_intent_present = bool(
        parse_picture_edge_intent(state.instruction) is not None
        or parse_textbox_underline_intent(state.instruction) is not None
    )
    if action == "presentation.inspect" and new_intent_present:
        if arguments:
            raise ValueError("presentation.inspect takes no arguments")
        if (
            picture_edge_plan(state) is not None
            or textbox_underline_plan(state) is not None
        ):
            return True
    if (
        parse_picture_height_intent(state.instruction) is not None
        and action == "presentation.inspect"
    ):
        if arguments:
            raise ValueError("presentation.inspect takes no arguments")
        return True
    return False


def completion_missing(state: Any) -> list[str]:
    if state.domain != "libreoffice_impress":
        return []
    missing: list[str] = []
    picture_intent = parse_picture_height_intent(state.instruction)
    if picture_intent is not None:
        plan = picture_height_plan(state)
        next_step = next_picture_height_action(state)
        if plan is None:
            missing.append(
                "inspect each requested slide and resolve its largest picture-like visual shape"
            )
        elif next_step is not None:
            missing.append(
                "set each requested picture to its physical height with a model-selected "
                "shape selector and measurement; do not convert mm, cm, or inches into "
                "LibreOffice internal units"
            )
        elif not picture_height_readback_satisfied(state):
            missing.append(
                "after changing picture height, save and run presentation.inspect; every "
                "target visual shape must have its exact requested height"
            )

    edge_intent = parse_picture_edge_intent(state.instruction)
    if edge_intent is not None:
        plan = picture_edge_plan(state)
        next_step = next_picture_edge_action(state)
        if plan is None:
            missing.append(
                "inspect the requested slide and resolve its primary picture from structural "
                "picture containers"
            )
        elif next_step is not None:
            missing.append(
                "move the observation-derived picture to the requested vertical edge while "
                f"preserving its size and horizontal position; next exact step: {next_step!r}"
            )
        elif not picture_edge_readback_satisfied(state):
            missing.append(
                "after moving the picture, save and run presentation.inspect; its exact "
                f"observation-derived geometry must place it at the {edge_intent.edge} edge"
            )

    underline_intent = parse_textbox_underline_intent(state.instruction)
    if underline_intent is not None:
        plan = textbox_underline_plan(state)
        next_spec = next_textbox_underline_spec(state)
        if plan is None:
            missing.append(
                "inspect every requested slide and resolve all nonempty text boxes from the "
                "recursive presentation structure"
            )
        elif next_spec is not None:
            missing.append(
                "apply the requested underline state to every observation-derived text box; "
                f"next target is {next_spec['sequence']} of {next_spec['required']}"
            )
        elif not textbox_underline_readback_satisfied(state):
            missing.append(
                "after formatting all text boxes, save and run presentation.inspect; every "
                "observation-derived target must report the requested underline state"
            )

    return missing
