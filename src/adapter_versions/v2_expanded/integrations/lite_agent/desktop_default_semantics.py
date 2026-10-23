"""Generic intent detection for desktop default-application associations."""

from __future__ import annotations

import re


def requests_default_application(instruction: str) -> bool:
    """Return whether the user explicitly requests a default application change."""
    normalized = re.sub(r"[-_]", " ", instruction.casefold())
    if re.search(r"\bdefault\b", normalized) is None:
        return False
    if (
        re.search(
            r"\b(?:app|application|browser|editor|handler|player|program|viewer)\b",
            normalized,
        )
        is None
    ):
        return False
    return bool(
        re.search(
            r"\b(?:assign|change|choose|configure|make|set|switch|use)\b",
            normalized,
        )
        or re.search(
            r"\bas\s+(?:my|the|your)?\s*default\b|\bdefault\b.{0,48}\bto\b",
            normalized,
        )
    )
