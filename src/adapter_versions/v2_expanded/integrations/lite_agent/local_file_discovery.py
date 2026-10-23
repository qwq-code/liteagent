"""Instruction-only staging for unresolved local input paths."""

from __future__ import annotations

import json
import posixpath
import re
from typing import Any, Iterable

from .vlc_semantics import required_actions as vlc_required_actions


_FILE_REFERENCE = re.compile(
    r"(?i)\b(?:artifact|artwork|document|file|files|image|images|paper|papers|"
    r"photo|photos|picture|pictures|report|reports|script|scripts)\b|"
    r"\.[a-z0-9]{1,12}\b"
)
_LOCAL_LOCATION = re.compile(
    r"(?i)\b(?:current\s+directory|desktop|documents|downloads|folder|home\s+directory)\b"
)
_EXISTING_INPUT = re.compile(
    r"(?i)\b(?:attached|available|downloaded|existing|located|opened|placed|prepared|"
    r"provided|saved|stored|supplied)\b|"
    r"\b(?:is|are|was|were)\s+(?:in|on|under)\b"
)
_ATTRIBUTIVE_LOCAL_INPUT = re.compile(
    r"(?i)\b(?:desktop|documents|downloads)\s+"
    r"(?:\.[a-z0-9]{1,12}\s+)?"
    r"(?:artifact|artwork|document|file|image|paper|photo|picture|report|script)\b"
)
_MAIL_SOURCE = re.compile(
    r"(?i)\b(?:address\s+book|attachment|e-?mail|mailbox|message|thunderbird)\b"
)
_CURRENT_APPLICATION_SOURCE = re.compile(
    r"(?i)\b(?:currently\s+open|opened\s+(?:now|in\s+(?:the\s+)?(?:app|application))|"
    r"open\s+now)\b"
)
_BATCH_INPUT = re.compile(
    r"(?i)\b(?:all|batch|each|every|multiple)\b.{0,40}"
    r"(?:\.[a-z0-9]{1,12}\b|documents?\b|files?\b|images?\b|papers?\b)"
)
_EXPLICIT_LOCAL_PATH = re.compile(r"(?<!\w)(?:/|~/)[^\s\"']+")

_CURRENT_CONTEXT_ACTIONS = frozenset(
    {
        "media.inspect_current",
        "presentation.inspect_current",
        "spreadsheet.inspect_current",
    }
)

_LOCAL_INPUT_ACTIONS = frozenset(
    {
        "desktop.open_path",
        "document.convert",
        "document.extract_images",
        "document.read_file",
        "file.read_text",
        "image.crop",
        "image.extract_text_batch",
        "image.insert_at_cursor",
        "media.extract_audio",
        "pdf.extract_text_batch",
        "pdf.outline.inspect",
        "pdf.pages.extract",
        "playback.open",
        "presentation.insert_audio",
        "spreadsheet.convert_file",
        "spreadsheet.read_file",
    }
)


def _event_arguments(event: Any) -> tuple[str | None, dict[str, Any]]:
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return None, {}
    action = proposed.get("action")
    arguments = proposed.get("arguments")
    if not isinstance(arguments, dict):
        return action if isinstance(action, str) else None, {}
    if action == "adapter.call":
        payload = arguments.get("payload")
        if isinstance(payload, dict):
            nested_action = payload.get("action") or arguments.get("action")
            nested_params = payload.get("params")
            return (
                nested_action if isinstance(nested_action, str) else None,
                nested_params if isinstance(nested_params, dict) else {},
            )
        nested_action = arguments.get("downstream_action") or arguments.get("action")
        nested_params = arguments.get("params")
        return (
            nested_action if isinstance(nested_action, str) else None,
            nested_params if isinstance(nested_params, dict) else {},
        )
    return action if isinstance(action, str) else None, arguments


def _zero_match_result(value: Any, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if isinstance(value, dict):
        matches = value.get("matches")
        if isinstance(matches, list) and not matches:
            return True
        if any(
            isinstance(value.get(key), int)
            and not isinstance(value.get(key), bool)
            and value[key] == 0
            for key in ("match_count", "returned_count")
        ):
            return True
        return any(_zero_match_result(child, depth + 1) for child in value.values())
    if isinstance(value, list):
        return any(_zero_match_result(child, depth + 1) for child in value)
    return False


def zero_match_filesystem_find_events(state: Any) -> list[Any]:
    """Return successful model-selected finds that proved a zero-match query."""
    return [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "executed", False)
        and not getattr(event, "error", None)
        and _event_arguments(event)[0] == "filesystem.find"
        and _zero_match_result(getattr(event, "result", None))
    ]


def zero_match_playback_find_events(state: Any) -> list[Any]:
    """Return successful local media searches that found no path."""
    return [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "executed", False)
        and not getattr(event, "error", None)
        and _event_arguments(event)[0] == "playback.find_local"
        and _zero_match_result(getattr(event, "result", None))
    ]


def unresolved_zero_match_find(state: Any) -> bool:
    """Keep discovering when every successful file search found nothing."""
    return bool(zero_match_filesystem_find_events(state)) and not (
        has_positive_local_file_discovery(state)
    )


def _find_parameter_schemas(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        properties = node.get("properties")
        found: list[dict[str, Any]] = []
        if isinstance(properties, dict) and {"roots", "name_patterns"}.issubset(properties):
            found.append(node)
        for child in node.values():
            found.extend(_find_parameter_schemas(child))
        return found
    if isinstance(node, list):
        found: list[dict[str, Any]] = []
        for child in node:
            found.extend(_find_parameter_schemas(child))
        return found
    return []


def constrain_zero_match_find_tools(
    tools: list[dict[str, Any]], state: Any
) -> list[dict[str, Any]]:
    """Force a materially different discovery query after a zero-match find."""
    zeroes = [
        *zero_match_filesystem_find_events(state),
        *zero_match_playback_find_events(state),
    ]
    if not zeroes:
        return tools
    queries: list[dict[str, Any]] = []
    truncated_media_label = False
    for event in zeroes:
        action, arguments = _event_arguments(event)
        if action == "playback.find_local" and getattr(state, "domain", None) == "vlc":
            patterns = arguments.get("name_patterns")
            truncated_media_label |= isinstance(patterns, list) and any(
                isinstance(pattern, str) and "..." in pattern for pattern in patterns
            )
        if arguments:
            queries.append({
                key: arguments[key]
                for key in ("roots", "name_patterns", "kind", "recursive", "max_depth")
                if key in arguments
            })
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if name not in {
            "adapter__filesystem_find",
            "adapter__adapter_call",
            "adapter__playback_find_local",
        }:
            continue
        schemas = _find_parameter_schemas(function.get("parameters"))
        for schema in schemas:
            properties = schema["properties"]
            if truncated_media_label and name == "adapter__playback_find_local":
                patterns = properties.get("name_patterns")
                items = patterns.get("items") if isinstance(patterns, dict) else None
                if isinstance(items, dict):
                    items["enum"] = [
                        "*", "*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov",
                        "*.mp3", "*.wav", "*.flac", "*.ogg",
                    ]
                    patterns["description"] = (
                        "A previous search used a truncated desktop label ending in ... "
                        "and found nothing. Omit this field to search all names, or select "
                        "one of these broad media globs. The visible ellipsis is not part "
                        "of the filename."
                    )
            kind = properties.get("kind")
            looking_for_directory = bool(re.search(
                r"(?i)\b(?:find|locate|search for)\s+(?:(?:the|a|an)\s+)?"
                r"(?:folder|directory)\b",
                str(getattr(state, "instruction", "")),
            ))
            if isinstance(kind, dict) and looking_for_directory and any(
                query.get("kind", "file") == "file" for query in queries
            ):
                kind["enum"] = [value for value in kind.get("enum", []) if value != "file"]
            if isinstance(kind, dict):
                kind["description"] = (
                    str(kind.get("description", "")).rstrip()
                    + " A prior successful find returned zero matches. Change the root or "
                    "basename pattern; change kind when looking for directories."
                ).strip()
            function["description"] = (
                str(function.get("description", "")).rstrip()
                + " The previous filesystem.find query returned zero matches. Do not repeat its exact "
                "roots, name_patterns, kind, recursive, or max_depth tuple; change at least one "
                "discovery dimension. Keep kind='file' for files; use kind='any' or "
                "kind='directory' when checking for folders."
            ).strip()
            dimensions = ("roots", "name_patterns", "kind", "recursive", "max_depth")
            forbidden = [
                {
                    "not": {
                        "allOf": [
                            {
                                "required": list(query),
                                "properties": {
                                    key: {"const": value} for key, value in query.items()
                                },
                            },
                            *(
                                {"not": {"required": [key]}}
                                for key in dimensions
                                if key not in query
                            ),
                        ]
                    }
                }
                for query in queries
            ]
            if forbidden:
                schema["allOf"] = [*schema.get("allOf", []), *forbidden]
    return tools


def _error_codes(value: Any, depth: int = 0) -> set[str]:
    if depth > 8:
        return set()
    if isinstance(value, dict):
        codes = {
            item.upper()
            for key in ("code", "error_code")
            if isinstance((item := value.get(key)), str)
        }
        for item in value.values():
            if isinstance(item, (dict, list)):
                codes.update(_error_codes(item, depth + 1))
        return codes
    if isinstance(value, list):
        codes: set[str] = set()
        for item in value:
            codes.update(_error_codes(item, depth + 1))
        return codes
    return set()


def _is_missing_path_error(value: Any) -> bool:
    return any(
        code == "PATH_NOT_FOUND"
        or code == "FILE_NOT_FOUND"
        or code.endswith("_PATH_NOT_FOUND")
        or code.endswith("_FILE_NOT_FOUND")
        for code in _error_codes(value)
    )


def _latest_failed_local_input(state: Any) -> Any | None:
    for event in reversed(getattr(state, "events", ())):
        proposed = getattr(event, "proposed", None)
        if (
            isinstance(proposed, dict)
            and proposed.get("kind") == "adapter"
            and proposed.get("action") in _LOCAL_INPUT_ACTIONS
            and not getattr(event, "executed", False)
            and _is_missing_path_error(getattr(event, "error", None))
        ):
            return event
    return None


def _path_values(value: Any, names: frozenset[str], depth: int = 0) -> set[str]:
    if depth > 8:
        return set()
    if isinstance(value, dict):
        found = {
            item
            for key, item in value.items()
            if key in names and isinstance(item, str) and item
        }
        for item in value.values():
            if isinstance(item, (dict, list)):
                found.update(_path_values(item, names, depth + 1))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found.update(_path_values(item, names, depth + 1))
        return found
    return set()


def _directory_representation(path: str) -> str:
    stripped = path.rstrip("/") or "/"
    return posixpath.dirname(stripped) or "."


def _equivalent_failed_root_representations(state: Any, roots: set[str]) -> set[str]:
    equivalents = set(roots)
    for event in getattr(state, "events", ()):
        proposed = getattr(event, "proposed", None)
        if (
            not isinstance(proposed, dict)
            or proposed.get("action") not in _LOCAL_INPUT_ACTIONS
            or not _is_missing_path_error(getattr(event, "error", None))
        ):
            continue
        requested = {
            _directory_representation(path)
            for path in _path_values(
                getattr(event, "error", None), frozenset({"requested_path"})
            )
        }
        resolved = {
            _directory_representation(path)
            for path in _path_values(
                getattr(event, "error", None), frozenset({"resolved_path"})
            )
        }
        if {item.rstrip("/") for item in roots}.intersection(
            item.rstrip("/") for item in requested
        ):
            equivalents.update(resolved)
        if {item.rstrip("/") for item in roots}.intersection(
            item.rstrip("/") for item in resolved
        ):
            equivalents.update(requested)
    with_slash_variants = set(equivalents)
    for root in equivalents:
        canonical = root.rstrip("/") or "/"
        with_slash_variants.add(canonical)
        if canonical != "/":
            with_slash_variants.add(canonical + "/")
    return with_slash_variants


def failed_filesystem_find_roots(state: Any, *, after_step: int = 0) -> list[str]:
    """Return model-selected roots that a structured find error proved unavailable."""
    failed: set[str] = set()
    for event in getattr(state, "events", ()):
        if getattr(event, "step", 0) <= after_step:
            continue
        proposed = getattr(event, "proposed", None)
        if (
            not isinstance(proposed, dict)
            or proposed.get("kind") != "adapter"
            or proposed.get("action") != "filesystem.find"
            or getattr(event, "executed", False)
            or not _is_missing_path_error(getattr(event, "error", None))
        ):
            continue
        arguments = proposed.get("arguments")
        roots = arguments.get("roots") if isinstance(arguments, dict) else None
        if not isinstance(roots, list):
            continue
        failed.update(root for root in roots if isinstance(root, str) and root)
    return sorted(_equivalent_failed_root_representations(state, failed))


def failed_local_input_needs_discovery(state: Any) -> bool:
    """Return whether an observed missing path still needs model-selected discovery."""
    failed = _latest_failed_local_input(state)
    if failed is None:
        return False
    for event in getattr(state, "events", ()):
        if getattr(event, "step", 0) <= getattr(failed, "step", 0):
            continue
        proposed = getattr(event, "proposed", None)
        if not isinstance(proposed, dict) or not getattr(event, "executed", False):
            continue
        action = proposed.get("action")
        if action == "filesystem.find" and _contains_returned_match(
            getattr(event, "result", None)
        ):
            return False
        if action in _LOCAL_INPUT_ACTIONS:
            return False
    return True


def constrain_failed_path_discovery_tools(
    tools: list[dict[str, Any]], state: Any
) -> list[dict[str, Any]]:
    """Explain recovery from an observed missing path without fixing any arguments."""
    failed = _latest_failed_local_input(state)
    if failed is None or not failed_local_input_needs_discovery(state):
        return tools
    unavailable_roots = failed_filesystem_find_roots(
        state, after_step=getattr(failed, "step", 0)
    )
    proposed = getattr(failed, "proposed", {})
    arguments = proposed.get("arguments") if isinstance(proposed, dict) else None
    prior_pattern = (
        arguments.get("input_pattern") if isinstance(arguments, dict) else None
    )
    pattern_guidance = (
        f" The failed action selected input_pattern={prior_pattern!r}; use that same "
        "basename glob in name_patterns when it describes the desired files."
        if isinstance(prior_pattern, str) and prior_pattern
        else ""
    )
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, dict) or function.get("name") != (
            "adapter__filesystem_find"
        ):
            continue
        function["description"] = (
            str(function.get("description", "")).rstrip()
            + " A previous model-selected local input path returned PATH_NOT_FOUND. "
            "Search for the existing input files themselves, not for a directory label; "
            "choose a broad existing root, file basename globs, kind=file, and recursive=true."
            + pattern_guidance
        ).strip()
        parameters = function.get("parameters")
        properties = (
            parameters.get("properties") if isinstance(parameters, dict) else None
        )
        if not isinstance(properties, dict):
            continue
        roots = properties.get("roots")
        if isinstance(roots, dict):
            roots["description"] = (
                str(roots.get("description", "")).rstrip()
                + " The preceding local input was not found. Choose a broad existing root "
                "such as ~/ rather than assuming its guessed parent directory exists."
            ).strip()
            if unavailable_roots:
                roots["description"] += (
                    " These roots were selected by the model and then returned a structured "
                    "missing-path error, so do not submit any of them again: "
                    + json.dumps(unavailable_roots, ensure_ascii=True)
                    + "."
                )
                roots["not"] = {"contains": {"enum": unavailable_roots}}
        patterns = properties.get("name_patterns")
        if isinstance(patterns, dict):
            patterns["description"] = (
                str(patterns.get("description", "")).rstrip()
                + pattern_guidance
                + " Search for matching input file basenames rather than a folder name."
            ).strip()
    return tools


def _contains_returned_match(value: Any, depth: int = 0) -> bool:
    if not isinstance(value, dict) or depth > 6:
        return False
    matches = value.get("matches")
    if isinstance(matches, list) and bool(matches):
        return True
    for key in ("returned_count", "match_count"):
        count = value.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            return True
    return any(
        _contains_returned_match(value.get(key), depth + 1)
        for key in (
            "adapter_response",
            "context_hint",
            "downstream_context",
            "response",
            "result",
        )
    )


def has_positive_local_file_discovery(
    state: Any, action: str = "filesystem.find"
) -> bool:
    for event in getattr(state, "events", ()):
        proposed = getattr(event, "proposed", None)
        if (
            isinstance(proposed, dict)
            and proposed.get("kind") == "adapter"
            and _event_arguments(event)[0] == action
            and getattr(event, "executed", False)
            and not getattr(event, "error", None)
            and _contains_returned_match(getattr(event, "result", None))
        ):
            return True
    return False


def requires_local_input_discovery(instruction: str) -> bool:
    """Return whether an existing local input is described without an exact path."""
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    if _EXPLICIT_LOCAL_PATH.search(normalized):
        return False
    if _BATCH_INPUT.search(normalized):
        return False
    clauses = re.split(r"(?<=[.!?])\s+|[;\n]+", normalized)
    return any(
        not _MAIL_SOURCE.search(clause)
        and not _CURRENT_APPLICATION_SOURCE.search(clause)
        and _FILE_REFERENCE.search(clause)
        and _LOCAL_LOCATION.search(clause)
        and (_EXISTING_INPUT.search(clause) or _ATTRIBUTIVE_LOCAL_INPUT.search(clause))
        for clause in clauses
    )


def stage_local_file_discovery(state: Any, actions: Iterable[str]) -> list[str]:
    """Leave Multi-Apps route selection to adapter.call catalog discovery."""
    return list(actions)


def local_file_discovery_stage_active(state: Any, actions: Iterable[str]) -> bool:
    """Return whether an unresolved VLC local media source is in discovery stage."""
    if getattr(state, "domain", None) != "vlc":
        return False
    if "playback.find_local" not in set(actions):
        return False
    # A ranked tool is an available option, not a required workflow stage.
    # Current-media transformations and explicit paths need no file search;
    # treating a suggested finder as mandatory hides completion indefinitely.
    if "playback.find_local" not in vlc_required_actions(
        "vlc", str(getattr(state, "instruction", ""))
    ):
        return False
    return not has_positive_local_file_discovery(state, "playback.find_local")


__all__ = [
    "constrain_failed_path_discovery_tools",
    "constrain_zero_match_find_tools",
    "failed_filesystem_find_roots",
    "failed_local_input_needs_discovery",
    "has_positive_local_file_discovery",
    "local_file_discovery_stage_active",
    "zero_match_playback_find_events",
    "zero_match_filesystem_find_events",
    "unresolved_zero_match_find",
    "requires_local_input_discovery",
    "stage_local_file_discovery",
]
