"""Strict generic contracts for semantic role formatting across multiple slides."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .impress_colors import IMPRESS_NAMED_COLORS, normalize_impress_color


ACTION = "slides.format_text_roles"
SINGLE_ACTION = "slide.format_text_roles"
ROLE_ACTIONS = (ACTION, SINGLE_ACTION)
_STYLE_FIELDS = frozenset({"color", "bold", "italic", "underline", "strike"})
_CLAUSE_BOUNDARY_RE = re.compile(
    r"(?i)(?:[.!?;]+\s*|\b(?:also|additionally|afterwards|then)\b[,:]?\s*)"
)


@dataclass(frozen=True)
class MultiSlideRoleFormatIntent:
    slides: tuple[int, ...]
    roles: tuple[str, ...]
    properties: dict[str, Any]


def _listed_slides(text: str) -> tuple[int, ...]:
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
        values.update(int(value) for value in re.findall(r"\d+", spec))
        for start, end in re.findall(r"(?i)(\d+)\s*(?:-|to|through)\s*(\d+)", spec):
            first, last = int(start), int(end)
            if first >= 1 and last >= first:
                values.update(range(first, last + 1))
    return tuple(value - 1 for value in sorted(values) if value >= 1)


def _title_format_scope(instruction: str) -> str:
    """Keep unrelated operation clauses from contributing slide references."""
    clauses = [part.strip() for part in _CLAUSE_BOUNDARY_RE.split(instruction)]
    candidates = [
        clause
        for clause in clauses
        if re.search(r"(?i)\b(?:titles?|headings?)\b", clause)
        and re.search(r"(?i)\b(?:slides?|pages?)\b", clause)
    ]
    return candidates[0] if len(candidates) == 1 else instruction


def _instruction_color(text: str) -> str | None:
    tokens = set(re.findall(r"(?i)#[0-9a-f]{6}\b", text))
    for name in sorted(IMPRESS_NAMED_COLORS, key=len, reverse=True):
        if re.search(rf"(?i)(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text):
            tokens.add(name)
    normalized = {
        color
        for token in tokens
        if (color := normalize_impress_color(token)) is not None
    }
    return normalized.pop() if len(normalized) == 1 else None


def _boolean_style(text: str, term: str) -> bool | None:
    if not re.search(rf"(?i)\b{term}\w*\b", text):
        return None
    disabled = re.search(
        rf"(?is)\b(?:clear|disable|not|no|remove|without)\b.{{0,32}}\b{term}\w*\b|"
        rf"\b{term}\w*\b.{{0,24}}\b(?:off|false)\b",
        text,
    )
    return disabled is None


def parse_multislide_role_format_intent(
    instruction: str,
) -> MultiSlideRoleFormatIntent | None:
    """Parse uniform title formatting on an arbitrary explicit slide list."""
    scope = _title_format_scope(instruction)
    slides = _listed_slides(scope)
    if len(slides) < 2 or not re.search(r"(?i)\b(?:titles?|headings?)\b", scope):
        return None
    if re.search(r"(?i)\b(?:body|content|tables?|text\s*boxes?|textboxes?)\b", scope):
        return None

    properties: dict[str, Any] = {}
    color = _instruction_color(scope)
    if color is not None:
        properties["color"] = color
    for field, term in (
        ("bold", "bold"),
        ("italic", "italic"),
        ("underline", "underlin"),
        ("strike", "strik"),
    ):
        value = _boolean_style(scope, term)
        if value is not None:
            properties[field] = value
    if not properties:
        return None
    return MultiSlideRoleFormatIntent(
        slides=slides,
        roles=("title",),
        properties=properties,
    )


def action_slide_indices(arguments: dict[str, Any]) -> tuple[int, ...] | None:
    has_slide = "slide" in arguments
    has_slides = "slides" in arguments
    if has_slide == has_slides:
        return None
    values = [arguments.get("slide")] if has_slide else arguments.get("slides")
    if (
        not isinstance(values, list)
        or not values
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in values
        )
        or len(values) != len(set(values))
    ):
        return None
    return tuple(values)


def _arguments_match_intent(
    arguments: dict[str, Any], intent: MultiSlideRoleFormatIntent
) -> bool:
    slides = action_slide_indices(arguments)
    if slides is None or not set(slides).issubset(intent.slides):
        return False
    roles = arguments.get("roles")
    if roles != list(intent.roles) or "overrides" in arguments:
        return False
    supplied = {key: arguments[key] for key in _STYLE_FIELDS if key in arguments}
    if set(supplied) != set(intent.properties):
        return False
    for key, expected in intent.properties.items():
        actual = supplied[key]
        if key == "color":
            if normalize_impress_color(actual) != expected:
                return False
        elif actual is not expected:
            return False
    return True


def multislide_role_argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Validate model-selected role-format arguments without modifying them."""
    intent = parse_multislide_role_format_intent(str(state.instruction))
    if intent is None or action not in ROLE_ACTIONS:
        return []
    if action == ACTION and ("slides" not in arguments or "slide" in arguments):
        return [
            "slides.format_text_roles requires a unique nonempty zero-based slides array"
        ]
    if action == SINGLE_ACTION and ("slide" not in arguments or "slides" in arguments):
        return ["slide.format_text_roles requires one valid zero-based slide"]
    slides = action_slide_indices(arguments)
    if slides is None:
        return [f"{action} has an invalid zero-based slide target"]
    if not set(slides).issubset(intent.slides):
        return [
            f"{action} may target only the zero-based slides explicitly "
            f"requested by the instruction: {list(intent.slides)}"
        ]
    if arguments.get("roles") != list(intent.roles):
        return ["this request targets the semantic title role; pass roles=['title']"]
    if "overrides" in arguments:
        return ["uniform multi-slide title formatting does not require overrides"]
    supplied = {key: arguments[key] for key in _STYLE_FIELDS if key in arguments}
    if set(supplied) != set(intent.properties):
        return [
            "the role-format call must contain every and only the shared style properties "
            f"requested by the instruction: {sorted(intent.properties)}"
        ]
    for key, expected in intent.properties.items():
        actual = supplied[key]
        matches = (
            normalize_impress_color(actual) == expected
            if key == "color"
            else actual is expected
        )
        if not matches:
            return [f"the model-selected {key} value does not match the instruction"]
    return []


def _mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mappings(child)


def adapter_confirmed_role_slides(
    event: Any, expected_roles: tuple[str, ...]
) -> set[int]:
    """Return slides whose Adapter result confirms a nonempty semantic-role rule."""
    arguments = event.proposed.get("arguments")
    if not isinstance(arguments, dict):
        return set()
    requested = action_slide_indices(arguments)
    if requested is None:
        return set()
    expected = set(expected_roles)
    confirmed: set[int] = set()
    for candidate in _mappings(event.result):
        slide = candidate.get("slide")
        rules = candidate.get("rules")
        if (
            isinstance(slide, bool)
            or not isinstance(slide, int)
            or slide not in requested
            or not isinstance(rules, list)
        ):
            continue
        if any(
            isinstance(rule, dict)
            and set(rule.get("normalized_roles", [])) == expected
            and isinstance(rule.get("formatted"), list)
            and bool(rule["formatted"])
            for rule in rules
        ):
            confirmed.add(slide)
    return confirmed


def multislide_role_requirement_errors(state: Any) -> list[str]:
    """Require Adapter-confirmed coverage for every instruction-named slide."""
    intent = parse_multislide_role_format_intent(str(state.instruction))
    if intent is None:
        return []
    covered: set[int] = set()
    for action in ROLE_ACTIONS:
        for event in state.successful_action_events(action):
            arguments = event.proposed.get("arguments")
            if not isinstance(arguments, dict) or not _arguments_match_intent(
                arguments, intent
            ):
                continue
            covered.update(adapter_confirmed_role_slides(event, intent.roles))
    missing = sorted(set(intent.slides).difference(covered))
    if not missing:
        return []
    return [
        "slides.format_text_roles or per-slide role calls lack Adapter-confirmed "
        "title-format coverage for "
        f"zero-based slides {missing}; the complete requested set is {list(intent.slides)}"
    ]


__all__ = [
    "ACTION",
    "ROLE_ACTIONS",
    "SINGLE_ACTION",
    "MultiSlideRoleFormatIntent",
    "action_slide_indices",
    "adapter_confirmed_role_slides",
    "multislide_role_argument_contract_errors",
    "multislide_role_requirement_errors",
    "parse_multislide_role_format_intent",
]
