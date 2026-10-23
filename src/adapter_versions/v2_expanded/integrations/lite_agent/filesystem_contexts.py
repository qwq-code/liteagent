from __future__ import annotations

from typing import Any


def filesystem_rename_context(
    result: dict[str, Any], verification: Any
) -> dict[str, Any]:
    source = result.get("source")
    destination = result.get("destination")
    return {
        "source": source,
        "destination": destination,
        "moved": bool(source and destination),
        "verification_passed": (
            verification.get("passed") if isinstance(verification, dict) else None
        ),
        "guidance": (
            "The source was renamed to destination and the destination path was verified. "
            "Treat moved and verification_passed as completion evidence; do not repeat the "
            "rename or search for the old basename unless the instruction requires another "
            "file operation."
        ),
    }


def filesystem_permission_context(
    result: dict[str, Any], verification: Any
) -> dict[str, Any]:
    return {
        key: result.get(key)
        for key in (
            "root",
            "cwd_source",
            "mode",
            "recursive",
            "target_type",
            "target_count",
            "changed_count",
            "vanished_count",
            "skipped_non_regular_count",
            "convergence_passes",
            "targets_truncated",
            "targets_omitted",
        )
    } | {
        "verification_passed": (
            verification.get("passed") if isinstance(verification, dict) else None
        ),
        "guidance": (
            "Every regular file still present in the verified scope has the requested mode; files "
            "that disappeared during traversal are counted separately, and directories and symbolic "
            "links were left unchanged. Treat target_count and verification_passed as final structural "
            "evidence and propose completion instead of searching or repeating chmod."
        ),
    }
