"""Semantic routing and evidence for Impress automatic page-number fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .impress_colors import IMPRESS_NAMED_COLORS, normalize_impress_color


ACTION = "master.set_page_number"

_FIELD_RE = re.compile(
    r"(?i)\b(?:(?:slide|page)[\s-]+(?:number(?:s|ing)?|numerals?)|"
    r"(?:number(?:s|ing)?|numerals?)[\s-]+(?:on|for)[\s-]+"
    r"(?:the[\s-]+)?(?:slide|page)s?)\b"
)
_MUTATION_RE = re.compile(
    r"(?i)\b(?:apply|change|disable|display|enable|format|hide|make|remove|"
    r"restore|reveal|set|show|turn|use)\b|\b(?:must|needs?\s+to|should)\s+be\b"
)
_ORDINAL_SUFFIX_RE = re.compile(r"(?i)^\s*(?:#\s*)?[1-9][0-9]*\b")
_SLIDE_TARGET_RE = re.compile(
    r"(?i)\b(?:slide|page)[\s-]*(?:number[\s-]*)?(?:#\s*)?[1-9][0-9]*\b"
)
_HIDE_RE = re.compile(
    r"(?is)(?:\b(?:hide|remove|disable)\b|\bturn\s+off\b|"
    r"\bmake\b.{0,30}\b(?:invisible|hidden)\b|\bshould\s+not\s+be\s+visible\b)"
)
_SHOW_RE = re.compile(
    r"(?is)(?:\b(?:show|display|enable|restore|reveal)\b|\bturn\s+on\b|"
    r"\bmake\b.{0,100}\bvisible\b|\bshould\s+be\s+visible\b)"
)
_COLOR_NAMES = "|".join(
    sorted((re.escape(name) for name in IMPRESS_NAMED_COLORS), key=len, reverse=True)
)
_COLOR_RE = re.compile(rf"(?i)#[0-9a-f]{{6}}\b|\b(?:{_COLOR_NAMES})\b")


@dataclass(frozen=True)
class PageNumberIntent:
    """Requested appearance of the automatic field, never a slide ordinal."""

    color: str | None
    visible: bool | None


def _field_matches(instruction: str) -> list[re.Match[str]]:
    return [
        match
        for match in _FIELD_RE.finditer(instruction)
        if _ORDINAL_SUFFIX_RE.match(instruction[match.end() :]) is None
    ]


def _near_field(
    instruction: str, matches: Iterable[re.Match[str]], radius: int = 100
) -> str:
    return " ".join(
        instruction[max(0, match.start() - radius) : match.end() + radius]
        for match in matches
    )


def parse_page_number_intent(instruction: str) -> PageNumberIntent | None:
    """Parse a requested automatic-number-field mutation from public language."""
    if _SLIDE_TARGET_RE.search(instruction) is not None:
        return None
    matches = _field_matches(instruction)
    if not matches:
        return None
    nearby = _near_field(instruction, matches)
    if _MUTATION_RE.search(nearby) is None:
        return None

    colors = {
        normalized
        for match in _COLOR_RE.finditer(nearby)
        if (normalized := normalize_impress_color(match.group(0))) is not None
    }
    color = colors.pop() if len(colors) == 1 else None

    hide = _HIDE_RE.search(nearby) is not None
    show = _SHOW_RE.search(nearby) is not None
    visible = False if hide and not show else True if show and not hide else None
    if color is None and visible is None:
        return None
    return PageNumberIntent(color=color, visible=visible)


def references_page_number_field(text: str) -> bool:
    """Return whether text names the automatic field rather than a slide ordinal."""
    return bool(_field_matches(text))


def suppress_page_number_action(text: str) -> bool:
    """Exclude the field tool from clear ordinal/count-only presentation requests."""
    ordinal = re.search(
        r"(?i)\b(?:slide|page)[\s-]+(?:number[\s-]+)?[1-9][0-9]*\b", text
    )
    page_count = re.search(r"(?i)\b(?:page|slide)[\s-]+count\b", text)
    return bool((ordinal or page_count) and not references_page_number_field(text))


def search_relevance_bonus(action: str, query: str) -> int:
    """Prioritize the exact automatic-field contract in free-form catalog search."""
    return 1_000 if action == ACTION and references_page_number_field(query) else 0


def required_actions(domain: str, instruction: str) -> list[str]:
    if domain != "libreoffice_impress":
        return []
    return [ACTION] if parse_page_number_intent(instruction) is not None else []


def page_number_argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Validate model-selected field settings without deriving or rewriting them."""
    if action != ACTION:
        return []
    intent = parse_page_number_intent(str(state.instruction))
    if intent is None:
        return []
    if (
        intent.color is not None
        and normalize_impress_color(arguments.get("color")) != intent.color
    ):
        return [
            "master.set_page_number color must match the page-number field color "
            "explicitly requested by the instruction"
        ]
    if intent.color is None and "color" in arguments:
        return [
            "the instruction does not request a page-number color change; omit color"
        ]
    if intent.visible is not None and arguments.get("visible") is not intent.visible:
        return [
            "master.set_page_number visible must match whether the instruction asks to "
            "show or hide the automatic page-number field"
        ]
    if intent.visible is None and arguments.get("visible") is False:
        return [
            "the instruction does not ask to hide page numbers; visible=false would make "
            "an unrelated destructive change"
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


def _confirmed_result(event: Any, state: Any) -> bool:
    arguments = event.proposed.get("arguments")
    if not isinstance(arguments, dict) or page_number_argument_contract_errors(
        state, ACTION, arguments
    ):
        return False
    candidates = [
        candidate
        for candidate in _mappings(event.result)
        if candidate.get("found") is True and isinstance(candidate.get("masters"), list)
    ]
    if not candidates:
        return False
    for candidate in candidates:
        masters = candidate["masters"]
        if not masters or not all(isinstance(item, dict) for item in masters):
            continue
        if "master" in arguments and not all(
            item.get("master") == arguments["master"] for item in masters
        ):
            continue
        if "color" in arguments and not all(
            normalize_impress_color(item.get("color"))
            == normalize_impress_color(arguments["color"])
            for item in masters
        ):
            continue
        if "visible" in arguments and not all(
            item.get("visible") is arguments["visible"] for item in masters
        ):
            continue
        return True
    return False


def page_number_requirement_errors(state: Any) -> list[str]:
    """Require an Adapter-confirmed mutation selected entirely by the model."""
    if parse_page_number_intent(str(state.instruction)) is None:
        return []
    if any(
        _confirmed_result(event, state)
        for event in state.successful_action_events(ACTION)
    ):
        return []
    return [
        "master.set_page_number lacks Adapter-confirmed coverage for the requested "
        "automatic page-number color or visibility"
    ]


__all__ = [
    "ACTION",
    "PageNumberIntent",
    "page_number_argument_contract_errors",
    "page_number_requirement_errors",
    "parse_page_number_intent",
    "references_page_number_field",
    "required_actions",
    "search_relevance_bonus",
    "suppress_page_number_action",
]
