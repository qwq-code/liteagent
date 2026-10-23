"""Generic semantics for screenshots of finite commands in a visible terminal."""

from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath
from typing import Any

from .adapter_results import has_passed_verification
from .result_envelopes import iter_result_mappings
from .terminal_output_semantics import confirmed_terminal_window_ids


_SHOW_ACTION = "terminal.show_output"
_CAPTURE_ACTION = "window.capture"


def requests_terminal_command_screenshot(instruction: str) -> bool:
    """Return whether a command and its output must be captured as a terminal image."""
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    has_command_execution = bool(
        re.search(r"\b(?:execute|run|invoke|perform)\b", normalized)
        and re.search(r"\b(?:command|command line|shell|terminal)\b", normalized)
    )
    has_terminal_image = bool(
        re.search(
            r"\b(?:screenshot|snapshot|image|picture|capture)\b.{0,80}"
            r"\b(?:terminal|command line|shell|window)\b"
            r"|\b(?:terminal|command line|shell|window)\b.{0,80}"
            r"\b(?:screenshot|snapshot|image|picture|capture)\b",
            normalized,
        )
    )
    has_saved_image = bool(
        re.search(r"\b(?:save|store|write|create|capture)\b", normalized)
        and re.search(r"(?:^|[^a-z0-9])[^\s'\"]+\.png\b", normalized)
    )
    return has_command_execution and has_terminal_image and has_saved_image


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return separate command-display and window-capture primitives."""
    if domain != "os" or not requests_terminal_command_screenshot(instruction):
        return []
    return [_SHOW_ACTION, _CAPTURE_ACTION]


def _paths_match(selected: Any, observed: Any) -> bool:
    if not isinstance(selected, str) or not isinstance(observed, str):
        return False
    selected = selected.strip()
    observed = observed.strip()
    if not selected or not observed:
        return False
    selected = posixpath.normpath(selected)
    observed = posixpath.normpath(observed)
    if not selected.startswith("~/"):
        return selected == observed
    suffix = PurePosixPath(selected[2:]).parts
    observed_parts = PurePosixPath(observed).parts
    if observed.startswith("~/"):
        return PurePosixPath(observed[2:]).parts == suffix
    return (
        len(observed_parts) >= 4
        and observed_parts[:2] == ("/", "home")
        and observed_parts[3:] == suffix
    ) or (
        len(observed_parts) >= 3
        and observed_parts[:2] == ("/", "root")
        and observed_parts[2:] == suffix
    )


def _capture_confirms_window(event: Any, window_ids: set[str]) -> bool:
    arguments = event.proposed.get("arguments")
    if not isinstance(arguments, dict) or not has_passed_verification(event.result):
        return False
    for mapping in iter_result_mappings(event.result):
        window_id = mapping.get("window_id")
        window = mapping.get("window")
        if (
            mapping.get("verified") is True
            and mapping.get("title_contains") == arguments.get("title_contains")
            and _paths_match(arguments.get("output_path"), mapping.get("output_path"))
            and isinstance(window_id, str)
            and window_id in window_ids
            and isinstance(window, str)
            and window.split(maxsplit=1)[0] == window_id
        ):
            return True
    return False


def _has_confirmed_capture_handoff(state: Any) -> bool:
    shows = [
        (event.step, confirmed_terminal_window_ids(event))
        for event in state.successful_action_events(_SHOW_ACTION)
    ]
    for capture in state.successful_action_events(_CAPTURE_ACTION):
        for show_step, window_ids in shows:
            if (
                show_step < capture.step
                and window_ids
                and _capture_confirms_window(capture, window_ids)
            ):
                return True
    return False


def completion_errors(state: Any) -> list[str]:
    """Require a verified terminal-display to matching-window-capture handoff."""
    required = required_actions(str(state.domain), str(state.instruction))
    missing = [
        f"the instruction requires a successful {action} call before completion"
        for action in required
        if not state.successful_action_events(action)
    ]
    if missing or not required:
        return missing
    if _has_confirmed_capture_handoff(state):
        return []
    return [
        "the terminal screenshot must be captured after terminal.show_output and must "
        "contain the same Adapter-confirmed terminal window; select that observed terminal "
        "window in a new window.capture call"
    ]


__all__ = [
    "completion_errors",
    "requests_terminal_command_screenshot",
    "required_actions",
]
