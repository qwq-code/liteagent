"""Completion and argument contracts for observed paths copied to the clipboard."""

from __future__ import annotations

import re
from typing import Any, Iterator

from .adapter_results import has_passed_verification
from .completion_policy import canonical_action_request, effective_adapter_action


_CLIPBOARD = re.compile(r"(?i)\bclip\s*board\b")
_LOOKUP = re.compile(r"(?i)\b(?:find|locate|search(?:\s+for)?|look\s+up|discover)\b")
_PATH_TERM = (
    r"(?:\b(?:full\s+)?(?:file\s+)?path\b|\blocation\b|"
    r"\bwhere\b.{0,80}\b(?:located|saved|stored)\b)"
)
_TRANSFER_TERM = r"\b(?:copy|place|put|set|store|write)\b"
_PATH_CLIPBOARD_BINDING = re.compile(
    rf"(?is)(?:"
    rf"{_PATH_TERM}.{{0,120}}{_TRANSFER_TERM}.{{0,80}}\bclip\s*board\b|"
    rf"{_TRANSFER_TERM}.{{0,80}}{_PATH_TERM}.{{0,80}}\bclip\s*board\b"
    rf")"
)
_NON_PATH_CLIPBOARD_BINDING = re.compile(
    rf"(?is){_TRANSFER_TERM}.{{0,60}}\b(?:contents?|text|title|body|summary|"
    rf"selection|words?|file\s*name|filename|(?:file|document)\s+itself)\b"
    rf".{{0,60}}\bclip\s*board\b"
)
_RESULT_KEYS = (
    "adapter_response",
    "response",
    "result",
    "context_hint",
    "downstream_context",
)
_SUPPORTED_DOMAINS = frozenset({"multi_apps", "os"})


def requests_found_path_to_clipboard(instruction: str) -> bool:
    """Return whether the instruction binds a looked-up path to the clipboard."""
    normalized = re.sub(r"\s+", " ", instruction)
    return bool(
        _CLIPBOARD.search(normalized)
        and _LOOKUP.search(normalized)
        and _PATH_CLIPBOARD_BINDING.search(normalized)
        and not _NON_PATH_CLIPBOARD_BINDING.search(normalized)
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    """Expose lookup and clipboard primitives for the bounded path workflow."""
    if domain not in _SUPPORTED_DOMAINS or not requests_found_path_to_clipboard(
        instruction
    ):
        return []
    return ["filesystem.find", "clipboard.set"]


def workflow_applies(state: Any) -> bool:
    """Return whether the state belongs to the supported clipboard path workflow."""
    return str(getattr(state, "domain", "")) in _SUPPORTED_DOMAINS and (
        requests_found_path_to_clipboard(str(getattr(state, "instruction", "")))
    )


def _attempted_action(state: Any, action: str) -> bool:
    return any(
        effective_adapter_action(event, str(getattr(state, "domain", "")))[1] == action
        for event in getattr(state, "events", ())
        if getattr(event, "proposed", {}).get("kind") == "adapter"
    )


def _result_mappings(value: Any) -> Iterator[dict[str, Any]]:
    pending: list[Any] = [value]
    seen: set[int] = set()
    for _depth in range(8):
        if not pending:
            return
        next_pending: list[Any] = []
        for candidate in pending:
            if not isinstance(candidate, dict) or id(candidate) in seen:
                continue
            seen.add(id(candidate))
            yield candidate
            for key in _RESULT_KEYS:
                child = candidate.get(key)
                if isinstance(child, dict):
                    next_pending.append(child)
        pending = next_pending


def _successful_events(state: Any, action: str) -> Iterator[tuple[Any, dict[str, Any]]]:
    for event in getattr(state, "successful_adapter_events", lambda: [])():
        _domain, event_action, arguments = effective_adapter_action(
            event, str(getattr(state, "domain", ""))
        )
        if event_action == action and has_passed_verification(
            getattr(event, "result", None)
        ):
            yield event, arguments


def observed_find_paths(state: Any, *, before_step: int | None = None) -> set[str]:
    """Return verified file paths disclosed by successful filesystem.find calls."""
    paths: set[str] = set()
    for event, _arguments in _successful_events(state, "filesystem.find"):
        if before_step is not None and getattr(event, "step", 0) >= before_step:
            continue
        for mapping in _result_mappings(getattr(event, "result", None)):
            matches = mapping.get("matches")
            if not isinstance(matches, list):
                continue
            for match in matches:
                path = match.get("path") if isinstance(match, dict) else None
                if not isinstance(path, str) or not path.strip():
                    continue
                paths.add(path)
    return paths


def _clipboard_arguments(
    domain: str, action: str, arguments: dict[str, Any]
) -> dict[str, Any] | None:
    _domain, canonical_action, selected = canonical_action_request(
        domain, action, arguments
    )
    return selected if canonical_action == "clipboard.set" else None


def path_clipboard_satisfied(state: Any) -> bool:
    """Return whether the final verified clipboard write uses a prior observed path."""
    if not workflow_applies(state):
        return False
    writes = list(_successful_events(state, "clipboard.set"))
    if not writes:
        return False
    event, arguments = max(writes, key=lambda item: getattr(item[0], "step", 0))
    paths = observed_find_paths(state, before_step=getattr(event, "step", 0))
    return isinstance(arguments.get("text"), str) and arguments["text"] in paths


def pending_actions(state: Any) -> list[str] | None:
    """Return the next bounded public stage, or None for ordinary recovery."""
    if not workflow_applies(state):
        return None
    if path_clipboard_satisfied(state):
        return []
    if observed_find_paths(state):
        return ["clipboard.set"]
    if _attempted_action(state, "filesystem.find"):
        return None
    return ["filesystem.find"]


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Require the model-selected clipboard payload to be an observed path."""
    if not workflow_applies(state):
        return []
    selected = _clipboard_arguments(
        str(getattr(state, "domain", "")), action, arguments
    )
    if selected is None:
        return []
    paths = observed_find_paths(state)
    if not paths:
        return [
            "the instruction requires finding a file path before copying it to the "
            "clipboard; use filesystem.find and select an exact returned path"
        ]
    text = selected.get("text")
    if isinstance(text, str) and text in paths:
        return []
    return [
        "clipboard.set text must be one exact file path returned by the successful "
        "filesystem.find observation for this path-to-clipboard request; the Runner "
        "does not choose or rewrite the text"
    ]


def completion_errors(state: Any) -> list[str]:
    """Require the final verified clipboard write to retain an observed path."""
    if not workflow_applies(state):
        return []
    writes = list(_successful_events(state, "clipboard.set"))
    if not writes:
        if not observed_find_paths(state):
            return [
                "no verified filesystem.find result exposes the requested file path for "
                "the clipboard"
            ]
        return [
            "no verified clipboard.set call copied an observed file path to the clipboard"
        ]
    event, arguments = max(writes, key=lambda item: getattr(item[0], "step", 0))
    paths = observed_find_paths(state, before_step=getattr(event, "step", 0))
    if not paths:
        return [
            "the final clipboard.set is not backed by a prior verified filesystem.find "
            "path observation"
        ]
    text = arguments.get("text")
    if isinstance(text, str) and text in paths:
        return []
    return [
        "the last verified clipboard.set no longer contains an exact file path returned "
        "by filesystem.find; select an observed path rather than file contents or other text"
    ]


__all__ = [
    "argument_contract_errors",
    "completion_errors",
    "observed_find_paths",
    "path_clipboard_satisfied",
    "pending_actions",
    "required_actions",
    "requests_found_path_to_clipboard",
    "workflow_applies",
]
