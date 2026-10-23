"""Discover files from the currently active VS Code workspace."""

from __future__ import annotations

from collections import deque
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .command import CommandRunner
from .errors import AdapterError


_ACTIVE_WINDOW_RE = re.compile(r"window id #\s*(0x[0-9a-f]+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'^(?:_NET_WM_NAME|WM_NAME)\([^)]*\)\s*=\s*"(.*)"$', re.MULTILINE
)
_CLASS_RE = re.compile(r"^WM_CLASS\([^)]*\)\s*=\s*(.*)$", re.MULTILINE)
_QUOTED_RE = re.compile(r'"((?:\\.|[^"\\])*)"')
_VSCODE_SUFFIX_RE = re.compile(
    r"\s+-\s+(?:Visual Studio Code|Code - OSS|VSCodium)$", re.IGNORECASE
)
_WORKSPACE_LABEL_RE = re.compile(r"\s+\(Workspace\)$", re.IGNORECASE)
_IGNORED_DIRECTORIES = frozenset(
    {
        ".cache",
        ".config",
        ".local",
        ".mozilla",
        ".npm",
        ".vscode",
        "node_modules",
    }
)


def _unescape_x_property(value: str) -> str:
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def _active_vscode_window(runner: CommandRunner) -> tuple[str, str, tuple[str, ...]]:
    if shutil.which("xprop") is None:
        raise AdapterError(
            "WORKSPACE_UNAVAILABLE",
            "xprop is unavailable, so the active VS Code workspace cannot be inspected",
            http_status=422,
        )
    root = runner.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"], check=False, timeout=5)
    match = _ACTIVE_WINDOW_RE.search(root["stdout"])
    if root["returncode"] != 0 or match is None or match.group(1) == "0x0":
        raise AdapterError(
            "WORKSPACE_UNAVAILABLE",
            "no focused desktop window is observable",
            {"xprop": root["stdout"].strip() or root["stderr"].strip()},
            422,
        )
    window_id = match.group(1)
    properties = runner.run(
        ["xprop", "-id", window_id, "_NET_WM_NAME", "WM_NAME", "WM_CLASS"],
        check=False,
        timeout=5,
    )
    if properties["returncode"] != 0:
        raise AdapterError(
            "WORKSPACE_UNAVAILABLE",
            "the focused window properties could not be read",
            {"window_id": window_id, "stderr": properties["stderr"].strip()},
            422,
        )
    title_match = _TITLE_RE.search(properties["stdout"])
    class_match = _CLASS_RE.search(properties["stdout"])
    title = _unescape_x_property(title_match.group(1)) if title_match else ""
    classes = (
        tuple(
            _unescape_x_property(value)
            for value in _QUOTED_RE.findall(class_match.group(1))
        )
        if class_match
        else ()
    )
    if not any(
        value.casefold() in {"code", "code-oss", "vscodium"}
        or "visual studio code" in value.casefold()
        for value in classes
    ):
        raise AdapterError(
            "WORKSPACE_UNAVAILABLE",
            "the focused window is not VS Code",
            {"window_id": window_id, "title": title, "window_classes": list(classes)},
            422,
        )
    return window_id, title.strip(), classes


def workspace_name_from_title(title: str) -> str | None:
    """Extract the displayed workspace name from a normal VS Code window title."""
    normalized = _VSCODE_SUFFIX_RE.sub("", title.strip()).strip()
    if not normalized or normalized.casefold() in {
        "visual studio code",
        "code - oss",
        "vscodium",
    }:
        return None
    parts = [part.strip() for part in normalized.split(" - ") if part.strip()]
    observed = parts[-1].lstrip("\u25cf ").strip()
    return _WORKSPACE_LABEL_RE.sub("", observed).strip() or None


def _path_from_file_uri(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme != "file":
        return None
    raw = unquote(parsed.path) if parsed.scheme == "file" else value
    if not raw.startswith("/"):
        return None
    return Path(raw).resolve()


def _workspace_file_roots(path: Path) -> list[Path]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return []
    folders = payload.get("folders") if isinstance(payload, dict) else None
    if not isinstance(folders, list):
        return []
    roots: list[Path] = []
    for folder in folders:
        if not isinstance(folder, dict):
            continue
        candidate = _path_from_file_uri(folder.get("uri"))
        if candidate is None and isinstance(folder.get("path"), str):
            candidate = Path(folder["path"]).expanduser()
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            candidate = candidate.resolve()
        if candidate is not None and candidate.is_dir():
            roots.append(candidate)
    return list(dict.fromkeys(roots))


def _stored_workspace_candidates(storage_root: Path) -> list[tuple[str, list[Path]]]:
    candidates: list[tuple[str, list[Path]]] = []
    if not storage_root.is_dir():
        return candidates
    for metadata_path in sorted(storage_root.glob("*/workspace.json")):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        folder = _path_from_file_uri(payload.get("folder"))
        if folder is not None and folder.is_dir():
            candidates.append((folder.name, [folder]))
            continue
        workspace_file = _path_from_file_uri(payload.get("workspace"))
        if workspace_file is None or not workspace_file.is_file():
            continue
        roots = _workspace_file_roots(workspace_file)
        if roots:
            candidates.append((workspace_file.stem, roots))
    return candidates


def _stored_workspace_file_candidates(storage_root: Path) -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    if not storage_root.is_dir():
        return candidates
    for metadata_path in sorted(storage_root.glob("*/workspace.json")):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        workspace_file = _path_from_file_uri(payload.get("workspace"))
        if (
            workspace_file is not None
            and workspace_file.suffix == ".code-workspace"
            and workspace_file.is_file()
        ):
            candidates.append((workspace_file.stem, workspace_file))
    return candidates


def _find_named_directories(
    name: str,
    roots: Iterable[Path],
    *,
    max_depth: int = 5,
    max_directories: int = 1024,
) -> list[Path]:
    matches: set[Path] = set()
    queue = deque(
        (root.expanduser().resolve(), 0) for root in roots if root.expanduser().is_dir()
    )
    scanned = 0
    while queue and scanned < max_directories:
        directory, depth = queue.popleft()
        scanned += 1
        if directory.name.casefold() == name.casefold():
            matches.add(directory)
        if depth >= max_depth:
            continue
        try:
            children = sorted(
                directory.iterdir(), key=lambda item: item.name.casefold()
            )
        except (FileNotFoundError, OSError, PermissionError):
            continue
        for child in children:
            try:
                if (
                    child.is_dir()
                    and not child.is_symlink()
                    and child.name not in _IGNORED_DIRECTORIES
                ):
                    queue.append((child.resolve(), depth + 1))
            except (FileNotFoundError, OSError, PermissionError):
                continue
    return sorted(matches, key=str)


def resolve_active_workspace(
    runner: CommandRunner,
    *,
    home: Path | None = None,
    storage_root: Path | None = None,
    search_roots: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Resolve active workspace roots only from observable VS Code state."""
    home_directory = (home or Path.home()).expanduser().resolve()
    window_id, title, classes = _active_vscode_window(runner)
    observed_name = workspace_name_from_title(title)
    if observed_name is None:
        raise AdapterError(
            "WORKSPACE_UNAVAILABLE",
            "the active VS Code title does not expose a workspace name",
            {"window_id": window_id, "title": title},
            422,
        )

    stored = _stored_workspace_candidates(
        storage_root
        or home_directory / ".config" / "Code" / "User" / "workspaceStorage"
    )
    matching_stored = [
        roots for name, roots in stored if name.casefold() == observed_name.casefold()
    ]
    unique_stored = {
        tuple(str(root.resolve()) for root in roots): roots for roots in matching_stored
    }
    if len(unique_stored) == 1:
        workspace_roots = next(iter(unique_stored.values()))
        source = "workspace_storage"
    elif len(unique_stored) > 1:
        raise AdapterError(
            "WORKSPACE_AMBIGUOUS",
            "multiple stored workspaces match the active VS Code title",
            {
                "workspace_name": observed_name,
                "candidates": [list(paths) for paths in sorted(unique_stored)],
            },
            409,
        )
    else:
        bounded_roots = list(search_roots or [home_directory])
        matches = _find_named_directories(observed_name, bounded_roots)
        if len(matches) != 1:
            raise AdapterError(
                "WORKSPACE_AMBIGUOUS" if matches else "WORKSPACE_UNAVAILABLE",
                (
                    "multiple directories match the active VS Code workspace name"
                    if matches
                    else "the active VS Code workspace directory could not be resolved"
                ),
                {
                    "workspace_name": observed_name,
                    "candidates": [str(path) for path in matches],
                    "searched_roots": [str(path) for path in bounded_roots],
                },
                409 if matches else 422,
            )
        workspace_roots = matches
        source = "bounded_title_match"

    return {
        "window_id": window_id,
        "window_title": title,
        "window_classes": list(classes),
        "workspace_name": observed_name,
        "workspace_roots": [str(path) for path in workspace_roots],
        "resolution_source": source,
    }


def resolve_active_workspace_file(
    runner: CommandRunner,
    *,
    home: Path | None = None,
    storage_root: Path | None = None,
) -> dict[str, Any]:
    """Resolve the active multi-root workspace file from observable VS Code state."""
    home_directory = (home or Path.home()).expanduser().resolve()
    window_id, title, classes = _active_vscode_window(runner)
    observed_name = workspace_name_from_title(title)
    if observed_name is None:
        raise AdapterError(
            "WORKSPACE_UNAVAILABLE",
            "the active VS Code title does not expose a workspace name",
            {"window_id": window_id, "title": title},
            422,
        )

    candidates = _stored_workspace_file_candidates(
        storage_root
        or home_directory / ".config" / "Code" / "User" / "workspaceStorage"
    )
    matches = {
        str(path.resolve()): path.resolve()
        for name, path in candidates
        if name.casefold() == observed_name.casefold()
    }
    if len(matches) != 1:
        raise AdapterError(
            "WORKSPACE_AMBIGUOUS" if matches else "WORKSPACE_UNAVAILABLE",
            (
                "multiple workspace files match the active VS Code title"
                if matches
                else "the active VS Code workspace file could not be resolved"
            ),
            {
                "workspace_name": observed_name,
                "candidates": sorted(matches),
            },
            409 if matches else 422,
        )
    workspace_file = next(iter(matches.values()))
    return {
        "window_id": window_id,
        "window_title": title,
        "window_classes": list(classes),
        "workspace_name": observed_name,
        "workspace_file": str(workspace_file),
        "workspace_roots": [
            str(path) for path in _workspace_file_roots(workspace_file)
        ],
        "resolution_source": "workspace_storage",
    }


def find_workspace_files(
    workspace: dict[str, Any], params: dict[str, Any]
) -> dict[str, Any]:
    """Find entries beneath resolved workspace roots using model-selected globs."""
    patterns = params["name_patterns"]
    kind = params.get("kind", "file")
    recursive = bool(params.get("recursive", True))
    include_hidden = bool(params.get("include_hidden", False))
    max_depth = int(params.get("max_depth", 8))
    max_results = int(params.get("max_results", 200))
    matches: dict[Path, dict[str, Any]] = {}
    scanned_entries = 0

    for raw_root in workspace["workspace_roots"]:
        root = Path(raw_root)
        queue = deque([(root, 0)])
        while queue:
            directory, depth = queue.popleft()
            try:
                entries = sorted(
                    directory.iterdir(), key=lambda path: path.name.casefold()
                )
            except (FileNotFoundError, OSError, PermissionError):
                continue
            for entry in entries:
                if not include_hidden and entry.name.startswith("."):
                    continue
                scanned_entries += 1
                try:
                    is_directory = entry.is_dir()
                    is_file = entry.is_file()
                    is_symlink = entry.is_symlink()
                except (FileNotFoundError, OSError, PermissionError):
                    continue
                if any(fnmatchcase(entry.name, pattern) for pattern in patterns):
                    kind_matches = (
                        kind == "any"
                        or (kind == "file" and is_file)
                        or (kind == "directory" and is_directory)
                    )
                    if kind_matches:
                        try:
                            resolved = entry.resolve()
                            stat_result = entry.stat()
                        except (FileNotFoundError, OSError, PermissionError):
                            continue
                        matches[resolved] = {
                            "path": str(resolved),
                            "name": entry.name,
                            "kind": "directory" if is_directory else "file",
                            "size_bytes": stat_result.st_size,
                            "workspace_root": str(root),
                        }
                if recursive and is_directory and not is_symlink and depth < max_depth:
                    queue.append((entry, depth + 1))

    ordered = [matches[path] for path in sorted(matches, key=str)]
    returned = ordered[:max_results]
    return {
        **workspace,
        "name_patterns": patterns,
        "kind": kind,
        "recursive": recursive,
        "max_depth": max_depth,
        "scanned_entries": scanned_entries,
        "match_count": len(ordered),
        "returned_count": len(returned),
        "truncated": len(ordered) > len(returned),
        "matches": returned,
    }


__all__ = [
    "find_workspace_files",
    "resolve_active_workspace",
    "resolve_active_workspace_file",
    "workspace_name_from_title",
]
