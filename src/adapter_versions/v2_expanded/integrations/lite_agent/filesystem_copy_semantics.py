"""Generic completion evidence for instruction-scoped file collections.

The predicate in this module is deliberately evidence-only.  It derives the
collection shape from the natural-language instruction and obtains the source
and copied paths from successful public filesystem results.  It never reads a
task identifier and never changes a model-selected proposal.
"""

from __future__ import annotations

import fnmatch
import posixpath
import re
from typing import Any
from urllib.parse import unquote, urlparse

from .completion_policy import effective_canonical_action


_COPY_VERB_RE = re.compile(
    r"(?i)\b(?:copy|copies|copied|duplicate|duplicates|replicate)\b"
)
_COLLECTION_RE = re.compile(
    r"(?i)\b(?:all|any|each|every|matching|selected|multiple)\b|"
    r"\bfiles\b|\bimages\b|\bpictures\b"
)
_RECURSIVE_RE = re.compile(
    r"(?i)\brecursiv\w*\b|\bsubfolders?\b|\bsubdirectories?\b|"
    r"\b(?:through|across|throughout)\s+(?:the\s+)?folders?\b"
)
_EXTENSION_RE = re.compile(r"(?i)(?:\*?\.)\s*([a-z0-9]{1,12})\b")
_DIRECTORY_RE = r"(?:directory|directories|folder|folders|dir|dirs)"
_COPY_ACTIONS = ("filesystem.copy_to_directories", "filesystem.copy")
_QUOTED_LABEL = r"[\"'“‘]([^\"'”’\r\n]+)[\"'”’]"
_BARE_LABEL = r"([A-Za-z0-9][A-Za-z0-9_.-]*)"
_PRESERVE_HIERARCHY_RE = re.compile(
    r"(?i)\bpreserv\w*\s+(?:the\s+)?(?:directory|folder)?\s*"
    r"(?:hierarchy|structure|layout)\b"
)


def _label(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    if match is None:
        return None
    for value in match.groups():
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _source_label(instruction: str) -> str | None:
    patterns = (
        rf"(?is)\bfolders?\s+of\s+(?:the\s+)?(?:{_QUOTED_LABEL}|{_BARE_LABEL})\s+{_DIRECTORY_RE}\b",
        rf"(?is)\bfrom\s+(?:the\s+)?(?:{_QUOTED_LABEL}|{_BARE_LABEL})\s+{_DIRECTORY_RE}\b",
        rf"(?is)\b(?:under|inside|within)\s+(?:the\s+)?(?:{_QUOTED_LABEL}|{_BARE_LABEL})\s+{_DIRECTORY_RE}\b",
    )
    for pattern in patterns:
        value = _label(pattern, instruction)
        if value is not None:
            return value
    return None


def _destination_label(instruction: str) -> str | None:
    patterns = (
        rf"(?is)\b(?:into|to|in)\s+(?:{_QUOTED_LABEL})",
        rf"(?is)\b(?:into|to|in)\s+(?:another\s+)?(?:the\s+)?{_DIRECTORY_RE}\s+"
        rf"(?:named|called|titled)\s+(?:{_QUOTED_LABEL}|{_BARE_LABEL})",
        rf"(?is)\b(?:into|to|in)\s+(?:another\s+)?(?:the\s+)?"
        rf"(?:{_QUOTED_LABEL}|{_BARE_LABEL})\s+{_DIRECTORY_RE}\b",
    )
    for pattern in patterns:
        value = _label(pattern, instruction)
        if value is not None and value.casefold() not in {
            "named",
            "called",
            "titled",
        }:
            return value
    return None


def requested_collection_copy(instruction: str) -> dict[str, Any] | None:
    """Parse a generic instruction that copies a collection of matching files."""
    text = str(instruction)
    if _COPY_VERB_RE.search(text) is None or _COLLECTION_RE.search(text) is None:
        return None
    extension_match = _EXTENSION_RE.search(text)
    if extension_match is None:
        return None
    source_label = _source_label(text)
    destination_label = _destination_label(text)
    source_context = bool(
        re.search(
            rf"(?is)\b(?:from|of|under|inside|within)\b.{{0,100}}"
            rf"{_DIRECTORY_RE}\b",
            text,
        )
        or re.search(r"(?is)\bcurrent\s+directory(?:\s+tree)?\b", text)
    )
    destination_context = bool(
        re.search(
            rf"(?is)\b(?:into|to|in)\b.{{0,100}}{_DIRECTORY_RE}\b",
            text,
        )
    )
    if not source_context or not destination_context:
        return None
    return {
        "pattern": f"*.{extension_match.group(1).casefold()}",
        "source_name": source_label,
        "destination_name": destination_label,
        "recursive": _RECURSIVE_RE.search(text) is not None
        or bool(re.search(r"(?is)\bcurrent\s+directory\s+tree\b", text)),
        "preserve_hierarchy": _PRESERVE_HIERARCHY_RE.search(text) is not None,
    }


def requested_copy_destinations(instruction: str) -> list[str]:
    """Return explicitly named destination directories, when the instruction lists them."""
    text = str(instruction)
    if _COPY_VERB_RE.search(text) is None:
        return []
    # Collection-copy instructions have a source directory before the copy
    # verb (for example ``the 'photos' directory ... into ... 'cpjpg'``).
    # Parse the destination from the same intent parser used by the completion
    # gate instead of scanning the first ``directory`` mention, which would
    # incorrectly constrain the copy schema to the source basename.
    intent = requested_collection_copy(text)
    if intent is not None:
        destination = intent.get("destination_name")
        if isinstance(destination, str) and destination.strip():
            return [destination.strip()]
    # For ordinary multi-destination copy instructions, only inspect the text
    # following an explicit destination preposition.  This keeps source labels
    # out of the returned list while preserving the existing quoted-label
    # contract for ``into each of the directories 'a' and 'b'``.
    match = re.search(
        r"(?is)\b(?:into|to|in)\b(?P<targets>[^.\n]*)",
        text,
    )
    if match is None:
        return []
    targets = [value.strip() for value in re.findall(_QUOTED_LABEL, match.group("targets"))]
    return list(dict.fromkeys(targets))


def parse_collection_copy_intent(instruction: str) -> dict[str, Any] | None:
    """Compatibility name for callers that prefer an explicit parser verb."""
    return requested_collection_copy(instruction)


def _result_mappings(value: Any) -> list[dict[str, Any]]:
    """Yield bounded public result-envelope layers, including context hints."""
    pending: list[Any] = [value]
    seen: set[int] = set()
    mappings: list[dict[str, Any]] = []
    for _depth in range(8):
        if not pending:
            break
        next_pending: list[Any] = []
        for item in pending:
            if not isinstance(item, dict) or id(item) in seen:
                continue
            seen.add(id(item))
            mappings.append(item)
            for key in (
                "adapter_response",
                "context_hint",
                "downstream_context",
                "response",
                "result",
            ):
                child = item.get(key)
                if isinstance(child, dict):
                    next_pending.append(child)
        pending = next_pending
    return mappings


def _normalize_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = value.strip()
    if path.startswith("file:"):
        parsed = urlparse(path)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return None
        path = unquote(parsed.path)
    elif "%" in path:
        path = unquote(path)
    if not (path.startswith("/") or path.startswith("~/")):
        return path
    return posixpath.normpath(path)


def _basename(value: Any) -> str | None:
    path = _normalize_path(value)
    if path is None:
        return None
    return posixpath.basename(path).casefold()


def _event_action(event: Any, default_domain: str) -> tuple[str, str, dict[str, Any]]:
    try:
        return effective_canonical_action(event, default_domain)
    except (AttributeError, TypeError, ValueError):
        return "", "", {}


def _successful_events(state: Any, action: str) -> list[tuple[Any, dict[str, Any]]]:
    events: list[tuple[Any, dict[str, Any]]] = []
    for event in getattr(state, "events", ()):
        proposed = getattr(event, "proposed", None)
        if not getattr(event, "executed", False) or not isinstance(proposed, dict):
            continue
        if proposed.get("kind") != "adapter" or getattr(event, "error", None):
            continue
        domain, event_action, arguments = _event_action(
            event, str(getattr(state, "domain", ""))
        )
        if event_action != action or domain not in {"os", "multi_apps"}:
            continue
        # A result explicitly reporting an error is not successful evidence,
        # even when a transport wrapper marked the event as executed.
        mappings = _result_mappings(getattr(event, "result", None))
        statuses = {item.get("status") for item in mappings}
        if "error" in statuses and "ok" not in statuses:
            continue
        events.append((event, arguments))
    return events


def _glob_matches_requested(patterns: Any, requested: str) -> bool:
    if not isinstance(patterns, list):
        return True
    requested_name = requested.casefold()
    for pattern in patterns:
        if not isinstance(pattern, str):
            continue
        normalized = pattern.strip().casefold()
        if normalized == requested_name:
            return True
        # A basename glob such as ``photo*.jpg`` still belongs to the
        # instruction's extension collection.
        if normalized.endswith(requested_name[1:]):
            return True
    return False


def _find_record(
    event: Any,
    arguments: dict[str, Any],
    intent: dict[str, Any],
) -> tuple[set[str], set[str], bool, int] | None:
    requested_pattern = str(intent["pattern"])
    path_set: set[str] = set()
    basename_set: set[str] = set()
    incomplete = False
    observed_count = 0
    mappings = _result_mappings(getattr(event, "result", None))
    for mapping in mappings:
        mapping_patterns = mapping.get("name_patterns")
        if not _glob_matches_requested(mapping_patterns, requested_pattern):
            continue
        if intent.get("recursive") and mapping.get("recursive") is False:
            continue
        kind = mapping.get("kind")
        if kind not in {None, "file", "any"}:
            continue
        matches = mapping.get("matches")
        if not isinstance(matches, list):
            continue
        local_paths: set[str] = set()
        for item in matches:
            if not isinstance(item, dict) or item.get("kind") not in {None, "file"}:
                continue
            path = _normalize_path(item.get("path"))
            if path is None or not fnmatch.fnmatchcase(
                posixpath.basename(path).casefold(), requested_pattern
            ):
                continue
            local_paths.add(path)
        if not local_paths:
            continue
        count = mapping.get("match_count")
        returned = mapping.get("returned_count")
        numeric_counts = [
            value
            for value in (count, returned)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        ]
        local_observed_count = max([len(local_paths), *numeric_counts], default=0)
        local_incomplete = (
            mapping.get("truncated") is True
            or (
                isinstance(count, int)
                and not isinstance(count, bool)
                and isinstance(returned, int)
                and not isinstance(returned, bool)
                and count > returned
            )
            or any(value > len(local_paths) for value in numeric_counts)
        )
        if local_observed_count > observed_count or (
            local_observed_count == observed_count and not local_incomplete
        ):
            path_set = local_paths
            basename_set = {posixpath.basename(path).casefold() for path in local_paths}
            observed_count = local_observed_count
            incomplete = local_incomplete
    if not path_set:
        return None
    return path_set, basename_set, incomplete, observed_count


def _copy_sources(event: Any, intent: dict[str, Any]) -> tuple[set[str], set[str]]:
    path_set: set[str] = set()
    basename_set: set[str] = set()
    requested_pattern = str(intent["pattern"])
    for mapping in _result_mappings(getattr(event, "result", None)):
        copied = mapping.get("copied")
        destination = mapping.get("destination")
        if not isinstance(copied, list):
            copied = []
        if not copied and not isinstance(destination, str):
            continue
        source_values = mapping.get("source")
        if isinstance(source_values, str):
            source_values = [source_values]
        elif not isinstance(source_values, list):
            source_values = []
        for source in source_values:
            normalized = _normalize_path(source)
            if normalized is None:
                continue
            if not fnmatch.fnmatchcase(
                posixpath.basename(normalized).casefold(), requested_pattern
            ):
                continue
            path_set.add(normalized)
            basename_set.add(posixpath.basename(normalized).casefold())
        # Some public wrappers preserve only the copied targets.  A single
        # target basename is still truthful source-set evidence when source is
        # absent; it cannot manufacture a source path or argument.
        if not source_values:
            targets = [*copied]
            if isinstance(destination, str):
                targets.append(destination)
            for target in targets:
                name = _basename(target)
                if name is not None and fnmatch.fnmatchcase(name, requested_pattern):
                    basename_set.add(name)
    return path_set, basename_set


def completion_errors(state: Any) -> list[str]:
    """Require every successful find match to appear in successful copies."""
    if str(getattr(state, "domain", "")) not in {"os", "multi_apps"}:
        return []
    intent = requested_collection_copy(str(getattr(state, "instruction", "")))
    if intent is None:
        return []
    find_records: list[
        tuple[Any, dict[str, Any], tuple[set[str], set[str], bool, int]]
    ] = []
    for event, arguments in _successful_events(state, "filesystem.find"):
        record = _find_record(event, arguments, intent)
        if record is not None:
            find_records.append((event, arguments, record))
    if not find_records:
        return []

    # Prefer the most complete observed collection; repeated searches often
    # include an earlier narrow result followed by the model's broader retry.
    (
        _find_event,
        _find_arguments,
        (
            expected_paths,
            expected_names,
            find_incomplete,
            _count,
        ),
    ) = max(
        find_records,
        key=lambda item: (len(item[2][0]), item[2][3], getattr(item[0], "step", 0)),
    )
    first_find_step = min(getattr(event, "step", 0) for event, _, _ in find_records)
    copy_records = [
        (event, _copy_sources(event, intent))
        for action in _COPY_ACTIONS
        for event, _arguments in _successful_events(state, action)
        if getattr(event, "step", 0) > first_find_step
    ]
    if not copy_records:
        return []
    copied_paths = {path for _event, (paths, _names) in copy_records for path in paths}
    copied_names = {name for _event, (_paths, names) in copy_records for name in names}

    missing_paths = expected_paths - copied_paths
    if missing_paths and len(expected_names) == len(expected_paths):
        missing_names = expected_names - copied_names
        # URL/tilde and absolute-path spellings can differ across declared
        # wrappers.  Use basename equivalence only when every expected basename
        # is unique, preserving strictness for same-name files in subfolders.
        if not missing_names:
            missing_paths = set()
    if find_incomplete:
        return [
            "filesystem.find returned a truncated or incomplete matching-file collection; "
            "repeat the model-selected find with a complete result before completion"
        ]
    if missing_paths:
        examples = sorted(missing_paths)[:8]
        remaining = len(missing_paths) - len(examples)
        return [
            "successful filesystem.copy or filesystem.copy_to_directories results do not cover every file returned "
            f"by filesystem.find; missing source paths {examples}"
            + (f" (and {remaining} more)" if remaining else "")
            + ". Copy each remaining observed source to its intended destination."
        ]
    return []


def collection_copy_path_guidance(state: Any) -> str | None:
    """Return bounded path guidance derived from observed matches and instruction."""
    intent = requested_collection_copy(str(getattr(state, "instruction", "")))
    if intent is None or not intent.get("destination_name"):
        return None
    records: list[tuple[Any, dict[str, Any], tuple[set[str], set[str], bool, int]]] = []
    for event, arguments in _successful_events(state, "filesystem.find"):
        record = _find_record(event, arguments, intent)
        if record is not None:
            records.append((event, arguments, record))
    if not records:
        return None
    _event, _arguments, (paths, _names, incomplete, _count) = max(
        records, key=lambda item: (len(item[2][0]), item[2][3], getattr(item[0], "step", 0))
    )
    if incomplete or not paths:
        return None
    try:
        common_root = posixpath.commonpath(sorted(paths))
    except ValueError:
        return None
    destination = str(intent["destination_name"])
    if not intent.get("preserve_hierarchy"):
        destination_root = posixpath.normpath(
            posixpath.join(posixpath.dirname(common_root), destination)
        )
        return (
            "This collection copy is a flat destination: copy each exact matching source file "
            f"directly into the named destination directory {destination!r}. "
            f"Resolved source root: {common_root!r}. Resolved destination root: {destination_root!r}. "
            f"Use this exact absolute destination directory, preserving only "
            "the original basename. Do not use the source directory or its basename as the destination. "
            f"MANDATORY next-call destinations value: [{destination_root!r}]. "
            "Use exactly one destination directory per source and do "
            "not append source subdirectories or create a hierarchy under the destination. "
            "The copy source must be one exact full file path from the find matches; do not "
            "pass a glob or directory. Issue one copy action per matched file."
        )
    return (
        "Observed matching files share source tree root "
        f"{common_root}. For the instruction's relative destination {destination!r}, "
        f"use {posixpath.normpath(posixpath.join(common_root, destination))!r} as the destination root "
        "and append each observed file's relative parent path to preserve hierarchy. "
        "For each source, pass exactly one destination directory: destination root joined "
        "with that source's relative parent directory; do not pass sibling directories "
        "or the destination root as additional destinations. "
        "The copy source must be one exact full file path from the find matches; do not pass a glob "
        "or directory. Issue one copy action per matched file. Use filesystem.copy_to_directories "
        "with the destination directory, or use filesystem.copy with the complete destination "
        "filename and create_parents=true when its parent does not exist."
    )


def resolved_collection_copy_destination(state: Any) -> str | None:
    """Resolve a flat collection destination from a successful public find.

    The returned path is evidence-derived: it combines the observed common
    source root with the destination name stated in the instruction.  It is
    used only to narrow the model-facing destination schema after discovery;
    model arguments are still validated and executed unchanged.
    """
    intent = requested_collection_copy(str(getattr(state, "instruction", "")))
    if intent is None or intent.get("preserve_hierarchy") or not intent.get("destination_name"):
        return None
    records: list[tuple[Any, tuple[set[str], set[str], bool, int]]] = []
    for event, _arguments in _successful_events(state, "filesystem.find"):
        record = _find_record(event, _arguments, intent)
        if record is not None:
            records.append((event, record))
    if not records:
        return None
    _event, (paths, _names, incomplete, _count) = max(
        records, key=lambda item: (len(item[1][0]), item[1][3], getattr(item[0], "step", 0))
    )
    if incomplete or not paths:
        return None
    try:
        common_root = posixpath.commonpath(sorted(paths))
    except ValueError:
        return None
    # With one observed file commonpath may be the file itself.  A destination
    # directory must always be based on its containing source directory.
    if posixpath.splitext(posixpath.basename(common_root))[1]:
        common_root = posixpath.dirname(common_root)
    destination = str(intent["destination_name"])
    if destination.startswith(("/", "~/")):
        return posixpath.normpath(destination)
    return posixpath.normpath(posixpath.join(posixpath.dirname(common_root), destination))


collection_copy_completion_errors = completion_errors


__all__ = [
    "collection_copy_completion_errors",
    "completion_errors",
    "parse_collection_copy_intent",
    "requested_collection_copy",
    "requested_copy_destinations",
    "resolved_collection_copy_destination",
]
