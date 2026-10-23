from __future__ import annotations

from typing import Any

from .errors import AdapterError


EXCLUSION_SCOPES = frozenset({"any_depth", "workspace_root"})


def exclusion_setting(
    pattern: str,
    scope: str,
    hidden: bool,
) -> tuple[str, dict[str, Any]]:
    normalized = pattern.strip()
    if not normalized:
        raise AdapterError("INVALID_REQUEST", "params.pattern must be non-empty")
    if scope not in EXCLUSION_SCOPES:
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.scope must be one of {sorted(EXCLUSION_SCOPES)}",
        )
    if scope == "any_depth" and not normalized.startswith("**/"):
        normalized = f"**/{normalized.lstrip('/')}"
    return normalized, {"files.exclude": {normalized: hidden}}
