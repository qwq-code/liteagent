"""Compatibility shims for decomposed Impress personal-information cleanup."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_REMOVAL_RE = re.compile(
    r"(?is)\b(?:delete|remove|clear|erase)\b.{0,100}"
    r"\b(?:personal|contact)\s+(?:information|info|details?)\b"
)
_SLIDE_RE = re.compile(r"(?i)\b(?:slide|page)\s+(\d+)\b")
_ICON_RE = re.compile(r"(?i)\bicons?\b")
_EXCLUDE_ICON_RE = re.compile(
    r"(?is)\b(?:without|excluding|except|keep|preserve|retain)\b.{0,40}\bicons?\b"
)


@dataclass(frozen=True)
class PersonalInformationRemovalIntent:
    slide: int | None
    include_adjacent_icons: bool


def parse_personal_information_removal_intent(
    instruction: str,
) -> PersonalInformationRemovalIntent | None:
    """Recognize cleanup wording without selecting a concrete shape or action."""
    match = _REMOVAL_RE.search(instruction)
    if match is None:
        return None
    nearby_start = max(0, match.start() - 120)
    nearby = instruction[nearby_start : min(len(instruction), match.end() + 140)]
    references = list(_SLIDE_RE.finditer(nearby))
    target = None
    if references:
        local_center = match.start() - nearby_start + len(match.group(0)) / 2
        closest = min(
            references,
            key=lambda item: abs((item.start() + item.end()) / 2 - local_center),
        )
        number = int(closest.group(1))
        if number >= 1:
            target = number - 1
    icon_window = instruction[match.start() : min(len(instruction), match.end() + 100)]
    include_icons = bool(_ICON_RE.search(icon_window)) and not bool(
        _EXCLUDE_ICON_RE.search(icon_window)
    )
    return PersonalInformationRemovalIntent(target, include_icons)


def stage_actions(state: Any, actions: list[str]) -> list[str]:
    """Keep normal atomic inspection and shape-deletion orchestration unchanged."""
    return actions


def personal_information_argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """The standard atomic action contracts validate their own arguments."""
    return []


def personal_information_requirement_errors(state: Any) -> list[str]:
    """Completion is covered by normal Impress mutation and read-back evidence."""
    return []


__all__ = [
    "PersonalInformationRemovalIntent",
    "parse_personal_information_removal_intent",
    "personal_information_argument_contract_errors",
    "personal_information_requirement_errors",
    "stage_actions",
]
