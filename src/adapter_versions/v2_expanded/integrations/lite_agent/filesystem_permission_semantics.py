"""Generic intent detection for regular-file permission changes."""

from __future__ import annotations

import re


_FILESYSTEM_SCOPE = re.compile(
    r"\b(?:director(?:y|ies)|file(?:s)?|folder(?:s)?|path|tree)\b",
    re.IGNORECASE,
)
_MUTATION = re.compile(
    r"\b(?:apply|change|chmod|modify|set|update)\b",
    re.IGNORECASE,
)
_PERMISSION = re.compile(
    r"\b(?:access\s+mode|file\s+mode|mode|permission(?:s)?)\b",
    re.IGNORECASE,
)


def requests_filesystem_permission_change(instruction: str) -> bool:
    """Return whether an OS instruction explicitly mutates filesystem permissions."""
    normalized = re.sub(r"[-_]+", " ", instruction)
    return bool(
        _FILESYSTEM_SCOPE.search(normalized)
        and _MUTATION.search(normalized)
        and (
            _PERMISSION.search(normalized) or re.search(r"\bchmod\b", normalized, re.I)
        )
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return the atomic discovery and per-file permission actions."""
    if domain != "os" or not requests_filesystem_permission_change(instruction):
        return []
    return ["filesystem.find", "filesystem.set_permissions"]


__all__ = ["requests_filesystem_permission_change", "required_actions"]
