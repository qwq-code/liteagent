from __future__ import annotations

import re


_COMMIT_RE = re.compile(r"(?i)\bcommit(?:ted|ting)?\b")
_PUSH_RE = re.compile(r"(?i)\bpush(?:ed|ing)?\b")


def required_actions(domain: str, instruction: str) -> list[str]:
    """Recall the generic command primitive without extracting Git arguments."""
    if (
        domain == "os"
        and _COMMIT_RE.search(instruction) is not None
        and _PUSH_RE.search(instruction) is not None
    ):
        return ["command.run"]
    return []
