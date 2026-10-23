"""Generic staging for transfers from current media to an open presentation."""

from __future__ import annotations

import re
from typing import Any, Iterable


_AUDIO_WORKFLOW = (
    "media.extract_current_audio",
    "presentation.insert_audio",
)
_FRAME_WORKFLOW = (
    "media.extract_current_frame",
    "presentation.set_background_image",
)


def _normalized(instruction: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", instruction.casefold())).strip()


def _mentions_current_media(instruction: str) -> bool:
    current_reference = bool(
        re.search(
            r"\b(?:current(?:ly)?|this|playing|loaded|opened)\b.{0,80}"
            r"\b(?:clip|media|movie|video|vlc)\b"
            r"|\b(?:clip|media|movie|video|vlc)\b.{0,80}"
            r"\b(?:being\s+played|current(?:ly)?|loaded|opened|playing|this)\b",
            instruction,
        )
    )
    return current_reference or bool(
        re.search(r"\b(?:what|whatever)\s+vlc\s+is\s+playing\b", instruction)
    )


def _mentions_open_presentation(instruction: str) -> bool:
    return bool(
        re.search(
            r"\b(?:deck|impress|presentation|slide|slides|slideshow)\b", instruction
        )
    )


def _requests_audio_transfer(instruction: str) -> bool:
    extracts_audio = bool(
        re.search(r"\b(?:extract|save|separate|take)\b", instruction)
        and re.search(r"\b(?:audio|music|soundtrack)\b", instruction)
    )
    inserts_audio = bool(
        re.search(r"\b(?:add|apply|embed|insert|set|use)\b", instruction)
        and re.search(
            r"\b(?:background\s+(?:audio|music|sound)|audio|music|soundtrack)\b",
            instruction,
        )
    )
    return extracts_audio and inserts_audio


def _requests_frame_background_transfer(instruction: str) -> bool:
    extracts_frame = bool(
        re.search(r"\b(?:capture|extract|grab|save|take)\b", instruction)
        and re.search(r"\b(?:frame|snapshot|still)\b", instruction)
    )
    applies_background = bool(
        re.search(r"\b(?:apply|make|set|use)\b", instruction)
        and re.search(r"\b(?:backdrop|background)\b", instruction)
    )
    return extracts_frame and applies_background


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return public actions only; all workflow arguments remain model-owned."""
    if domain != "multi_apps":
        return []
    normalized = _normalized(instruction)
    if not (
        _mentions_current_media(normalized) and _mentions_open_presentation(normalized)
    ):
        return []
    actions: list[str] = []
    if _requests_audio_transfer(normalized):
        actions.extend(_AUDIO_WORKFLOW)
    if _requests_frame_background_transfer(normalized):
        actions.extend(_FRAME_WORKFLOW)
    return actions


def stage_actions(state: Any, actions: Iterable[str]) -> list[str]:
    """Expose the first incomplete model-owned action in each dependency chain."""
    selected = list(actions)
    required = required_actions(str(state.domain), str(state.instruction))
    if required not in [list(_AUDIO_WORKFLOW), list(_FRAME_WORKFLOW)]:
        return selected
    target = next(
        (action for action in required if not state.successful_action_events(action)),
        None,
    )
    if target is None:
        return selected
    focused = [action for action in selected if action == target]
    return focused or selected


__all__ = ["required_actions", "stage_actions"]
