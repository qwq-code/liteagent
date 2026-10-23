"""Generic semantics for finite commands whose output must remain visible."""

from __future__ import annotations

import re
from typing import Any

from .result_envelopes import iter_result_mappings


ACTION = "terminal.show_output"

_COMMAND_RE = re.compile(r"(?i)\b(?:command|command[- ]line|shell|terminal)\b")
_EXECUTION_RE = re.compile(r"(?i)\b(?:execute|run|use|invoke|perform)\b")
_VISIBLE_OUTPUT_RE = re.compile(
    r"(?is)(?:\b(?:display|leave|print|show)\b.{0,100}"
    r"\b(?:output|result|terminal)\b|"
    r"\b(?:output|result)\b.{0,100}\b(?:terminal|visible)\b)"
)
_SCREENSHOT_RE = re.compile(r"(?i)\b(?:screenshot|snapshot|picture|image)\b")


def requests_visible_terminal_output(instruction: str) -> bool:
    """Recognize a finite command whose result must remain in a terminal."""
    normalized = re.sub(r"[-_]+", " ", instruction)
    return bool(
        _COMMAND_RE.search(normalized)
        and _EXECUTION_RE.search(normalized)
        and _VISIBLE_OUTPUT_RE.search(normalized)
        and not _SCREENSHOT_RE.search(normalized)
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    if domain != "os" or not requests_visible_terminal_output(instruction):
        return []
    return [ACTION]


def stage_actions(state: Any, actions: list[str]) -> list[str]:
    if not required_actions(str(state.domain), str(state.instruction)):
        return [action for action in actions if action != ACTION]
    if not state.successful_action_events(ACTION) and ACTION in actions:
        return [ACTION]
    return actions


def _confirmed_result(event: Any) -> dict[str, Any] | None:
    arguments = event.proposed.get("arguments")
    if not isinstance(arguments, dict):
        return None
    expected_returncodes = arguments.get("expected_returncodes", [0])
    if not isinstance(expected_returncodes, list):
        return None
    for mapping in iter_result_mappings(event.result):
        terminal = mapping.get("terminal")
        if (
            mapping.get("argv") == arguments.get("argv")
            and mapping.get("cwd_source") == arguments.get("cwd_source")
            and mapping.get("provenance") == arguments.get("provenance")
            and mapping.get("returncode") in expected_returncodes
            and mapping.get("verified") is True
            and isinstance(mapping.get("completion_marker"), str)
            and mapping["completion_marker"]
            and isinstance(terminal, dict)
            and terminal.get("command_completed") is True
            and terminal.get("output_visible") is True
        ):
            return mapping
    return None


def confirmed_terminal_window_ids(event: Any) -> set[str]:
    """Return Adapter-confirmed window handles for one exact terminal call."""
    result = _confirmed_result(event)
    terminal = result.get("terminal") if isinstance(result, dict) else None
    windows = terminal.get("windows") if isinstance(terminal, dict) else None
    if not isinstance(windows, list):
        return set()
    return {
        window.split(maxsplit=1)[0]
        for window in windows
        if isinstance(window, str) and window.strip()
    }


def _confirmed_event(event: Any) -> bool:
    return _confirmed_result(event) is not None


def completion_errors(state: Any) -> list[str]:
    if not required_actions(str(state.domain), str(state.instruction)):
        return []
    if any(_confirmed_event(event) for event in state.successful_action_events(ACTION)):
        return []
    return [
        "terminal.show_output lacks Adapter-confirmed execution of the exact model-selected "
        "argv with a completed command and output still visible in the terminal"
    ]


__all__ = [
    "ACTION",
    "confirmed_terminal_window_ids",
    "completion_errors",
    "requests_visible_terminal_output",
    "required_actions",
    "stage_actions",
]
