"""Keep a complete age-organization file inventory actionable."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .completion_policy import effective_canonical_action


def _age_organization_instruction(instruction: str) -> bool:
    text = instruction.casefold()
    return all(
        re.search(pattern, text)
        for pattern in (
            r"\b(?:compress|archive|gzip)\b",
            r"\b(?:move|organize)\b",
            r"\b(?:modified|older|newer)\b",
        )
    )


def _complete_dated_inventory(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    hint = result.get("context_hint")
    if not isinstance(hint, dict):
        return False
    matches = hint.get("matches")
    count = hint.get("match_count")
    return bool(
        type(count) is int
        and count > 0
        and hint.get("returned_count") == count
        and hint.get("truncated") is False
        and isinstance(matches, list)
        and len(matches) == count
        and all(
            isinstance(item, dict)
            and item.get("kind") == "file"
            and isinstance(item.get("path"), str)
            and isinstance(item.get("modified_at"), str)
            and item["modified_at"]
            for item in matches
        )
    )


def _named_destination(instruction: str, verb: str, preposition: str) -> str | None:
    match = re.search(
        rf"(?i)\b{verb}\b.{{0,100}}?\b{preposition}\s+[\"']?(/[^\s\"']+)",
        instruction,
    )
    if not match:
        return None
    return str(PurePosixPath(match.group(1).rstrip(".,;")))


def _inside(path: str, directory: str) -> bool:
    return path != directory and str(PurePosixPath(path)).startswith(directory + "/")


def age_organization_complete(state: Any) -> bool:
    """All discovered sources have matching, read-back-verified destinations."""
    if getattr(state, "domain", None) != "os" or not _age_organization_instruction(
        str(getattr(state, "instruction", ""))
    ):
        return False
    instruction = state.instruction
    old_dir = _named_destination(
        instruction, "(?:put|place)", "(?:in|into)"
    ) or _named_destination(instruction, "compress", "(?:into|to)")
    new_dir = _named_destination(instruction, "move", "to")
    if not old_dir or not new_dir or old_dir == new_dir:
        return False
    events = getattr(state, "events", ())
    initial = next(
        (
            event
            for event in events
            if getattr(event, "executed", False)
            and not getattr(event, "error", None)
            and effective_canonical_action(event, state.domain)[:2]
            == ("os", "filesystem.find")
            and _complete_dated_inventory(getattr(event, "result", None))
        ),
        None,
    )
    if initial is None:
        return False
    initial_paths = {
        item["path"] for item in initial.result["context_hint"]["matches"]
    }
    if len(initial_paths) != len(initial.result["context_hint"]["matches"]):
        return False
    compressed: dict[str, str] = {}
    last_compression_step = 0
    for event in events:
        if not getattr(event, "executed", False) or getattr(event, "error", None):
            continue
        _domain, action, arguments = effective_canonical_action(event, state.domain)
        if action != "archive.compress_file":
            continue
        source = arguments.get("source")
        destination = arguments.get("destination")
        if (
            isinstance(source, str)
            and isinstance(destination, str)
            and source in initial_paths
            and _inside(destination, old_dir)
            and arguments.get("remove_source") is True
        ):
            compressed[source] = destination
            last_compression_step = max(last_compression_step, event.step)
    if not compressed:
        return False
    if any(
        path not in compressed and not _inside(path, new_dir)
        for path in initial_paths
    ):
        return False
    expected = {compressed.get(path, path) for path in initial_paths}
    latest = events[-1] if events else None
    return bool(
        latest is not None
        and getattr(latest, "step", 0) > last_compression_step
        and getattr(latest, "executed", False)
        and not getattr(latest, "error", None)
        and effective_canonical_action(latest, state.domain)[:2]
        == ("os", "filesystem.find")
        and _complete_dated_inventory(getattr(latest, "result", None))
        and {
            item["path"] for item in latest.result["context_hint"]["matches"]
        } == expected
    )


def constrain_age_organization_find_tools(
    tools: list[dict[str, Any]], state: Any
) -> list[dict[str, Any]]:
    """Handoff from one complete file inventory to available mutation tools."""
    if getattr(state, "domain", None) != "os" or not _age_organization_instruction(
        str(getattr(state, "instruction", ""))
    ):
        return tools
    selected = {
        tool.get("function", {}).get("name")
        for tool in tools
        if isinstance(tool.get("function"), dict)
    }
    if not {"adapter__archive_compress_file", "adapter__filesystem_rename"}.issubset(
        selected
    ):
        return tools
    events = getattr(state, "events", ())
    if not events:
        return tools
    latest = events[-1]
    domain, action, arguments = effective_canonical_action(latest, state.domain)
    if domain != "os" or action != "filesystem.find":
        return tools
    if (
        not getattr(latest, "executed", False)
        or getattr(latest, "error", None)
        or not _complete_dated_inventory(getattr(latest, "result", None))
    ):
        return tools
    roots = arguments.get("roots")
    if not isinstance(roots, list) or not roots or not all(
        isinstance(root, str) and root in state.instruction for root in roots
    ):
        return tools
    return [
        tool
        for tool in tools
        if tool.get("function", {}).get("name")
        not in {"adapter__filesystem_find", "tools_search"}
    ]
