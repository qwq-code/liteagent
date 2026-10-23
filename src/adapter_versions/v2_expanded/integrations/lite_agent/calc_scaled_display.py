"""Instruction semantics for reusable Calc scaled-number display operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


_SCALE_DIVISORS = {
    "thousand": 1_000,
    "thousands": 1_000,
    "million": 1_000_000,
    "millions": 1_000_000,
    "billion": 1_000_000_000,
    "billions": 1_000_000_000,
    "trillion": 1_000_000_000_000,
    "trillions": 1_000_000_000_000,
}
_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_SCALE = r"thousands?|millions?|billions?|trillions?"


def _unit_pattern(name: str) -> str:
    return rf"(?:\s*\(\s*(?P<{name}>[^()\s]{{1,8}})\s*\))?"


_SCALE_RE = re.compile(rf"(?i)\b(?P<scale>{_SCALE})\b" + _unit_pattern("unit"))
_COLUMN_RE = re.compile(r"(?i)\bcolumn\s+(?P<column>[A-Z]{1,3})\b")
_CLAUSE_BOUNDARY_RE = re.compile(r"(?i)\s+and\s+|[;.\n]+")
_DISPLAY_INTENT_RE = re.compile(
    r"(?i)\b(?:show|display|represent(?:ation)?|format|scale|scaled|convert|use|put)\b"
)
_DECIMAL_PLACES_RE = re.compile(
    r"(?i)\b(?:round(?:ed|ing)?(?:\s+\w+){0,3}?|show(?:\s+\w+){0,3}?)\s+"
    r"(?P<count>\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"decimal\s+places?\b"
)
_SPACE_SEPARATOR_RE = re.compile(
    r"(?i)\b(?:white\s+space|whitespace|space)\b.{0,48}\b(?:digit|number|value|unit|suffix)"
    r"|\b(?:digit|number|value|unit|suffix)\b.{0,48}\b(?:white\s+space|whitespace|space)\b"
)
_NO_SPACE_RE = re.compile(
    r"(?i)\b(?:no|without)\s+(?:a\s+)?(?:white\s+space|whitespace|space)\b"
)
_HALF_UP_RE = re.compile(
    r"(?i)\bhalf(?:\s+should\s+be\s+rounded)?[ -]?up\b|"
    r"\bhalf\b.{0,32}\brounded\s+up\b"
)
_DESTINATION_COLUMN_RE = re.compile(
    r"(?i)(?:^|!|\$)(?P<column>[A-Z]{1,3})\$?[1-9][0-9]*"
)


@dataclass(frozen=True)
class ScaledDisplayOutput:
    destination_column: str
    divisor: int
    unit: str | None


@dataclass(frozen=True)
class ScaledDisplayIntent:
    outputs: tuple[ScaledDisplayOutput, ...]
    decimal_places: int | None
    separator: str | None
    rounding_mode: str | None


def _decimal_places(instruction: str) -> int | None:
    match = _DECIMAL_PLACES_RE.search(instruction)
    if match is None:
        return None
    count = match.group("count").casefold()
    return int(count) if count.isdigit() else _NUMBER_WORDS[count]


def parse_scaled_display_intent(instruction: str) -> ScaledDisplayIntent | None:
    """Parse explicit scale/unit-to-column clauses without using task identity."""
    if _DISPLAY_INTENT_RE.search(instruction) is None:
        return None
    outputs: list[ScaledDisplayOutput] = []
    seen: set[tuple[str, int, str | None]] = set()
    for clause in _CLAUSE_BOUNDARY_RE.split(instruction):
        scales = list(_SCALE_RE.finditer(clause))
        columns = list(_COLUMN_RE.finditer(clause))
        if len(scales) != 1 or len(columns) != 1:
            continue
        scale_match = scales[0]
        column_match = columns[0]
        scale = scale_match.group("scale").casefold()
        unit = scale_match.groupdict().get("unit")
        output = ScaledDisplayOutput(
            destination_column=column_match.group("column").upper(),
            divisor=_SCALE_DIVISORS[scale],
            unit=unit.strip() if unit else None,
        )
        key = (output.destination_column, output.divisor, output.unit)
        if key not in seen:
            seen.add(key)
            outputs.append(output)
    if not outputs:
        return None
    requires_space = bool(_SPACE_SEPARATOR_RE.search(instruction)) and not bool(
        _NO_SPACE_RE.search(instruction)
    )
    return ScaledDisplayIntent(
        outputs=tuple(outputs),
        decimal_places=_decimal_places(instruction),
        separator=" " if requires_space else None,
        rounding_mode="half_up" if _HALF_UP_RE.search(instruction) else None,
    )


def _destination_column(value: Any) -> str | None:
    match = _DESTINATION_COLUMN_RE.search(str(value).strip())
    return match.group("column").upper() if match is not None else None


def _call_covers(
    arguments: dict[str, Any],
    output: ScaledDisplayOutput,
    intent: ScaledDisplayIntent,
) -> bool:
    target_range = arguments.get("range", arguments.get("destination"))
    if _destination_column(target_range) != output.destination_column:
        return False
    # The cell value may already be converted by a model-selected formula or
    # write. A display divisor alone cannot establish the effective scale.
    if (
        output.unit is not None
        and str(arguments.get("unit", "")).strip() != output.unit
    ):
        return False
    if (
        intent.decimal_places is not None
        and arguments.get("decimal_places") != intent.decimal_places
    ):
        return False
    if intent.separator is not None:
        separator = arguments.get("separator", "space")
        if separator not in {intent.separator, "space"}:
            return False
    if (
        intent.rounding_mode is not None
        and arguments.get("rounding_mode", "half_up") != intent.rounding_mode
    ):
        return False
    return True


def missing_scaled_display_outputs(
    instruction: str,
    calls: Iterable[dict[str, Any]],
) -> list[ScaledDisplayOutput]:
    """Return explicit output clauses not covered by successful model-selected calls."""
    intent = parse_scaled_display_intent(instruction)
    if intent is None:
        return []
    arguments = [item for item in calls if isinstance(item, dict)]
    return [
        output
        for output in intent.outputs
        if not any(_call_covers(item, output, intent) for item in arguments)
    ]


def describe_scaled_display_output(output: ScaledDisplayOutput) -> str:
    unit = f", unit {output.unit!r}" if output.unit is not None else ""
    return f"column {output.destination_column}{unit}"
