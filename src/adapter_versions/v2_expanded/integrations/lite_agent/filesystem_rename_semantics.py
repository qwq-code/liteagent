"""Generic intent detection for filesystem rename operations."""

from __future__ import annotations

import re


_FILESYSTEM_OBJECT = re.compile(
    r"\b(?:archive|directory|document|file|folder|item|path)\b",
    re.IGNORECASE,
)


def requests_filesystem_rename(instruction: str) -> bool:
    """Return whether an OS instruction explicitly renames a filesystem object."""
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    if _FILESYSTEM_OBJECT.search(normalized) is None:
        return False
    if re.search(r"\brenam(?:e|ed|ing)\b", normalized):
        return True
    return bool(
        re.search(
            r"\b(?:change|modify|update)\b.{0,48}\b(?:its|the|this|that)?\s*name\b",
            normalized,
        )
        or re.search(
            r"\bname\b.{0,48}\b(?:chang(?:e|ed|ing)|modif(?:y|ied|ying)|"
            r"updat(?:e|ed|ing))\b",
            normalized,
        )
    )


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return only the public action name; model-facing arguments remain unparsed."""
    if domain != "os" or not requests_filesystem_rename(instruction):
        return []
    return ["filesystem.rename"]


__all__ = ["requests_filesystem_rename", "required_actions"]
