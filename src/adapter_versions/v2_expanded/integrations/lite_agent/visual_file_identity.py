"""Follow observed image identities through successful single-file renames."""
from __future__ import annotations

from pathlib import PurePosixPath
from posixpath import normpath
from typing import Any

from .completion_policy import effective_canonical_action


_IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_IDENTITY_FIELDS = ("sha256", "size_bytes", "modified_at")


def _matches(value: Any):
    if isinstance(value, dict):
        for match in value.get("matches", []) if isinstance(value.get("matches"), list) else []:
            if isinstance(match, dict):
                yield match
        for child in value.values():
            yield from _matches(child)
    elif isinstance(value, list):
        for child in value:
            yield from _matches(child)


def pending_visual_image(state) -> tuple[str | None, bool]:
    """Return the next observed image and whether this identity was opened.

    A rename moves the record to its resulting path. A later find can create a
    new record at the old path or invalidate it when comparable metadata changes.
    Metadata is evidence of change, not a guarantee of byte-for-byte identity.
    """
    records: dict[str, dict[str, Any]] = {}
    for event in state.events:
        if not event.executed or event.error:
            continue
        result = event.result if isinstance(event.result, dict) else {}
        hint = result.get("context_hint") or {}
        if not isinstance(hint, dict):
            hint = {}
        context = hint.get("downstream_context") or {}
        if not isinstance(context, dict):
            context = {}
        if hint.get("verification_passed") is False or context.get("verification_passed") is False:
            continue
        adapter, action, arguments = effective_canonical_action(event, state.domain)
        if adapter != "os":
            continue
        params = arguments.get("params", arguments)
        if not isinstance(params, dict):
            continue
        if action == "filesystem.find":
            for match in _matches(result):
                path = match.get("path")
                if (not isinstance(path, str) or match.get("kind") != "file"
                        or PurePosixPath(path).suffix.casefold() not in _IMAGE_SUFFIXES):
                    continue
                path = normpath(path)
                identity = {key: match[key] for key in _IDENTITY_FIELDS if match.get(key) is not None}
                prior = records.get(path)
                changed = prior and any(
                    key in prior["identity"] and prior["identity"][key] != value
                    for key, value in identity.items()
                )
                if prior is None or changed:
                    records[path] = {"identity": identity, "opened": False, "renamed": False}
                else:
                    prior["identity"].update(identity)
        elif action == "desktop.open_path":
            path = context.get("path") or params.get("path")
            if isinstance(path, str) and normpath(path) in records:
                records[normpath(path)]["opened"] = True
        elif action == "filesystem.rename":
            if context.get("moved") is False:
                continue
            source = context.get("source") or params.get("source")
            destination = context.get("destination") or params.get("destination")
            if not isinstance(source, str) or not isinstance(destination, str):
                continue
            source = normpath(source)
            if source not in records:
                continue
            if "/" not in destination:
                destination = str(PurePosixPath(source).parent / destination)
            destination = normpath(destination)
            if not destination.startswith("/") or destination == source:
                continue
            record = records.pop(source)
            record["renamed"] = True
            records[destination] = record
    for path, record in records.items():
        if not record["renamed"]:
            return path, record["opened"]
    return None, False
