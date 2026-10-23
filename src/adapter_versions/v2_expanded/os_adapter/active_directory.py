"""Resolve a directory from the currently focused desktop context."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import re
import shutil
from typing import Callable, Iterable

from .command import CommandRunner
from .errors import AdapterError


_ACTIVE_WINDOW_RE = re.compile(r"window id #\s*(0x[0-9a-f]+)", re.IGNORECASE)
_TITLE_RE = re.compile(
    r'^(?:_NET_WM_NAME|WM_NAME)\([^)]*\)\s*=\s*"(.*)"$', re.MULTILINE
)
_CLASS_RE = re.compile(r"^WM_CLASS\([^)]*\)\s*=\s*(.*)$", re.MULTILINE)
_QUOTED_RE = re.compile(r'"((?:\\.|[^"\\])*)"')
_FILES_SUFFIX_RE = re.compile(
    r"(?:\s+-\s+Files|\s+\u2013\s+Files|\s+\u2014\s+Files)$",
    re.IGNORECASE,
)


def _unescape_x_property(value: str) -> str:
    return value.replace(r"\"", '"').replace(r"\\", "\\")


def _active_window_properties(
    runner: CommandRunner,
) -> tuple[str, str, tuple[str, ...]]:
    if shutil.which("xprop") is None:
        raise AdapterError(
            "ACTIVE_CONTEXT_UNAVAILABLE",
            "xprop is unavailable, so the focused desktop window cannot be inspected",
            http_status=422,
        )
    root = runner.run(
        ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
        check=False,
        timeout=5,
    )
    match = _ACTIVE_WINDOW_RE.search(root["stdout"])
    if root["returncode"] != 0 or match is None or match.group(1) == "0x0":
        raise AdapterError(
            "ACTIVE_CONTEXT_UNAVAILABLE",
            "no focused desktop window is observable",
            {"xprop": root["stdout"].strip() or root["stderr"].strip()},
            422,
        )
    window_id = match.group(1)
    properties = runner.run(
        [
            "xprop",
            "-id",
            window_id,
            "_NET_WM_NAME",
            "WM_NAME",
            "WM_CLASS",
        ],
        check=False,
        timeout=5,
    )
    if properties["returncode"] != 0:
        raise AdapterError(
            "ACTIVE_CONTEXT_UNAVAILABLE",
            "the focused desktop window properties could not be read",
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
    return window_id, title.strip(), classes


def directory_name_from_file_manager_title(title: str) -> str | None:
    """Return the folder basename represented by a normal Files window title."""
    normalized = _FILES_SUFFIX_RE.sub("", title.strip()).strip()
    if not normalized or normalized.casefold() in {"files", "recent", "starred"}:
        return None
    if normalized.startswith("/"):
        return normalized
    return normalized


def find_named_directories(
    name: str,
    roots: Iterable[Path],
    *,
    max_depth: int = 4,
    max_directories: int = 512,
) -> list[Path]:
    """Find bounded, non-symlink directory candidates by observed basename."""
    exact: set[Path] = set()
    folded: set[Path] = set()
    queue = deque(
        (root.expanduser().resolve(), 0) for root in roots if root.expanduser().is_dir()
    )
    scanned = 0
    while queue and scanned < max_directories:
        directory, depth = queue.popleft()
        scanned += 1
        if directory.name == name:
            exact.add(directory)
        elif directory.name.casefold() == name.casefold():
            folded.add(directory)
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
                if child.is_dir() and not child.is_symlink():
                    queue.append((child.resolve(), depth + 1))
            except (FileNotFoundError, OSError, PermissionError):
                continue
    return sorted(exact or folded, key=str)


def resolve_active_desktop_directory(
    runner: CommandRunner,
    terminal_directory: Callable[[], Path],
    *,
    home: Path | None = None,
    search_roots: Iterable[Path] | None = None,
) -> Path:
    """Resolve an active terminal CWD or uniquely named focused Files folder."""
    home_directory = (home or Path.home()).expanduser().resolve()
    window_id, title, classes = _active_window_properties(runner)
    class_tokens = {value.casefold() for value in classes}
    if any("terminal" in value for value in class_tokens):
        return terminal_directory().resolve()
    if not any("nautilus" in value or value == "files" for value in class_tokens):
        raise AdapterError(
            "ACTIVE_CONTEXT_UNAVAILABLE",
            "the focused window is neither a terminal nor the Files application",
            {"window_id": window_id, "title": title, "window_classes": list(classes)},
            422,
        )

    observed_name = directory_name_from_file_manager_title(title)
    if observed_name is None:
        raise AdapterError(
            "ACTIVE_CONTEXT_UNAVAILABLE",
            "the focused Files window does not expose a concrete folder name",
            {"window_id": window_id, "title": title},
            422,
        )
    if observed_name.startswith("/"):
        absolute = Path(observed_name).resolve()
        if absolute.is_dir():
            return absolute
    if observed_name.casefold() == "home":
        return home_directory

    roots = list(search_roots or ())
    if not roots:
        roots = [home_directory]
        for candidate in (Path("/tmp"), Path("/mnt/data")):
            if candidate.is_dir():
                roots.append(candidate)
    candidates = find_named_directories(observed_name, roots)
    if len(candidates) != 1:
        raise AdapterError(
            "ACTIVE_CONTEXT_AMBIGUOUS" if candidates else "ACTIVE_CONTEXT_UNAVAILABLE",
            (
                "multiple directories match the focused Files folder name"
                if candidates
                else "the focused Files folder could not be resolved to a local directory"
            ),
            {
                "window_id": window_id,
                "title": title,
                "observed_folder_name": observed_name,
                "candidates": [str(path) for path in candidates],
                "searched_roots": [str(path) for path in roots],
            },
            409 if candidates else 422,
        )
    return candidates[0]


__all__ = [
    "directory_name_from_file_manager_title",
    "find_named_directories",
    "resolve_active_desktop_directory",
]
