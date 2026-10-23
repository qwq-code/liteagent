from __future__ import annotations

import stat
import re
from pathlib import Path

from .errors import AdapterError


PERMISSION_CONVERGENCE_MAX_PASSES = 3
PERMISSION_TARGET_SAMPLE_LIMIT = 32


def parse_permission_mode(value: str) -> int:
    """Parse an unambiguous user-facing octal permission string."""
    if not isinstance(value, str) or re.fullmatch(r"[0-7]{3,4}", value) is None:
        raise AdapterError(
            "INVALID_ARGUMENT",
            "mode must be a three- or four-digit octal string such as 644 or 0755",
        )
    return int(value, 8)


def set_regular_file_permission(path: Path, *, mode: str) -> dict[str, object]:
    """Set and read back one regular file's mode without following symlinks."""
    mode_value = parse_permission_mode(mode)
    try:
        before = path.lstat()
    except FileNotFoundError:
        raise AdapterError(
            "PATH_NOT_FOUND", f"path does not exist: {path}", http_status=404
        ) from None
    if not stat.S_ISREG(before.st_mode):
        raise AdapterError(
            "INVALID_ARGUMENT", "path must identify exactly one regular file"
        )

    before_mode = stat.S_IMODE(before.st_mode)
    if before_mode != mode_value:
        path.chmod(mode_value, follow_symlinks=False)

    try:
        after = path.lstat()
    except FileNotFoundError:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the selected file disappeared while its permission mode was changed",
            {"path": str(path)},
            422,
        ) from None
    if (
        not stat.S_ISREG(after.st_mode)
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the selected file changed identity while its permission mode was changed",
            {"path": str(path)},
            422,
        )
    after_mode = stat.S_IMODE(after.st_mode)
    if after_mode != mode_value:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the selected file does not have the requested permission mode",
            {
                "path": str(path),
                "requested_mode": f"{mode_value:04o}",
                "observed_mode": f"{after_mode:04o}",
            },
            422,
        )
    return {
        "path": str(path),
        "mode": f"{mode_value:04o}",
        "mode_value": mode_value,
        "changed": before_mode != after_mode,
    }


def regular_file_targets(root: Path, *, recursive: bool) -> list[Path]:
    candidates = root.rglob("*") if recursive else root.iterdir()
    targets: list[Path] = []
    for path in sorted(candidates):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode):
            targets.append(path)
    return targets


def observe_regular_file_modes(root: Path, *, recursive: bool) -> dict[str, int]:
    observed: dict[str, int] = {}
    for path in regular_file_targets(root, recursive=recursive):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode):
            observed[str(path.relative_to(root))] = stat.S_IMODE(info.st_mode)
    return observed


def set_regular_file_permissions(
    root: Path,
    *,
    mode: str,
    recursive: bool,
) -> dict[str, object]:
    mode_value = parse_permission_mode(mode)
    changed_paths: set[Path] = set()
    vanished_paths: set[Path] = set()
    skipped_non_regular_paths: set[Path] = set()
    observed: dict[str, int] = {}
    completed_passes = 0

    for pass_index in range(PERMISSION_CONVERGENCE_MAX_PASSES):
        completed_passes = pass_index + 1
        targets = regular_file_targets(root, recursive=recursive)
        if not targets and not observed:
            raise AdapterError(
                "NO_MATCHES",
                "the selected directory contains no regular files in the requested scope",
                {
                    "root": str(root),
                    "recursive": recursive,
                    "vanished_count": len(vanished_paths),
                    "skipped_non_regular_count": len(skipped_non_regular_paths),
                },
                404,
            )

        for path in targets:
            try:
                before = path.lstat()
                if not stat.S_ISREG(before.st_mode):
                    skipped_non_regular_paths.add(path)
                    continue
                before_mode = stat.S_IMODE(before.st_mode)
                if before_mode != mode_value:
                    path.chmod(mode_value, follow_symlinks=False)
                after = path.lstat()
            except FileNotFoundError:
                vanished_paths.add(path)
                continue
            if not stat.S_ISREG(after.st_mode):
                skipped_non_regular_paths.add(path)
                continue
            after_mode = stat.S_IMODE(after.st_mode)
            if after_mode != mode_value:
                raise AdapterError(
                    "VERIFICATION_FAILED",
                    "one or more processed regular files do not have the requested permission mode",
                    {
                        "path": str(path),
                        "requested_mode": f"{mode_value:04o}",
                        "observed_mode": f"{after_mode:04o}",
                    },
                    422,
                )
            if before_mode != mode_value:
                changed_paths.add(path)

        observed = observe_regular_file_modes(root, recursive=recursive)
        mismatched = {
            path: observed_mode
            for path, observed_mode in observed.items()
            if observed_mode != mode_value
        }
        if not mismatched:
            break
    else:
        mismatch_samples = dict(
            sorted(mismatched.items())[:PERMISSION_TARGET_SAMPLE_LIMIT]
        )
        raise AdapterError(
            "VERIFICATION_FAILED",
            "the regular-file tree did not converge to the requested permission mode",
            {
                "root": str(root),
                "requested_mode": f"{mode_value:04o}",
                "convergence_passes": completed_passes,
                "mismatched_count": len(mismatched),
                "mismatched_samples": mismatch_samples,
                "mismatched_samples_truncated": len(mismatched)
                > PERMISSION_TARGET_SAMPLE_LIMIT,
            },
            422,
        )

    if not observed:
        raise AdapterError(
            "NO_MATCHES",
            "no regular files remained in the requested scope at verification time",
            {
                "root": str(root),
                "recursive": recursive,
                "vanished_count": len(vanished_paths),
                "skipped_non_regular_count": len(skipped_non_regular_paths),
            },
            404,
        )

    observed_paths = sorted(root / relative for relative in observed)
    observed_path_set = set(observed_paths)
    target_samples = observed_paths[:PERMISSION_TARGET_SAMPLE_LIMIT]

    return {
        "root": str(root),
        "mode": f"{mode_value:04o}",
        "mode_value": mode_value,
        "recursive": recursive,
        "target_type": "regular_files",
        "target_count": len(observed),
        "changed_count": len(changed_paths & observed_path_set),
        "vanished_count": len(vanished_paths),
        "skipped_non_regular_count": len(skipped_non_regular_paths),
        "convergence_passes": completed_passes,
        "targets": [str(path) for path in target_samples],
        "targets_truncated": len(observed_paths) > PERMISSION_TARGET_SAMPLE_LIMIT,
        "targets_omitted": max(0, len(observed_paths) - len(target_samples)),
    }


__all__ = [
    "PERMISSION_CONVERGENCE_MAX_PASSES",
    "PERMISSION_TARGET_SAMPLE_LIMIT",
    "observe_regular_file_modes",
    "parse_permission_mode",
    "regular_file_targets",
    "set_regular_file_permission",
    "set_regular_file_permissions",
]
