"""Generic completion evidence for explicitly named output artifacts.

This module checks only filenames that the instruction ties to an output
operation. It consumes model-selected calls and returned Adapter evidence; it
never picks a destination or rewrites an action.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

from .completion_policy import action_is_read_only, effective_canonical_action


_FILE_TOKEN = (
    r'(?:"[^"\r\n]+\.[A-Za-z0-9]{1,12}\.?"'
    r"|'[^'\r\n]+\.[A-Za-z0-9]{1,12}\.?'"
    r"|`[^`\r\n]+\.[A-Za-z0-9]{1,12}`"
    r"|(?:~/|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_. -]+)*\.[A-Za-z0-9]{1,12})"
)
_OUTPUT_VERB_TARGET = re.compile(
    rf"(?is)\b(?:save|export|write|create|generate|compress|zip|convert|copy|move|merge|"
    rf"place|put|store|capture|record|produce|crop)\b"
    rf"(?:(?![.!?]\s+[A-Z]).){{0,180}}?\b(?:as|to|into|under)\b"
    rf"(?:(?![.!?]\s+[A-Z]).){{0,80}}?(?P<target>{_FILE_TOKEN})"
)
_NAMED_OUTPUT_TARGET = re.compile(
    rf"(?is)\b(?:create|generate|save|export|write|produce)\b"
    rf"(?:(?!\b(?:from|using|read|open)\b|[.!?]\s+[A-Z]).){{0,100}}?"
    rf"\b(?:file|document|archive|zip|report|image|output)\s+"
    rf"(?:named|called|titled)\s+(?P<target>{_FILE_TOKEN})"
)
_TITLE_OUTPUT_TARGET = re.compile(
    rf"(?is)\b(?:name|title)\s+(?:the\s+)?"
    rf"(?:file|document|archive|zip|report|image|output)\s+"
    rf"(?:as\s+)?(?P<target>{_FILE_TOKEN})"
)
_OUTPUT_ACTION_WORDS = (
    "save", "export", "convert", "copy", "move", "create", "write", "capture",
    "extract", "crop", "compress", "generate", "record", "download",
)
_OUTPUT_RESULT_KEYS = frozenset(
    {"path", "url", "output_path", "archive_path", "stdout_path", "destination", "copied", "files"}
)
def _target_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().strip("\"'`")
    if value.startswith("file:"):
        parsed = urlparse(value)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return None
        value = unquote(parsed.path)
    elif "%" in value:
        value = unquote(value)
    value = value.replace("\\", "/")
    return posixpath.normpath(value)


def requested_output_targets(instruction: str) -> list[str]:
    """Return unique filenames explicitly attached to an output instruction."""
    targets: list[str] = []
    for pattern in (
        _OUTPUT_VERB_TARGET,
        _NAMED_OUTPUT_TARGET,
        _TITLE_OUTPUT_TARGET,
    ):
        for match in pattern.finditer(str(instruction)):
            value = _target_path(match.group("target"))
            if value:
                # Natural-language sentences sometimes put their full stop
                # inside the filename's quotes. Do not alter observed paths.
                value = re.sub(r"(\.[A-Za-z0-9]{1,12})\.$", r"\1", value)
            if value and PurePosixPath(value).name and value not in targets:
                targets.append(value)
    return targets


def _action_creates_artifact(
    action: str, arguments: dict[str, Any], target: str | None = None
) -> bool:
    if action_is_read_only(action):
        return False
    operation = action.rsplit(".", 1)[-1].casefold()
    if action == "command.run":
        argv = arguments.get("argv")
        if arguments.get("stdout_path"):
            return True
        return bool(
            target
            and isinstance(argv, list)
            and any(_matches_target(argument, target) for argument in argv)
        )
    return any(word in operation for word in _OUTPUT_ACTION_WORDS)


def _mappings(value: Any) -> Iterator[dict[str, Any]]:
    seen: set[int] = set()
    pending: list[Any] = [value]
    for _depth in range(8):
        next_pending: list[Any] = []
        for mapping in pending:
            if not isinstance(mapping, dict) or id(mapping) in seen:
                continue
            seen.add(id(mapping))
            yield mapping
            for key in ("context_hint", "downstream_context", "adapter_response", "response", "result"):
                child = mapping.get(key)
                if isinstance(child, dict):
                    next_pending.append(child)
        pending = next_pending


def _path_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _path_values(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in _OUTPUT_RESULT_KEYS:
                yield from _path_values(item)
            elif key in {"path", "url", "output_path", "archive_path", "stdout_path", "destination"}:
                yield from _path_values(item)


def _matches_target(candidate: Any, target: str) -> bool:
    path = _target_path(candidate)
    if path is None:
        return False
    if target.startswith("~/"):
        if path.startswith("~/"):
            return path == target
        parts = PurePosixPath(path).parts
        if len(parts) > 3 and parts[:2] == ("/", "home"):
            return "/".join(parts[3:]) == target[2:]
        if len(parts) > 2 and parts[:2] == ("/", "root"):
            return "/".join(parts[2:]) == target[2:]
        return False
    if target.startswith("/"):
        return path == target
    return PurePosixPath(path).name == PurePosixPath(target).name


def _event_output_paths(event: Any, domain: str) -> tuple[str, list[str]]:
    _event_domain, action, arguments = effective_canonical_action(event, domain)
    if not _action_creates_artifact(action, arguments):
        return action, []
    paths: list[str] = []
    for mapping in _mappings(getattr(event, "result", None)):
        for key, value in mapping.items():
            if key in _OUTPUT_RESULT_KEYS:
                paths.extend(item for item in _path_values({key: value}) if item not in paths)
    return action, paths


def _verified_later_find(state: Any, target: str, after_step: int) -> bool:
    for event in getattr(state, "successful_adapter_events", lambda: [])():
        if getattr(event, "step", 0) <= after_step:
            continue
        _domain, action, _arguments = effective_canonical_action(
            event, str(getattr(state, "domain", ""))
        )
        if action != "filesystem.find":
            continue
        for mapping in _mappings(getattr(event, "result", None)):
            matches = mapping.get("matches")
            if not isinstance(matches, list):
                continue
            for item in matches:
                if (
                    isinstance(item, dict)
                    and item.get("kind") in {None, "file"}
                    and _matches_target(item.get("path"), target)
                ):
                    return True
    return False


def completion_errors(state: Any) -> list[str]:
    """Require explicit output filenames to be present in observed results."""
    targets = requested_output_targets(str(getattr(state, "instruction", "")))
    if not targets:
        return []
    events = list(getattr(state, "successful_adapter_events", lambda: [])())
    missing: list[str] = []
    for target in targets:
        observed = False
        for event in events:
            domain = str(getattr(state, "domain", ""))
            action, paths = _event_output_paths(event, domain)
            if any(_matches_target(path, target) for path in paths):
                observed = True
                break
            if _action_creates_artifact(
                action, effective_canonical_action(event, domain)[2], target,
            ) and _verified_later_find(state, target, getattr(event, "step", 0)):
                observed = True
                break
        if not observed:
            missing.append(target)
    if not missing:
        return []
    return [
        "the explicitly named output file(s) are not confirmed by a successful output "
        "result or a later filesystem.find read-back: "
        + ", ".join(repr(path) for path in missing)
    ]


__all__ = ["completion_errors", "requested_output_targets"]
