from __future__ import annotations

from collections import deque
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


SPREADSHEET_SUFFIXES = frozenset({".csv", ".ods", ".xlsx"})
PATH_SCAN_MAX_DEPTH = 4
PATH_SCAN_MAX_DIRECTORIES = 256
PATH_SCAN_MAX_RESULTS = 8


def _requested_basename(value: str) -> str:
    if value.startswith("file://"):
        return Path(unquote(urlparse(value).path)).name
    return Path(value).name


def _requested_path_parts(value: str) -> tuple[str, ...]:
    path = unquote(urlparse(value).path) if value.startswith("file://") else value
    return tuple(part.casefold() for part in Path(path).parts)


def _rank_path_candidates(
    requested_path: str,
    candidates: list[str],
) -> tuple[list[str], list[dict[str, Any]], str | None, str | None]:
    requested_parts = _requested_path_parts(requested_path)
    scored: list[tuple[str, int]] = []
    for candidate in candidates:
        candidate_parts = tuple(part.casefold() for part in Path(candidate).parts)
        suffix_matches = 0
        for requested_part, candidate_part in zip(
            reversed(requested_parts), reversed(candidate_parts), strict=False
        ):
            if requested_part != candidate_part:
                break
            suffix_matches += 1
        scored.append((candidate, suffix_matches))
    scored.sort(key=lambda item: (-item[1], item[0].casefold(), item[0]))
    preferred = None
    reason = None
    if len(scored) == 1:
        preferred = scored[0][0]
        reason = (
            "only_exact_basename_candidate"
            if Path(preferred).name == _requested_basename(requested_path)
            else "only_case_insensitive_basename_candidate"
        )
    elif len(scored) > 1 and scored[0][1] > 1 and scored[0][1] > scored[1][1]:
        preferred = scored[0][0]
        reason = "unique_longest_case_insensitive_path_suffix"
    return (
        [path for path, _score in scored],
        [
            {"path": path, "case_insensitive_suffix_components": score}
            for path, score in scored
        ],
        preferred,
        reason,
    )


def _find_exact_basename_candidates(
    requested_path: str,
    *,
    home: Path | None = None,
    allowed_file_suffixes: frozenset[str] | None = None,
    include_directories: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    root = (home or Path.home()).resolve()
    basename = _requested_basename(requested_path)
    exact_candidates: list[str] = []
    casefold_candidates: list[str] = []
    directories: deque[tuple[Path, int]] = deque([(root, 0)])
    directories_scanned = 0
    directory_errors = 0
    stopped_at_result_limit = False
    casefold_result_limit_reached = False

    while directories and directories_scanned < PATH_SCAN_MAX_DIRECTORIES:
        directory, depth = directories.popleft()
        directories_scanned += 1
        try:
            entries = sorted(
                os.scandir(directory),
                key=lambda entry: (entry.name.casefold(), entry.name),
            )
        except OSError:
            directory_errors += 1
            continue

        for entry in entries:
            try:
                is_file = entry.is_file(follow_symlinks=False)
                is_directory = entry.is_dir(follow_symlinks=False)
                file_matches = is_file and (
                    allowed_file_suffixes is None
                    or Path(entry.name).suffix.casefold() in allowed_file_suffixes
                )
                eligible = file_matches or (include_directories and is_directory)
                if eligible and entry.name == basename:
                    exact_candidates.append(str(Path(entry.path).resolve()))
                    if len(exact_candidates) >= PATH_SCAN_MAX_RESULTS:
                        stopped_at_result_limit = True
                        break
                elif eligible and entry.name.casefold() == basename.casefold():
                    if len(casefold_candidates) < PATH_SCAN_MAX_RESULTS:
                        casefold_candidates.append(str(Path(entry.path).resolve()))
                    if len(casefold_candidates) >= PATH_SCAN_MAX_RESULTS:
                        casefold_result_limit_reached = True
                if (
                    depth < PATH_SCAN_MAX_DEPTH
                    and not entry.name.startswith(".")
                    and is_directory
                ):
                    directories.append((Path(entry.path), depth + 1))
            except OSError:
                continue
        if stopped_at_result_limit:
            break

    # Preserve exact-case behavior whenever any exact basename exists. A bounded
    # case-insensitive fallback is returned only when exact discovery found nothing;
    # callers still require the model to select and explicitly retry a returned path.
    candidates = exact_candidates or casefold_candidates
    scan = {
        "root": str(root),
        "exact_basename": basename,
        "max_depth": PATH_SCAN_MAX_DEPTH,
        "max_directories": PATH_SCAN_MAX_DIRECTORIES,
        "directories_scanned": directories_scanned,
        "directory_errors": directory_errors,
        "directory_limit_reached": bool(
            directories and directories_scanned >= PATH_SCAN_MAX_DIRECTORIES
        ),
        "max_results": PATH_SCAN_MAX_RESULTS,
        "result_limit_reached": (
            stopped_at_result_limit
            if exact_candidates
            else casefold_result_limit_reached
        ),
    }
    return candidates, scan


def find_spreadsheet_path_candidates(
    requested_path: str,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Find exact-first basename spreadsheet candidates for an explicit retry."""
    candidates, scan = _find_exact_basename_candidates(
        requested_path,
        home=home,
        allowed_file_suffixes=SPREADSHEET_SUFFIXES,
    )
    candidates, path_matches, preferred, preferred_reason = _rank_path_candidates(
        requested_path, candidates
    )
    return {
        "candidate_spreadsheet_paths": candidates,
        "candidate_spreadsheet_path": preferred,
        "candidate_path_matches": path_matches,
        "candidate_path_preference_reason": preferred_reason,
        "candidate_count_returned": len(candidates),
        "selection_required": True,
        "explicit_retry_required": True,
        "retry_options": [
            {"action": "spreadsheet.read_file", "path": path} for path in candidates
        ],
        "scan": scan,
    }


def find_open_path_candidates(
    requested_path: str,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Find exact-first basename candidates for an explicit open retry."""
    candidates, scan = _find_exact_basename_candidates(
        requested_path,
        home=home,
        include_directories=True,
    )
    candidates, path_matches, preferred, preferred_reason = _rank_path_candidates(
        requested_path, candidates
    )
    return {
        "candidate_paths": candidates,
        "candidate_path": preferred,
        "candidate_path_matches": path_matches,
        "candidate_path_preference_reason": preferred_reason,
        "candidate_count_returned": len(candidates),
        "selection_required": True,
        "explicit_retry_required": True,
        "retry_options": [
            {"action": "desktop.open_path", "path": path} for path in candidates
        ],
        "scan": scan,
    }


def find_file_path_candidates(
    requested_path: str,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Find exact-first basename file candidates for an explicit read retry."""
    candidates, scan = _find_exact_basename_candidates(
        requested_path,
        home=home,
    )
    candidates, path_matches, preferred, preferred_reason = _rank_path_candidates(
        requested_path, candidates
    )
    return {
        "candidate_file_paths": candidates,
        "candidate_file_path": preferred,
        "candidate_path_matches": path_matches,
        "candidate_path_preference_reason": preferred_reason,
        "candidate_count_returned": len(candidates),
        "selection_required": True,
        "explicit_retry_required": True,
        "retry_options": [
            {"action": "file.read_text", "path": path} for path in candidates
        ],
        "scan": scan,
    }
