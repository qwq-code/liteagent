from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections import deque
from fnmatch import fnmatchcase
import gzip
import json
import os
import re
import shlex
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional guest dependency
    Image = None

from .active_directory import resolve_active_desktop_directory
from .archive import create_zip, extract_zip
from .command import (
    CommandRunner,
    gsettings_failure_guidance,
    literal_argument_failure_guidance,
)
from .desktop import inspect_applications, set_mime_associations
from .errors import AdapterError
from .lifecycle import OSLifecycle, TERMINAL_TITLE
from .local_paths import is_protected_local_root
from .pdf_tools import extract_pdf_pages, inspect_pdf_outline
from .pdf_tables import inspect_pdf_table
from .pdf_forms import fill_pdf_form, inspect_pdf_form
from .permissions import set_regular_file_permission, set_regular_file_permissions
from .terminal_profile import inspect_default_profile, set_default_profile_setting
from .window_capture import capture_window
from .visible_terminal import run_visible_terminal_command
from .verifier import (
    gsettings_value,
    package_state,
    parse_favorites,
    trash_entries,
    user_state,
)
from .wallpaper import set_wallpaper as set_desktop_wallpaper


def _source(path: str, *, directory: bool | None = None) -> Path:
    target = Path(path).expanduser()
    if not target.exists():
        raise AdapterError(
            "PATH_NOT_FOUND", f"path does not exist: {target}", http_status=404
        )
    if directory is True and not target.is_dir():
        raise AdapterError("INVALID_ARGUMENT", f"path is not a directory: {target}")
    if directory is False and not target.is_file():
        raise AdapterError("INVALID_ARGUMENT", f"path is not a file: {target}")
    return target


def _find_root(path: str) -> tuple[Path, str | None]:
    """Resolve an unnamed home folder using the standard Desktop location."""
    requested = Path(path).expanduser()
    if requested.exists():
        if not requested.is_dir():
            raise AdapterError("INVALID_ARGUMENT", f"path is not a directory: {requested}")
        return requested, None

    home = Path.home()
    if requested.parent == home and requested.name not in {"Desktop", "Documents", "Downloads"}:
        desktop_root = home / "Desktop" / requested.name
        if desktop_root.is_dir():
            return desktop_root, str(requested)

    # Preserve the public PATH_NOT_FOUND contract for genuinely invalid roots.
    return _source(path, directory=True), None


_SHELL_SYNTAX_TOKENS = frozenset({">", ">>", "|", "||", "&&", ";"})
_COMMAND_RUN_REDIRECTION_RECOVERY = (
    "remove the redirection token and destination from argv, then pass the "
    "destination as stdout_path; set append_stdout=true only for >> semantics"
)
_TERMINAL_OUTPUT_REDIRECTION_RECOVERY = (
    "remove the redirection token and destination from argv so terminal.show_output "
    "leaves the command output visible; if file output is required instead, choose the "
    "public command.run action and use command.run's stdout_path field; set command.run's "
    "append_stdout=true only for >> semantics"
)


def _reject_shell_syntax(argv: list[str], *, redirection_recovery: str) -> None:
    shell_tokens = []
    is_find = bool(argv) and Path(argv[0]).name == "find"
    find_exec = False
    for index, token in enumerate(argv):
        if is_find:
            if not find_exec and token in {"-exec", "-execdir", "-ok", "-okdir"}:
                find_exec = True
            elif find_exec and (
                token == ";" or (token == "+" and argv[index - 1] == "{}")
            ):
                # find consumes its own execution terminator without a shell.
                find_exec = False
                continue
        if token in _SHELL_SYNTAX_TOKENS:
            shell_tokens.append(token)
    if not shell_tokens:
        return
    details: dict[str, Any] = {
        "shell_tokens": shell_tokens,
        "argv": argv,
        "shell_parsing": False,
    }
    if ">" in shell_tokens or ">>" in shell_tokens:
        details["recovery"] = redirection_recovery
    else:
        details["recovery"] = (
            "For a pipeline, conditional, or other shell syntax, pass exactly "
            '["bash", "-c", <one complete model-authored script>] '
            "as argv; do not place shell operators in separate argv items. "
            "To run one command in a different directory, put only that command "
            'in argv and set cwd_source="explicit" with your selected absolute '
            "directory in cwd_path instead of using cd and &&. All relative "
            "arguments resolve from that working directory."
        )
    raise AdapterError(
        "SHELL_SYNTAX_UNSUPPORTED",
        "argv is executed directly and cannot contain shell operators",
        details,
        422,
    )


def _reject_noop_rename(source: Path, destination: Path) -> None:
    """Reject moves that cannot change the directory entry being moved."""
    for field, path in (("source", source), ("destination", destination)):
        if is_protected_local_root(path):
            raise AdapterError(
                "INVALID_ARGUMENT",
                f"{field} must not resolve to the filesystem or home root",
            )
    if source.resolve() == destination.resolve():
        raise AdapterError(
            "DESTINATION_CONFLICT",
            "destination must differ from source",
            http_status=409,
        )
    if destination.exists():
        try:
            same_inode = os.path.samefile(source, destination)
        except (OSError, ValueError):
            same_inode = False
        if same_inode:
            raise AdapterError(
                "DESTINATION_CONFLICT",
                "destination must not refer to the same inode as source",
                http_status=409,
            )


def _command_path(raw_path: str, cwd: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path(cwd) / path
    return path.resolve(strict=False)


def _reject_stdout_input_alias(argv: list[str], stdout_path: str, cwd: str) -> None:
    """Reject shell-style redirection that would truncate an argv input file."""
    destination = _command_path(stdout_path, cwd)
    if not destination.exists():
        return
    for index, raw_argument in enumerate(argv):
        candidate = _command_path(raw_argument, cwd)
        if not candidate.is_file():
            continue
        try:
            aliases_destination = os.path.samefile(candidate, destination)
        except OSError:
            aliases_destination = candidate == destination
        if not aliases_destination:
            continue
        raise AdapterError(
            "OUTPUT_CONFLICT",
            "stdout_path must differ from every existing file argument in argv",
            {
                "stdout_path": stdout_path,
                "conflicting_argv_index": index,
                "conflicting_argument": raw_argument,
                "recovery": (
                    "choose a distinct stdout_path for captured output; do not redirect "
                    "a command back onto one of its input files"
                ),
            },
            409,
        )


def _active_terminal_working_directory() -> Path:
    home = Path.home().resolve()
    candidates: set[Path] = set()
    for process_dir in Path("/proc").glob("[0-9]*"):
        try:
            command = (
                (process_dir / "cmdline")
                .read_bytes()
                .split(b"\0", 1)[0]
                .decode("utf-8")
            )
            working_directory = Path(os.readlink(process_dir / "cwd")).resolve()
        except (
            FileNotFoundError,
            OSError,
            PermissionError,
            ProcessLookupError,
            UnicodeDecodeError,
        ):
            continue
        if Path(command).name not in {"bash", "zsh", "fish"}:
            continue
        if working_directory == home or home in working_directory.parents:
            candidates.add(working_directory)
    non_home = [path for path in candidates if path != home]
    if not candidates:
        raise AdapterError(
            "TERMINAL_UNAVAILABLE",
            "no active user shell working directory is observable; use an absolute path or ~/ path instead of a relative path",
            {
                "recovery": (
                    "retry with an exact absolute path returned by observation, or a ~/ path; "
                    "relative paths require an observable active terminal working directory"
                ),
                "relative_paths_supported": False,
            },
            http_status=422,
        )
    return max(
        non_home or list(candidates), key=lambda path: (len(path.parts), str(path))
    )


def _resolve_path_from_active_terminal(raw_path: str) -> Path:
    """Resolve relative user paths against the observed terminal working directory."""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = _active_terminal_working_directory() / path
    return path.resolve()


def _compact_pdf_layout_text(text: str) -> str:
    """Keep table row boundaries while removing pdftotext layout padding."""
    compacted_lines: list[str] = []
    previous_blank = False
    for raw_line in text.splitlines():
        line = re.sub(r" {2,}", "\t", raw_line.rstrip(" \t"))
        is_blank = not line
        if is_blank and previous_blank:
            continue
        compacted_lines.append(line)
        previous_blank = is_blank

    compacted = "\n".join(compacted_lines)
    if compacted and text.endswith(("\n", "\r")):
        compacted += "\n"
    return compacted


def _text_window(
    text: str, *, start_char: int, max_chars: int
) -> tuple[str, int, int, bool]:
    """Return one bounded, model-selected window with truthful offsets."""
    start = min(max(start_char, 0), len(text))
    end = min(start + max_chars, len(text))
    return text[start:end], start, end, end < len(text)


def _batch_candidate_directories(
    root: Path,
    pattern: str,
    *,
    include_hidden: bool,
    supported_suffixes: frozenset[str] | None = None,
    max_depth: int = 4,
    max_directories: int = 256,
    max_results: int = 8,
) -> dict[str, Any]:
    queue = deque([(root, 0)])
    suggestions: list[str] = []
    scanned = 0
    while queue and scanned < max_directories and len(suggestions) < max_results:
        directory, depth = queue.popleft()
        scanned += 1
        try:
            entries = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
        except (FileNotFoundError, OSError, PermissionError):
            continue

        matching_source = False
        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                if (
                    entry.is_file()
                    and fnmatchcase(entry.name, pattern)
                    and (
                        supported_suffixes is None
                        or entry.suffix.casefold() in supported_suffixes
                    )
                ):
                    matching_source = True
                    break
            except (FileNotFoundError, OSError, PermissionError):
                continue
        if directory != root and matching_source:
            suggestions.append(str(directory.resolve()))

        if depth >= max_depth:
            continue
        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                if entry.is_dir() and not entry.is_symlink():
                    queue.append((entry, depth + 1))
            except (FileNotFoundError, OSError, PermissionError):
                continue

    return {
        "suggested_directories": suggestions,
        "suggestion_scan": {
            "root": str(root),
            "max_depth": max_depth,
            "max_directories": max_directories,
            "max_results": max_results,
            "directories_scanned": scanned,
            "truncated": bool(queue) or len(suggestions) >= max_results,
        },
    }


OCR_SOURCE_SUFFIXES = frozenset(
    {".bmp", ".jpeg", ".jpg", ".pdf", ".png", ".tif", ".tiff", ".webp"}
)


def _pdf_candidate_directories(
    root: Path,
    pattern: str,
    *,
    include_hidden: bool,
) -> dict[str, Any]:
    return _batch_candidate_directories(
        root,
        pattern,
        include_hidden=include_hidden,
        supported_suffixes=frozenset({".pdf"}),
    )


def _ocr_candidate_directories(
    root: Path,
    pattern: str,
    *,
    include_hidden: bool,
) -> dict[str, Any]:
    return _batch_candidate_directories(
        root,
        pattern,
        include_hidden=include_hidden,
        supported_suffixes=OCR_SOURCE_SUFFIXES,
    )


def _document_candidate_directories(
    root: Path,
    pattern: str,
    *,
    include_hidden: bool,
) -> dict[str, Any]:
    return _batch_candidate_directories(
        root,
        pattern,
        include_hidden=include_hidden,
    )


def _batch_input_directory(
    params: dict[str, Any],
    candidate_directories: Callable[..., dict[str, Any]],
) -> Path:
    cwd_source = params["cwd_source"]
    if cwd_source == "active_terminal":
        try:
            input_directory = _active_terminal_working_directory()
        except AdapterError as error:
            if error.code != "TERMINAL_UNAVAILABLE":
                raise
            pattern = params["input_pattern"]
            recovery = candidate_directories(
                Path.home().resolve(),
                pattern,
                include_hidden=bool(params.get("include_hidden", False)),
            )
            suggestions = recovery["suggested_directories"]
            if suggestions:
                guidance = (
                    'retry with cwd_source="explicit" and cwd_path set to one '
                    "suggested_directories entry"
                )
            else:
                guidance = (
                    "use filesystem.find to locate the input directory, then retry with "
                    'cwd_source="explicit" and that absolute directory as cwd_path'
                )
            raise AdapterError(
                "TERMINAL_UNAVAILABLE",
                f"{error.message}; {guidance}",
                {
                    "requested_cwd_source": cwd_source,
                    "input_pattern": pattern,
                    **recovery,
                    "retry": {
                        "cwd_source": "explicit",
                        "cwd_path_options": suggestions,
                    },
                },
                error.http_status,
            ) from error
    elif cwd_source == "home":
        input_directory = Path.home()
    else:
        input_directory = Path(params["cwd_path"]).expanduser()
    return _source(str(input_directory), directory=True).resolve()


def _gvariant(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise AdapterError("INVALID_ARGUMENT", "GNOME setting value must be scalar")


class OSActions:
    def __init__(
        self,
        runner: CommandRunner | None = None,
        lifecycle: OSLifecycle | None = None,
    ) -> None:
        self.runner = runner or CommandRunner()
        self.lifecycle = lifecycle or OSLifecycle(self.runner)

    def find_files(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        requested_roots = list(params.get("roots", [str(Path.home())]))
        root_aliases: dict[str, str] = {}
        roots = []
        for value in requested_roots:
            resolved, alias = _find_root(value)
            roots.append(resolved.resolve())
            if alias is not None:
                root_aliases[alias] = str(resolved.resolve())
        roots = list(dict.fromkeys(roots))
        patterns = params["name_patterns"]
        kind = params.get("kind", "file")
        recursive = bool(params.get("recursive", True))
        include_hidden = bool(params.get("include_hidden", False))
        max_depth = int(params.get("max_depth", 4))
        max_results = int(params.get("max_results", 50))
        matches: dict[Path, dict[str, Any]] = {}
        scanned_entries = 0

        for root in roots:
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
                                "modified_at": datetime.fromtimestamp(
                                    stat_result.st_mtime, tz=timezone.utc
                                ).isoformat(),
                            }
                    if (
                        recursive
                        and is_directory
                        and not is_symlink
                        and depth + 1 < max_depth
                    ):
                        queue.append((entry, depth + 1))

        ordered = [matches[path] for path in sorted(matches, key=str)]
        returned = ordered[:max_results]
        return {
            "requested_roots": requested_roots,
            "roots": [str(root) for root in roots],
            "root_aliases": root_aliases,
            "name_patterns": patterns,
            "kind": kind,
            "recursive": recursive,
            "max_depth": max_depth,
            "matches": returned,
            "match_count": len(ordered),
            "returned_count": len(returned),
            "truncated": len(ordered) > len(returned),
            "scanned_entries": scanned_entries,
        }

    def open_path(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        requested = Path(params["path"]).expanduser()
        if not requested.exists():
            parent = requested.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            nearby = []
            if parent.is_dir():
                try:
                    nearby = [
                        str(path.resolve())
                        for path in sorted(
                            parent.iterdir(), key=lambda path: path.name.casefold()
                        )
                        if not path.name.startswith(".")
                    ][:24]
                except (OSError, PermissionError):
                    nearby = []
            raise AdapterError(
                "PATH_NOT_FOUND",
                f"path does not exist: {requested}",
                {
                    "nearest_existing_parent": str(parent),
                    "nearby_entries": nearby,
                    "recovery": "Use filesystem.find when the required file or folder path is unknown.",
                },
                404,
            )
        target = requested.resolve()
        command = self.runner.start(
            ["gio", "open", str(target)],
            error_code="OPEN_FAILED",
            error_message=f"failed to launch desktop path: {target}",
        )
        wait_seconds = float(params.get("wait_seconds", 1.0))
        if wait_seconds:
            time.sleep(wait_seconds)
        return {
            "path": str(target),
            "kind": "directory" if target.is_dir() else "file",
            "opened": True,
            "wait_seconds": wait_seconds,
            "launcher_pid": command["pid"],
            "launcher_returncode": command["returncode"],
        }

    def copy_file(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        source = _source(params["source"], directory=False).resolve()
        destination = Path(params["destination"]).expanduser()
        if not destination.is_absolute():
            raise AdapterError(
                "INVALID_ARGUMENT", "destination must resolve to an absolute path"
            )
        destination = destination.resolve()
        if source == destination:
            raise AdapterError(
                "DESTINATION_CONFLICT",
                "destination must differ from source",
                http_status=409,
            )
        if not destination.parent.is_dir():
            if params.get("create_parents", False):
                self.create_directory(
                    {"path": str(destination.parent), "parents": True}, _timeout
                )
            else:
                raise AdapterError(
                    "PATH_NOT_FOUND",
                    f"destination parent does not exist: {destination.parent}",
                    {
                        "recovery": (
                            "Set create_parents=true to create this output file's parent directories, "
                            "or create the parent with filesystem.create_directory first."
                        )
                    },
                    404,
                )
        if destination.exists():
            if destination.is_dir():
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"destination is a directory: {destination}",
                    http_status=409,
                )
            if not params.get("replace", False):
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"destination exists: {destination}",
                    http_status=409,
                )
        shutil.copy2(source, destination)
        return {
            "source": str(source),
            "destination": str(destination),
            "size_bytes": destination.stat().st_size,
            "replaced": bool(params.get("replace", False)),
        }

    def copy_matching_tree(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        # Relative paths in a model-selected filesystem request refer to the visible
        # terminal context, never to the Adapter service's installation directory.
        source = _source(
            str(_resolve_path_from_active_terminal(params["source"])), directory=True
        )
        destination = _resolve_path_from_active_terminal(params["destination"])
        if destination == source:
            raise AdapterError(
                "INVALID_ARGUMENT", "destination must differ from source"
            )
        destination.mkdir(parents=True, exist_ok=True)
        directories = []
        files = []
        for path in sorted(source.rglob("*")):
            if path == destination or destination in path.parents:
                continue
            relative = path.relative_to(source)
            if path.is_dir():
                (destination / relative).mkdir(parents=True, exist_ok=True)
                directories.append(str(relative))
            elif path.is_file() and path.match(params["pattern"]):
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                files.append(str(relative))
        return {
            "source": str(source),
            "destination": str(destination),
            "pattern": params["pattern"],
            "directories": directories,
            "copied_relative_paths": files,
        }

    def copy_to_directories(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        raw_paths = [params["source"], *params["destinations"]]
        needs_active_directory = any(
            not Path(raw).expanduser().is_absolute() for raw in raw_paths
        )
        if needs_active_directory:
            try:
                active_directory = _active_terminal_working_directory()
            except AdapterError as error:
                if error.code != "TERMINAL_UNAVAILABLE":
                    raise
                relative_paths = [
                    raw
                    for raw in raw_paths
                    if not Path(raw).expanduser().is_absolute()
                ]
                raise AdapterError(
                    "TERMINAL_UNAVAILABLE",
                    (
                        f"{error.message}; relative filesystem paths require an active "
                        "terminal working directory; resolve the intended parent directory "
                        "before retrying with its exact absolute path"
                    ),
                    {
                        "relative_paths": relative_paths,
                        "retry": (
                            "Resolve the intended parent directory from the instruction or "
                            "observed state, then use its exact absolute path. ~/ denotes "
                            "the home directory, not the current folder; do not prepend it "
                            "unless home is the intended location."
                        ),
                    },
                    error.http_status,
                ) from error
        else:
            active_directory = None

        def resolve_path(raw: str) -> Path:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                assert active_directory is not None
                path = active_directory / path
            return path.resolve()

        source = _source(str(resolve_path(params["source"])), directory=False).resolve()
        directories = [resolve_path(raw) for raw in params["destinations"]]
        if len(set(directories)) != len(directories):
            raise AdapterError(
                "INVALID_ARGUMENT",
                "destination paths must be unique after relative-path resolution",
            )
        for directory in directories:
            if directory.exists() and not directory.is_dir():
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"destination must be a directory, but this path is not: {directory}",
                    {
                        "recovery": (
                            "destinations accepts directory paths, not output filenames. "
                            "Use filesystem.copy for one exact source/output file pair."
                        ),
                    },
                    409,
                )
        targets = [directory / source.name for directory in directories]
        # copy2 treats a directory target as another parent, silently changing the output path.
        for target in targets:
            if target.resolve() == source:
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"destination would overwrite the source file: {target}",
                    http_status=409,
                )
            if target.is_dir():
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"destination is a directory: {target}",
                    http_status=409,
                )
        copied = []
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(target))
        return {"source": str(source), "copied": copied}

    def create_directory(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        directory = Path(params["path"]).expanduser()
        existed = directory.exists()
        if existed and not directory.is_dir():
            raise AdapterError(
                "DESTINATION_CONFLICT",
                f"path exists and is not a directory: {directory}",
                http_status=409,
            )
        directory.mkdir(parents=bool(params.get("parents", True)), exist_ok=True)
        return {
            "path": str(directory.resolve()),
            "created": not existed,
            "parents": bool(params.get("parents", True)),
        }

    def rename(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        allowed = {"source", "destination", "replace", "search_roots", "source_query", "new_name"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_ARGUMENT",
                "filesystem.rename accepts one exact path pair or one basename pair",
                {"unexpected": unexpected},
            )
        has_explicit_pair = "source" in params or "destination" in params
        has_legacy_pair = "source_query" in params or "new_name" in params
        if has_explicit_pair and has_legacy_pair:
            raise AdapterError(
                "INVALID_ARGUMENT",
                "filesystem.rename accepts either source/destination or source_query/new_name, not both",
            )
        if has_explicit_pair:
            source_value = params.get("source")
            destination_value = params.get("destination")
        else:
            source_value = params.get("source_query")
            destination_value = params.get("new_name")
        if not isinstance(source_value, str) or not isinstance(destination_value, str):
            raise AdapterError(
                "INVALID_ARGUMENT",
                "filesystem.rename requires a complete source/destination or source_query/new_name pair",
            )
        source_is_path = source_value.startswith(("/", "~/"))
        destination_is_path = destination_value.startswith(("/", "~/"))
        if source_is_path:
            source = _source(str(Path(source_value).expanduser()))
        else:
            if (
                not source_value
                or source_value in {"~", ".", ".."}
                or "/" in source_value
                or "\\" in source_value
                or "\x00" in source_value
            ):
                raise AdapterError(
                    "INVALID_ARGUMENT",
                    "basename rename values must be one concrete basename without path separators",
                )
            roots = params.get("search_roots")
            if roots is None:
                roots = []
                desktop = Path.home() / "Desktop"
                if desktop.is_dir():
                    roots.append(str(desktop))
                roots.append(str(Path.home()))
            matches = self.find_files(
                {
                    "roots": roots,
                    "name_patterns": [source_value],
                    "kind": "any",
                    "recursive": True,
                    "include_hidden": False,
                    "max_depth": 4,
                    "max_results": 64,
                },
                _timeout,
            )["matches"]
            if not matches:
                raise AdapterError(
                    "PATH_NOT_FOUND",
                    f"no filesystem object named {source_value!r} was found under the selected roots",
                    {"source": source_value, "roots": roots},
                    404,
                )
            if len(matches) > 1:
                raise AdapterError(
                    "AMBIGUOUS_PATH",
                    f"multiple filesystem objects named {source_value!r} were found; provide an exact source path or narrower search_roots",
                    {"source": source_value, "candidates": [item["path"] for item in matches]},
                    409,
                )
            source = Path(matches[0]["path"])
        if destination_is_path:
            destination = Path(destination_value).expanduser()
        else:
            if (
                not destination_value
                or destination_value in {".", ".."}
                or "/" in destination_value
                or "\\" in destination_value
                or "\x00" in destination_value
            ):
                raise AdapterError(
                    "INVALID_ARGUMENT",
                    "basename rename values must be one concrete basename without path separators",
                )
            destination = source.parent / destination_value
        if not source.is_absolute() or not destination.is_absolute():
            raise AdapterError(
                "INVALID_ARGUMENT",
                "source and destination must resolve to absolute paths",
            )
        _reject_noop_rename(source, destination)
        if destination.exists() and destination != source:
            if not params.get("replace", False):
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"destination exists: {destination}",
                    http_status=409,
                )
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return {"source": str(source), "destination": str(destination)}

    def chmod_tree(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        root = _active_terminal_working_directory()
        root = _source(str(root), directory=True).resolve()
        return set_regular_file_permissions(
            root,
            mode=params["mode"],
            recursive=True,
        ) | {"cwd_source": "active_terminal"}

    def set_permissions(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        path = Path(params["path"]).expanduser()
        if not path.is_absolute():
            raise AdapterError("INVALID_ARGUMENT", "path must be absolute")
        return set_regular_file_permission(path.absolute(), mode=params["mode"])

    def compress_file(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        source = _source(params["source"], directory=False).resolve()
        destination = Path(params["destination"]).expanduser()
        if not destination.is_absolute():
            raise AdapterError(
                "INVALID_ARGUMENT", "destination must resolve to an absolute path"
            )
        destination = destination.resolve()
        if not destination.parent.is_dir():
            raise AdapterError(
                "PATH_NOT_FOUND",
                f"destination parent does not exist: {destination.parent}",
                {
                    "recovery": "Create the parent with filesystem.create_directory first."
                },
                404,
            )
        if destination.exists() and not params.get("overwrite", False):
            raise AdapterError(
                "DESTINATION_CONFLICT",
                f"destination exists: {destination}",
                http_status=409,
            )
        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        os.close(temporary_fd)
        temporary = Path(temporary_name)
        try:
            with (
                source.open("rb") as source_stream,
                gzip.open(temporary, "wb") as archive_stream,
            ):
                shutil.copyfileobj(source_stream, archive_stream)
            with gzip.open(temporary, "rb") as archive_stream:
                while archive_stream.read(1024 * 1024):
                    pass
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        remove_source = bool(params["remove_source"])
        if remove_source:
            source.unlink()
        return {
            "source": str(source),
            "destination": str(destination),
            "remove_source": remove_source,
            "source_exists": source.exists(),
            "compressed_size_bytes": destination.stat().st_size,
        }

    @staticmethod
    def _clipboard_commands() -> tuple[str, list[str], list[str]]:
        if shutil.which("xsel"):
            return (
                "xsel",
                ["xsel", "--clipboard", "--input"],
                ["xsel", "--clipboard", "--output"],
            )
        if shutil.which("xclip"):
            return (
                "xclip",
                ["xclip", "-selection", "clipboard", "-in"],
                ["xclip", "-selection", "clipboard", "-out"],
            )
        raise AdapterError(
            "CLIPBOARD_UNAVAILABLE",
            "neither xsel nor xclip is available in the desktop session",
            {"required_commands": ["xsel", "xclip"]},
            503,
        )

    def _read_clipboard_text(self, timeout: float) -> tuple[str, str]:
        backend, _write_argv, read_argv = self._clipboard_commands()
        completed = self.runner.run(
            read_argv,
            timeout=timeout,
            error_code="CLIPBOARD_FAILED",
            error_message="failed to read the desktop clipboard",
        )
        return backend, completed["stdout"]

    def set_clipboard(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        text = params["text"]
        backend, write_argv, _read_argv = self._clipboard_commands()
        self.runner.run(
            write_argv,
            timeout=timeout,
            input_text=text,
            error_code="CLIPBOARD_FAILED",
            error_message="failed to write the desktop clipboard",
        )
        observed_backend, observed = self._read_clipboard_text(timeout)
        if observed != text:
            raise AdapterError(
                "CLIPBOARD_VERIFICATION_FAILED",
                "desktop clipboard read-back did not match the requested text",
                {
                    "backend": observed_backend,
                    "expected_chars": len(text),
                    "observed_chars": len(observed),
                },
                422,
            )
        return {
            "text": observed,
            "character_count": len(observed),
            "utf8_bytes": len(observed.encode("utf-8")),
            "backend": backend,
            "verified": True,
        }

    def get_clipboard(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        backend, text = self._read_clipboard_text(timeout)
        max_chars = int(params.get("max_chars", 100_000))
        returned = text[:max_chars]
        return {
            "text": returned,
            "character_count": len(text),
            "returned_character_count": len(returned),
            "utf8_bytes": len(text.encode("utf-8")),
            "truncated": len(returned) < len(text),
            "backend": backend,
        }

    def append_each_line(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        if "lines" in params:
            lines = list(params["lines"])
        else:
            lines = (
                _source(params["input_path"], directory=False)
                .read_text(encoding="utf-8")
                .splitlines()
            )
        content = "\n".join(line + params["suffix"] for line in lines) + (
            "\n" if lines else ""
        )
        output = _resolve_path_from_active_terminal(params["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + f".tmp-{os.getpid()}")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(output)
        return {"path": str(output), "content": content, "line_count": len(lines)}

    def list_trash(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        entries = trash_entries(self.runner)
        offset = int(params.get("offset", 0))
        max_results = int(params.get("max_results", 100))
        page = entries[offset : offset + max_results]
        returned_count = len(page)
        truncated = offset + returned_count < len(entries)
        return {
            "entries": page,
            "entry_count": len(entries),
            "offset": offset,
            "max_results": max_results,
            "returned_count": returned_count,
            "truncated": truncated,
            "next_offset": offset + returned_count if truncated else None,
        }

    def restore_trash(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        if set(params) != {"trash_uri", "original_path"} or not all(
            isinstance(params.get(field), str) and params[field]
            for field in ("trash_uri", "original_path")
        ):
            raise AdapterError(
                "INVALID_ARGUMENT",
                "trash.restore requires an exact trash_uri/original_path pair from trash.list",
            )
        entries = trash_entries(self.runner)
        trash_uri = params["trash_uri"]
        original = str(Path(params["original_path"]).expanduser())
        uri_entries = [entry for entry in entries if entry["trash_uri"] == trash_uri]
        if not uri_entries:
            raise AdapterError(
                "PATH_NOT_FOUND",
                "the exact trash URI is not present",
                {"trash_uri": trash_uri},
                404,
            )
        if any(entry["original_path"] != original for entry in uri_entries):
            raise AdapterError(
                "TRASH_TARGET_MISMATCH",
                "trash_uri and original_path do not identify the same current Trash entry",
                {
                    "trash_uri": trash_uri,
                    "original_path": original,
                    "observed_original_paths": sorted(
                        {entry["original_path"] for entry in uri_entries}
                    ),
                },
                409,
            )
        self.runner.run(
            ["gio", "trash", "--restore", trash_uri],
            error_code="OPERATION_FAILED",
            error_message="failed to restore trash entry",
        )
        return {
            "original_path": original,
            "trash_uri": trash_uri,
            "already_restored": False,
        }

    def set_setting(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        encoded = _gvariant(params["value"])
        self.runner.run(
            ["gsettings", "set", params["schema"], params["key"], encoded],
            error_code="SETTING_UNAVAILABLE",
            error_message="failed to update GNOME setting",
        )
        observed = gsettings_value(self.runner, params["schema"], params["key"])
        return {
            "schema": params["schema"],
            "key": params["key"],
            "expected": encoded,
            "observed": observed,
        }

    def inspect_desktop_applications(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        return inspect_applications(params)

    def set_mime_associations(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        return set_mime_associations(self.runner, params, timeout)

    def set_wallpaper(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        return set_desktop_wallpaper(self.runner, params, timeout)

    def notifications_configure(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        do_not_disturb = bool(params["do_not_disturb"])
        setting = self.set_setting(
            {
                "schema": "org.gnome.desktop.notifications",
                "key": "show-banners",
                "value": not do_not_disturb,
            },
            timeout,
        )
        return {"do_not_disturb": do_not_disturb, "settings": [setting]}

    def set_accessibility_scale(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        if "magnifier_factor" in params or "text_factor" not in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.set_accessibility_scale requires only text_factor; use separate desktop.set_setting calls for screen-magnifier-enabled and mag-factor",
            )
        setting = self.set_setting(
            {
                "schema": "org.gnome.desktop.interface",
                "key": "text-scaling-factor",
                "value": float(params["text_factor"]),
            },
            timeout,
        )
        return {"settings": [setting]}

    def set_dim_inactive(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        selected = [field for field in ("idle_delay", "idle_dim") if field in params]
        if len(selected) != 1:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.set_dim_inactive requires exactly one of idle_delay or idle_dim; do not combine a delay change with a dimming toggle in one call",
            )
        if "idle_delay" in params:
            return {
                "settings": [
                    self.set_setting(
                        {
                            "schema": "org.gnome.desktop.session",
                            "key": "idle-delay",
                            "value": int(params["idle_delay"]),
                        },
                        timeout,
                    )
                ]
            }
        return {
            "settings": [
                self.set_setting(
                    {
                        "schema": "org.gnome.settings-daemon.plugins.power",
                        "key": "idle-dim",
                        "value": bool(params["idle_dim"]),
                    },
                    timeout,
                )
            ]
        }

    def remove_favorite(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        if set(params) != {"desktop_id"} or not isinstance(
            params.get("desktop_id"), str
        ):
            raise AdapterError(
                "INVALID_ARGUMENT",
                "desktop.remove_favorite requires one exact desktop_id from desktop.favorites.list",
            )
        schema = "org.gnome.shell"
        key = "favorite-apps"
        before = parse_favorites(gsettings_value(self.runner, schema, key))
        desktop_id = params["desktop_id"]
        if desktop_id not in before:
            raise AdapterError(
                "FAVORITE_NOT_FOUND",
                f"favorite application is not present: {desktop_id}",
                {"favorites": before},
                404,
            )
        after = [item for item in before if item != desktop_id]
        self.runner.run(
            ["gsettings", "set", schema, key, repr(after)],
            error_code="SETTING_UNAVAILABLE",
            error_message="failed to update favorite applications",
        )
        observed = parse_favorites(gsettings_value(self.runner, schema, key))
        return {"before": before, "after": observed, "removed": desktop_id}

    def list_favorites(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        favorites = parse_favorites(
            gsettings_value(self.runner, "org.gnome.shell", "favorite-apps")
        )
        offset = int(params.get("offset", 0))
        max_results = int(params.get("max_results", 100))
        page = favorites[offset : offset + max_results]
        returned_count = len(page)
        truncated = offset + returned_count < len(favorites)
        return {
            "favorites": page,
            "favorite_count": len(favorites),
            "offset": offset,
            "max_results": max_results,
            "returned_count": returned_count,
            "truncated": truncated,
            "next_offset": offset + returned_count if truncated else None,
        }

    def set_volume(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        sink = params.get("sink", "@DEFAULT_SINK@")
        self.runner.run(["pulseaudio", "--start"], check=False)
        self.runner.run(
            ["pactl", "set-sink-volume", sink, f"{float(params['percent']):g}%"],
            error_code="AUDIO_UNAVAILABLE",
            error_message="failed to set sink volume",
        )
        return {"sink": sink, "percent": int(float(params["percent"]))}

    def set_timezone(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        timezone = params["timezone"]
        if not (Path("/usr/share/zoneinfo") / timezone).is_file():
            raise AdapterError(
                "INVALID_ARGUMENT", f"timezone is unavailable: {timezone}"
            )
        self.runner.sudo(
            ["timedatectl", "set-timezone", timezone],
            timeout=timeout,
            error_message="failed to set system timezone",
        )
        return {"timezone": timezone}

    def _terminal_schema(self) -> str:
        profile = gsettings_value(
            self.runner, "org.gnome.Terminal.ProfilesList", "default"
        ).strip("'")
        return f"org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{profile}/"

    def inspect_terminal_default_profile(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        return inspect_default_profile(params)

    def set_terminal_default_profile_setting(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        return set_default_profile_setting(params)

    def configure_terminal_size(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        schema = self._terminal_schema()
        columns = int(params["columns"])
        rows = int(params["rows"])
        self.runner.run(
            ["gsettings", "set", schema, "default-size-columns", str(columns)]
        )
        self.runner.run(["gsettings", "set", schema, "default-size-rows", str(rows)])
        self.lifecycle.shutdown()
        self.runner.run(
            [
                "gnome-terminal",
                f"--title={TERMINAL_TITLE}",
                "--",
                "bash",
                "--noprofile",
                "--norc",
            ],
            timeout=10,
            error_code="TERMINAL_UNAVAILABLE",
            error_message="failed to warm the configured terminal profile",
        )
        deadline = time.monotonic() + 10
        windows = []
        while time.monotonic() < deadline:
            self.runner.run(["wmctrl", "-a", TERMINAL_TITLE], check=False)
            windows = [
                line
                for line in self.lifecycle.windows()
                if TERMINAL_TITLE.lower() in line.lower()
            ]
            if windows:
                break
            time.sleep(0.1)
        if not windows:
            raise AdapterError(
                "TERMINAL_UNAVAILABLE",
                "configured terminal window did not become ready",
                http_status=422,
            )
        return {"schema": schema, "columns": columns, "rows": rows, "windows": windows}

    def show_terminal_output(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        argv = list(params["argv"])
        _reject_shell_syntax(
            argv,
            redirection_recovery=_TERMINAL_OUTPUT_REDIRECTION_RECOVERY,
        )
        cwd_source = params["cwd_source"]
        if cwd_source == "active_context":
            cwd = resolve_active_desktop_directory(
                self.runner,
                _active_terminal_working_directory,
            )
        elif cwd_source == "active_terminal":
            cwd = _active_terminal_working_directory()
        elif cwd_source == "home":
            cwd = Path.home().resolve()
        else:
            cwd = Path(params["cwd_path"]).expanduser().resolve()
        _source(str(cwd), directory=True)
        return run_visible_terminal_command(
            self.runner,
            self.lifecycle,
            params,
            cwd=cwd,
            timeout=timeout,
        )

    def capture_window(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        return capture_window(self.runner, self.lifecycle, params, timeout=timeout)

    def run_command(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        argv = list(params["argv"])
        cwd_source = params.get("cwd_source")
        if cwd_source == "active_terminal":
            cwd = str(_active_terminal_working_directory())
        elif cwd_source == "home":
            cwd = str(Path.home())
        elif cwd_source == "explicit":
            cwd = str(Path(params["cwd_path"]).expanduser())
        else:
            # Compatibility for terminal.launch and historical callers.
            cwd = str(Path(params.get("cwd", str(Path.home()))).expanduser())
        _source(cwd, directory=True)
        _reject_shell_syntax(
            argv,
            redirection_recovery=_COMMAND_RUN_REDIRECTION_RECOVERY,
        )
        expected_returncodes = list(params.get("expected_returncodes", [0]))
        if params.get("terminal"):
            terminal_title = (
                f"{TERMINAL_TITLE} Command {os.getpid()}-{time.monotonic_ns()}"
            )
            script = (
                '"$@"; status=$?; printf "\\n[command exited with status %s]\\n" "$status"; '
                "exec bash --noprofile --norc"
            )
            launch = self.runner.run(
                [
                    "gnome-terminal",
                    f"--title={terminal_title}",
                    f"--working-directory={cwd}",
                    "--",
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-c",
                    script,
                    "osworld-adapter-command",
                    *argv,
                ],
                timeout=min(15.0, timeout),
                error_code="TERMINAL_UNAVAILABLE",
                error_message="failed to launch command in a terminal",
            )
            deadline = time.monotonic() + min(timeout, 10.0)
            windows: list[str] = []
            while time.monotonic() < deadline:
                windows = [
                    line
                    for line in self.lifecycle.windows()
                    if terminal_title.casefold() in line.casefold()
                ]
                if windows:
                    break
                time.sleep(0.1)
            if not windows:
                raise AdapterError(
                    "TERMINAL_UNAVAILABLE",
                    "launched terminal window did not become observable",
                    {"argv": argv, "cwd": cwd},
                    422,
                )
            result = {
                "argv": argv,
                "returncode": launch["returncode"],
                "stdout": launch["stdout"],
                "stderr": launch["stderr"],
                "duration_ms": launch["duration_ms"],
                "terminal": {
                    "launched": True,
                    "title": terminal_title,
                    "windows": windows,
                    "child_status": "not_waited",
                },
            }
        else:
            stdout_path = params.get("stdout_path")
            executed_argv = argv
            if stdout_path:
                destination = _command_path(str(stdout_path), cwd)
                _source(str(destination.parent), directory=True)
                if destination.is_dir():
                    raise AdapterError(
                        "INVALID_ARGUMENT",
                        f"stdout_path is a directory: {destination}",
                    )
                _reject_stdout_input_alias(argv, str(stdout_path), cwd)
                operator = ">>" if params.get("append_stdout") else ">"
                script = f'output=$1; shift; exec "$@" {operator} "$output"'
                executed_argv = [
                    "bash",
                    "-c",
                    script,
                    "osworld-adapter-redirect",
                    str(destination),
                    *argv,
                ]
            try:
                result = self.runner.run(
                    executed_argv,
                    timeout=timeout,
                    input_text=params.get("input"),
                    check=False,
                    cwd=cwd,
                )
            except AdapterError as exc:
                if exc.code != "OPERATION_TIMEOUT" or not isinstance(exc.details, dict):
                    raise
                raise AdapterError(
                    exc.code,
                    exc.message,
                    {
                        **exc.details,
                        "requested_argv": argv,
                        "cwd": cwd,
                        "terminal_launch": False,
                        "waited_for_process_exit": True,
                        "partial_effects_possible": True,
                        "guidance": (
                            "This command ran without a terminal and waited for process exit. "
                            "A timeout does not prove that the application failed to open or "
                            "that no changes occurred; inspect the current state before retrying. "
                            "If you intend to launch a long-running GUI application from a "
                            "visible terminal, select command.run with terminal=true. "
                            "cwd_source and provenance alone do not select terminal execution."
                        ),
                    },
                    exc.http_status,
                ) from exc
            if stdout_path:
                destination = _command_path(str(stdout_path), cwd)
                result["argv"] = argv
                result["stdout_path"] = str(destination)
                result["append_stdout"] = bool(params.get("append_stdout"))
                result["stdout_bytes"] = (
                    destination.stat().st_size if destination.is_file() else None
                )
        result["cwd"] = cwd
        result["cwd_source"] = cwd_source or "legacy_explicit"
        result["expected_returncodes"] = expected_returncodes
        if result["returncode"] not in expected_returncodes:
            guidance = gsettings_failure_guidance(
                argv, result["stderr"]
            ) or literal_argument_failure_guidance(argv, result["stderr"])
            if guidance:
                result["guidance"] = guidance
            raise AdapterError(
                "COMMAND_FAILED",
                "command returned an unexpected status",
                result,
                422,
            )
        record_shell_history = (
            params.get("provenance") == "shell_history"
            or params.get("record_shell_history") is True
        )
        if record_shell_history:
            history_path = Path(
                os.environ.get("HISTFILE", str(Path.home() / ".bash_history"))
            ).expanduser()
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_entry = shlex.join(argv)
            if params.get("stdout_path"):
                operator = ">>" if params.get("append_stdout") else ">"
                history_entry = f"{history_entry} {operator} {shlex.quote(str(params['stdout_path']))}"
            with history_path.open("a", encoding="utf-8") as history:
                history.write(history_entry + "\n")
            result["shell_history"] = {
                "recorded": True,
                "path": str(history_path),
                "entry": history_entry,
            }
        result["provenance"] = params.get("provenance") or (
            "shell_history" if record_shell_history else "none"
        )
        return result

    def convert_documents_batch(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        input_directory = _batch_input_directory(
            params, _document_candidate_directories
        )

        pattern = params["input_pattern"]
        include_hidden = bool(params.get("include_hidden", False))
        all_matches = sorted(
            path.resolve() for path in input_directory.glob(pattern) if path.is_file()
        )
        matches = [
            path
            for path in all_matches
            if include_hidden or not path.name.startswith(".")
        ]
        if not matches:
            raise AdapterError(
                "NO_MATCHES",
                f"no input files match {pattern} in {input_directory}",
                {
                    "directory": str(input_directory),
                    "input_pattern": pattern,
                    "hidden_matches_excluded": len(all_matches),
                },
                404,
            )

        output_format = params["output_format"].casefold()
        output_directory = Path(
            params.get("output_directory", str(input_directory))
        ).expanduser()
        output_directory.mkdir(parents=True, exist_ok=True)
        output_directory = output_directory.resolve()

        destinations: dict[Path, Path] = {}
        for source in matches:
            destination = output_directory / f"{source.stem}.{output_format}"
            previous = destinations.get(destination)
            if previous is not None and previous != source:
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"multiple inputs map to {destination}",
                    {"first": str(previous), "second": str(source)},
                    409,
                )
            if destination.resolve() == source:
                raise AdapterError(
                    "INVALID_ARGUMENT",
                    "input and output formats resolve to the same file",
                    {"path": str(source)},
                )
            destinations[destination] = source

        existing = sorted(path for path in destinations if path.exists())
        if existing and not params.get("overwrite", False):
            raise AdapterError(
                "DESTINATION_CONFLICT",
                "one or more converted files already exist",
                {"paths": [str(path) for path in existing]},
                409,
            )
        for path in existing:
            path.unlink()

        executable = shutil.which("libreoffice") or shutil.which("soffice")
        if executable is None:
            raise AdapterError(
                "LIBREOFFICE_UNAVAILABLE",
                "LibreOffice command-line executable is not installed",
                http_status=503,
            )
        history_entry = " ".join(
            [
                Path(executable).name,
                "--headless",
                "--convert-to",
                shlex.quote(output_format),
                *(
                    ["--outdir", shlex.quote(str(output_directory))]
                    if "output_directory" in params
                    else []
                ),
                pattern,
            ]
        )
        if params["provenance"] == "shell_history":
            history_path = Path(
                os.environ.get("HISTFILE", str(Path.home() / ".bash_history"))
            ).expanduser()
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with history_path.open("a", encoding="utf-8") as history:
                history.write(history_entry + "\n")

        # Each CLI process gets its own profile. A bounded pool prevents one slow
        # document from serially consuming the whole batch timeout.
        started = time.monotonic()
        deadline = started + max(0.1, timeout)
        # Keep OCR deterministic in the constrained guest; concurrent
        # tesseract subprocesses can stall on large or progressive images.
        worker_count = 1

        def convert_one(item: tuple[int, Path], profile_root: Path) -> dict[str, Any]:
            index, source = item
            profile = profile_root / f"profile-{index:04d}"
            remaining = deadline - time.monotonic()
            if remaining <= 0.1:
                return {
                    "source": str(source),
                    "status": "error",
                    "error": {
                        "code": "OPERATION_TIMEOUT",
                        "message": "batch conversion deadline expired before launch",
                    },
                }
            argv = [
                executable,
                f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--headless",
                "--nologo",
                "--nodefault",
                "--nolockcheck",
                "--norestore",
                "--convert-to",
                output_format,
                "--outdir",
                str(output_directory),
                str(source),
            ]
            try:
                result = self.runner.run(
                    argv,
                    timeout=remaining,
                    check=False,
                    cwd=str(input_directory),
                )
            except AdapterError as error:
                return {
                    "source": str(source),
                    "status": "error",
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                    },
                }
            return {
                "source": str(source),
                "status": "ok" if result["returncode"] == 0 else "error",
                "command_result": result,
            }

        with tempfile.TemporaryDirectory(prefix="osworld-lo-batch-") as profile:
            profile_root = Path(profile)
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                command_results = list(
                    executor.map(
                        lambda item: convert_one(item, profile_root),
                        enumerate(matches),
                    )
                )

        converted = sorted(
            path for path in destinations if path.is_file() and path.stat().st_size > 0
        )
        missing = sorted(set(destinations).difference(converted))
        failed_commands = [
            result for result in command_results if result["status"] != "ok"
        ]
        if missing or failed_commands:
            raise AdapterError(
                "CONVERSION_INCOMPLETE",
                "LibreOffice did not successfully create every requested output",
                {
                    "converted": [str(path) for path in converted],
                    "missing": [str(path) for path in missing],
                    "failed_commands": failed_commands,
                    "command_results": command_results,
                },
                422,
            )
        return {
            "input_directory": str(input_directory),
            "input_pattern": pattern,
            "output_format": output_format,
            "output_directory": str(output_directory),
            "matched": [str(path) for path in matches],
            "hidden_matches_excluded": len(all_matches) - len(matches),
            "converted": [
                {"path": str(path), "size": path.stat().st_size} for path in converted
            ],
            "command": history_entry,
            "command_results": command_results,
            "isolated_profile": True,
            "parallel_workers": worker_count,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "provenance": params["provenance"],
            "shell_history": (
                {"recorded": True, "entry": history_entry}
                if params["provenance"] == "shell_history"
                else {"recorded": False}
            ),
        }

    def convert_document(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        source = _source(params["source"], directory=False).resolve()
        destination = Path(params["destination"]).expanduser()
        if not destination.is_absolute():
            raise AdapterError(
                "INVALID_ARGUMENT", "destination must resolve to an absolute path"
            )
        destination = destination.resolve()
        if source == destination:
            raise AdapterError(
                "DESTINATION_CONFLICT",
                "destination must differ from source",
                http_status=409,
            )
        if not destination.parent.is_dir():
            raise AdapterError(
                "PATH_NOT_FOUND",
                f"destination parent does not exist: {destination.parent}",
                {
                    "recovery": "Create the parent with filesystem.create_directory first."
                },
                404,
            )
        if destination.exists():
            if destination.is_dir() or not params.get("overwrite", False):
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"destination exists: {destination}",
                    http_status=409,
                )

        output_format = destination.suffix.removeprefix(".").casefold()
        executable = shutil.which("libreoffice") or shutil.which("soffice")
        if executable is None:
            raise AdapterError(
                "LIBREOFFICE_UNAVAILABLE",
                "LibreOffice command-line executable is not installed",
                http_status=503,
            )

        with (
            tempfile.TemporaryDirectory(prefix="osworld-lo-single-profile-") as profile,
            tempfile.TemporaryDirectory(
                prefix=f".{destination.name}.convert-", dir=destination.parent
            ) as output_directory,
        ):
            profile_uri = Path(profile).resolve().as_uri()
            argv = [
                executable,
                f"-env:UserInstallation={profile_uri}",
                "--headless",
                "--nologo",
                "--nodefault",
                "--nolockcheck",
                "--norestore",
                "--convert-to",
                output_format,
                "--outdir",
                output_directory,
                str(source),
            ]
            command_result = self.runner.run(
                argv,
                timeout=timeout,
                check=False,
                cwd=str(source.parent),
            )
            generated = Path(output_directory) / f"{source.stem}.{output_format}"
            if (
                command_result["returncode"] != 0
                or not generated.is_file()
                or generated.stat().st_size == 0
            ):
                raise AdapterError(
                    "CONVERSION_INCOMPLETE",
                    "LibreOffice did not create the requested output",
                    {
                        "source": str(source),
                        "destination": str(destination),
                        "command_result": command_result,
                    },
                    422,
                )
            os.replace(generated, destination)

        return {
            "source": str(source),
            "destination": str(destination),
            "output_format": output_format,
            "size_bytes": destination.stat().st_size,
            "replaced": bool(params.get("overwrite", False)),
            "command_result": command_result,
            "isolated_profile": True,
        }

    def extract_pdf_text_batch(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        input_directory = _batch_input_directory(params, _pdf_candidate_directories)

        pattern = params["input_pattern"]
        include_hidden = bool(params.get("include_hidden", False))
        all_matches = sorted(
            path.resolve() for path in input_directory.glob(pattern) if path.is_file()
        )
        visible_matches = [
            path
            for path in all_matches
            if include_hidden or not path.name.startswith(".")
        ]
        matches = [path for path in visible_matches if path.suffix.casefold() == ".pdf"]
        if not matches:
            recovery = _pdf_candidate_directories(
                input_directory,
                pattern,
                include_hidden=include_hidden,
            )
            suggestion = recovery["suggested_directories"]
            message = f"no PDF files match {pattern} directly in {input_directory}"
            if suggestion:
                message += (
                    "; matching PDFs exist in suggested_directories, so retry with "
                    "cwd_source=explicit and one listed directory as cwd_path"
                )
            raise AdapterError(
                "NO_MATCHES",
                message,
                {
                    "directory": str(input_directory),
                    "input_pattern": pattern,
                    "hidden_matches_excluded": len(all_matches) - len(visible_matches),
                    "non_pdf_matches_excluded": len(visible_matches),
                    **recovery,
                },
                404,
            )

        executable = shutil.which("pdftotext")
        if executable is None:
            raise AdapterError(
                "PDF_TEXT_EXTRACTOR_UNAVAILABLE",
                "the pdftotext executable is not installed",
                http_status=503,
            )

        start_page = int(params.get("start_page", 1))
        page_count = params.get("page_count")
        max_chars = int(params.get("max_chars_per_file", 8_000))
        start_char = int(params.get("start_char", 0))
        preserve_layout = bool(params.get("preserve_layout", True))
        started = time.monotonic()
        deadline = started + max(0.1, timeout)
        worker_count = min(4, len(matches))

        def extract_one(item: tuple[int, Path], output_root: Path) -> dict[str, Any]:
            index, source = item
            remaining = deadline - time.monotonic()
            if remaining <= 0.1:
                return {
                    "path": str(source),
                    "status": "error",
                    "error": {
                        "code": "OPERATION_TIMEOUT",
                        "message": "PDF extraction deadline expired before launch",
                    },
                }
            output_path = output_root / f"{index:04d}.txt"
            argv = [
                executable,
                "-enc",
                "UTF-8",
                "-f",
                str(start_page),
            ]
            if page_count is not None:
                argv.extend(["-l", str(start_page + int(page_count) - 1)])
            if preserve_layout:
                argv.append("-layout")
            argv.extend([str(source), str(output_path)])
            try:
                command_result = self.runner.run(
                    argv,
                    timeout=remaining,
                    check=False,
                    cwd=str(input_directory),
                )
            except AdapterError as error:
                return {
                    "path": str(source),
                    "status": "error",
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                    },
                }
            if command_result["returncode"] != 0 or not output_path.is_file():
                return {
                    "path": str(source),
                    "status": "error",
                    "error": {
                        "code": "PDF_TEXT_EXTRACTION_FAILED",
                        "message": "pdftotext did not create a readable output",
                        "command_result": command_result,
                    },
                }
            raw_text = output_path.read_text(encoding="utf-8", errors="replace")
            text = _compact_pdf_layout_text(raw_text) if preserve_layout else raw_text
            window, window_start, window_end, source_truncated = _text_window(
                text, start_char=start_char, max_chars=max_chars
            )
            return {
                "path": str(source),
                "status": "ok",
                "text": window,
                "returned_chars": len(window),
                "extracted_chars": len(text),
                "raw_extracted_chars": len(raw_text),
                "layout_compacted": preserve_layout,
                "source_start_char": window_start,
                "source_end_char": window_end,
                "source_total_chars": len(text),
                "next_start_char": window_end if source_truncated else None,
                "offset_basis": (
                    "layout_compacted_text" if preserve_layout else "extracted_text"
                ),
                "source_truncated": source_truncated,
                "truncated": source_truncated,
                "command_result": command_result,
            }

        with tempfile.TemporaryDirectory(prefix="osworld-pdf-text-") as output:
            output_root = Path(output)
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                files = list(
                    executor.map(
                        lambda item: extract_one(item, output_root),
                        enumerate(matches),
                    )
                )

        failed = [item for item in files if item["status"] != "ok"]
        if failed:
            raise AdapterError(
                "PDF_TEXT_EXTRACTION_INCOMPLETE",
                "text could not be extracted from every matching PDF",
                {
                    "directory": str(input_directory),
                    "input_pattern": pattern,
                    "files": files,
                    "failed": failed,
                },
                422,
            )
        return {
            "input_directory": str(input_directory),
            "input_pattern": pattern,
            "matched": [str(path) for path in matches],
            "hidden_matches_excluded": len(all_matches) - len(visible_matches),
            "non_pdf_matches_excluded": len(visible_matches) - len(matches),
            "start_page": start_page,
            "page_count": page_count,
            "max_chars_per_file": max_chars,
            "preserve_layout": preserve_layout,
            "files": files,
            "total_returned_chars": sum(item["returned_chars"] for item in files),
            "parallel_workers": worker_count,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    def extract_image_text_batch(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        input_directory = _batch_input_directory(params, _ocr_candidate_directories)

        pattern = params["input_pattern"]
        include_hidden = bool(params.get("include_hidden", False))
        all_matches = sorted(
            path.resolve() for path in input_directory.glob(pattern) if path.is_file()
        )
        visible_matches = [
            path
            for path in all_matches
            if include_hidden or not path.name.startswith(".")
        ]
        matches = [
            path
            for path in visible_matches
            if path.suffix.casefold() in OCR_SOURCE_SUFFIXES
        ]
        if not matches:
            recovery = _ocr_candidate_directories(
                input_directory,
                pattern,
                include_hidden=include_hidden,
            )
            suggestions = recovery["suggested_directories"]
            message = (
                f"no supported image or PDF files match {pattern} directly in "
                f"{input_directory}"
            )
            if suggestions:
                message += (
                    "; matching OCR sources exist in suggested_directories, so retry with "
                    "cwd_source=explicit and one listed directory as cwd_path"
                )
            raise AdapterError(
                "NO_MATCHES",
                message,
                {
                    "directory": str(input_directory),
                    "input_pattern": pattern,
                    "supported_extensions": sorted(OCR_SOURCE_SUFFIXES),
                    "hidden_matches_excluded": len(all_matches) - len(visible_matches),
                    "unsupported_matches_excluded": len(visible_matches),
                    **recovery,
                },
                404,
            )

        max_files = int(params.get("max_files", 50))
        if len(matches) > max_files:
            raise AdapterError(
                "BATCH_LIMIT_EXCEEDED",
                f"{len(matches)} files match input_pattern, exceeding max_files={max_files}",
                {
                    "directory": str(input_directory),
                    "input_pattern": pattern,
                    "matched_files": len(matches),
                    "max_files": max_files,
                },
                422,
            )

        started = time.monotonic()
        deadline = started + max(0.1, timeout)
        tesseract = shutil.which("tesseract")
        if tesseract is None:
            raise AdapterError(
                "OCR_DEPENDENCY_UNAVAILABLE",
                "tesseract is unavailable; install OCR dependencies during guest preparation",
                http_status=503,
            )

        pdftoppm = shutil.which("pdftoppm")
        if (
            any(path.suffix.casefold() == ".pdf" for path in matches)
            and pdftoppm is None
        ):
            raise AdapterError(
                "PDF_RENDERER_UNAVAILABLE",
                "pdftoppm is required to OCR PDF pages but is not installed",
                http_status=503,
            )

        max_chars = int(params.get("max_chars_per_file", 8_000))
        start_char = int(params.get("start_char", 0))
        max_pages = int(params.get("max_pages_per_pdf", 8))
        # Two workers balance batch latency against tesseract CPU contention.
        worker_count = min(2, len(matches))

        def command_summary(result: dict[str, Any]) -> dict[str, Any]:
            return {
                "returncode": result.get("returncode"),
                "duration_ms": result.get("duration_ms"),
                "stderr": str(result.get("stderr", ""))[-1000:],
            }

        def failure(
            source: Path, code: str, message: str, details: Any = None
        ) -> dict[str, Any]:
            error = {"code": code, "message": message}
            if details is not None:
                error["details"] = details
            return {"path": str(source), "status": "error", "error": error}

        def extract_one(item: tuple[int, Path], output_root: Path) -> dict[str, Any]:
            index, source = item
            remaining = deadline - time.monotonic()
            if remaining <= 0.1:
                return failure(
                    source,
                    "OPERATION_TIMEOUT",
                    "OCR deadline expired before this file was processed",
                )
            file_root = output_root / f"{index:04d}"
            file_root.mkdir()
            render_result = None
            if source.suffix.casefold() == ".pdf":
                assert pdftoppm is not None
                prefix = file_root / "page"
                rendered = self.runner.run(
                    [
                        pdftoppm,
                        "-png",
                        "-r",
                        "200",
                        "-f",
                        "1",
                        "-l",
                        str(max_pages),
                        str(source),
                        str(prefix),
                    ],
                    timeout=max(0.1, deadline - time.monotonic()),
                    check=False,
                    cwd=str(input_directory),
                )
                render_result = command_summary(rendered)
                images = sorted(file_root.glob("page-*.png"))
                if rendered["returncode"] != 0 or not images:
                    return failure(
                        source,
                        "PDF_RENDER_FAILED",
                        "pdftoppm did not create readable page images",
                        render_result,
                    )
                source_kind = "pdf"
            else:
                images = [source]
                source_kind = "image"

            page_texts = []
            ocr_commands = []
            for page in images:
                remaining = deadline - time.monotonic()
                if remaining <= 0.1:
                    return failure(
                        source,
                        "OPERATION_TIMEOUT",
                        "OCR deadline expired while reading pages",
                        {
                            "pages_completed": len(page_texts),
                            "pages_planned": len(images),
                        },
                    )
                ocr_input = page
                if source_kind == "image" and Image is not None:
                    try:
                        with Image.open(page) as image:
                            # Keep OCR bounded for large receipt photos. The
                            # task needs text and totals, not source resolution.
                            max_dimension = 1000
                            if max(image.size) > max_dimension:
                                scale = max_dimension / max(image.size)
                                resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))))
                                ocr_input = file_root / "ocr-input.png"
                                resized.save(ocr_input, format="PNG")
                    except (OSError, ValueError):
                        ocr_input = page
                extracted = self.runner.run(
                    [tesseract, str(ocr_input), "stdout", "-l", "eng", "--psm", "11" if source_kind == "pdf" else "6", "--oem", "1"],
                    timeout=remaining,
                    check=False,
                    cwd=str(input_directory),
                )
                ocr_commands.append(command_summary(extracted))
                if extracted["returncode"] != 0:
                    return failure(
                        source,
                        "OCR_FAILED",
                        "tesseract failed to read an input page",
                        {
                            "page": page.name,
                            "command": ocr_commands[-1],
                        },
                    )
                page_texts.append(str(extracted.get("stdout", "")).strip())

            text = "\n\n".join(page_texts).strip()
            window, window_start, window_end, source_truncated = _text_window(
                text, start_char=start_char, max_chars=max_chars
            )
            return {
                "path": str(source),
                "status": "ok",
                "source_kind": source_kind,
                "pages_processed": len(images),
                "text": window,
                "returned_chars": len(window),
                "extracted_chars": len(text),
                "source_start_char": window_start,
                "source_end_char": window_end,
                "source_total_chars": len(text),
                "next_start_char": window_end if source_truncated else None,
                "offset_basis": "ocr_text",
                "source_truncated": source_truncated,
                "truncated": source_truncated,
                "empty_text": not bool(text),
                "render_command": render_result,
                "ocr_commands": ocr_commands,
            }

        # Bound both batch concurrency and each tesseract process. Without
        # this, OpenMP can oversubscribe the constrained guest and make one
        # large receipt consume the entire action timeout.
        ocr_env_keys = ("OMP_THREAD_LIMIT", "OMP_NUM_THREADS")
        prior_ocr_env = {key: os.environ.get(key) for key in ocr_env_keys}
        os.environ["OMP_THREAD_LIMIT"] = "1"
        os.environ["OMP_NUM_THREADS"] = "1"
        try:
            with tempfile.TemporaryDirectory(prefix="osworld-image-ocr-") as output:
                output_root = Path(output)
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    files = list(
                        executor.map(
                            lambda item: extract_one(item, output_root),
                            enumerate(matches),
                        )
                    )
        finally:
            for key, value in prior_ocr_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        successful = [item for item in files if item["status"] == "ok"]
        failed = [item for item in files if item["status"] != "ok"]
        if not successful:
            raise AdapterError(
                "OCR_EXTRACTION_FAILED",
                "OCR did not successfully read any matching file",
                {
                    "directory": str(input_directory),
                    "input_pattern": pattern,
                    "files": files,
                },
                422,
            )
        return {
            "input_directory": str(input_directory),
            "input_pattern": pattern,
            "matched": [str(path) for path in matches],
            "supported_extensions": sorted(OCR_SOURCE_SUFFIXES),
            "hidden_matches_excluded": len(all_matches) - len(visible_matches),
            "unsupported_matches_excluded": len(visible_matches) - len(matches),
            "max_chars_per_file": max_chars,
            "max_pages_per_pdf": max_pages,
            "ocr_engine": "tesseract",
            "ocr_language": "eng",
            "dependency_installed": False,
            "files": files,
            "successful_count": len(successful),
            "failed_count": len(failed),
            "total_returned_chars": sum(
                int(item["returned_chars"]) for item in successful
            ),
            "parallel_workers": worker_count,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    def launch_terminal(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self.run_command({**params, "terminal": True}, timeout)

    def ensure_account(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        username = params["username"]
        home = str(Path(params["home"]).expanduser())
        shell = params.get("shell", "/bin/bash")
        mode = int(params.get("mode", 0o750))
        exists = (
            self.runner.run(["getent", "passwd", username], check=False)["returncode"]
            == 0
        )
        if not exists:
            create_flag = "--no-create-home" if Path(home).exists() else "--create-home"
            self.runner.sudo(
                [
                    "useradd",
                    create_flag,
                    "--home-dir",
                    home,
                    "--shell",
                    shell,
                    username,
                ],
                timeout=timeout,
                error_code="USER_OPERATION_FAILED",
                error_message="failed to create user account",
            )
        else:
            self.runner.sudo(
                ["usermod", "--home", home, "--shell", shell, username],
                timeout=timeout,
                error_code="USER_OPERATION_FAILED",
                error_message="failed to update user account",
            )
        self.runner.sudo(
            ["mkdir", "-p", home], timeout=timeout, error_code="USER_OPERATION_FAILED"
        )
        group = self.runner.run(["id", "-gn", username])["stdout"].strip()
        self.runner.sudo(
            ["chown", "-R", f"{username}:{group}", home],
            timeout=timeout,
            error_code="USER_OPERATION_FAILED",
        )
        self.runner.sudo(
            ["chmod", f"{mode:o}", home],
            timeout=timeout,
            error_code="USER_OPERATION_FAILED",
        )
        password_hash = self.runner.run(
            ["openssl", "passwd", "-6", "-stdin"],
            input_text=params["password"] + "\n",
            error_code="USER_OPERATION_FAILED",
            error_message="failed to hash account password",
        )["stdout"].strip()
        self.runner.sudo(
            ["usermod", "--password", password_hash, username],
            timeout=timeout,
            error_code="USER_OPERATION_FAILED",
            error_message="failed to set account password",
        )
        return {
            "account": user_state(self.runner, username),
            "created": not exists,
            "mode": mode,
        }

    def install_snap(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        package = params["package"]
        state = package_state(self.runner, package)
        if not state["snap_installed"]:
            argv = ["snap", "install", package]
            if params.get("channel"):
                argv.append(f"--channel={params['channel']}")
            self.runner.sudo(
                argv,
                timeout=timeout,
                error_code="PACKAGE_INSTALL_FAILED",
                error_message=f"failed to install snap package {package}",
            )
        return package_state(self.runner, package)

    def dispatch(
        self, action: str, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        handlers = {
            "filesystem.find": self.find_files,
            "filesystem.create_directory": self.create_directory,
            "filesystem.copy": self.copy_file,
            "filesystem.copy_to_directories": self.copy_to_directories,
            "filesystem.rename": self.rename,
            "filesystem.set_permissions": self.set_permissions,
            "clipboard.get": self.get_clipboard,
            "clipboard.set": self.set_clipboard,
            "text.append_each_line": self.append_each_line,
            "trash.list": self.list_trash,
            "trash.restore": self.restore_trash,
            "notifications.configure": self.notifications_configure,
            "desktop.set_setting": self.set_setting,
            "desktop.open_path": self.open_path,
            "desktop.set_wallpaper": self.set_wallpaper,
            "desktop.applications.inspect": self.inspect_desktop_applications,
            "desktop.mime_associations.set": self.set_mime_associations,
            "desktop.set_accessibility_scale": self.set_accessibility_scale,
            "desktop.set_dim_inactive": self.set_dim_inactive,
            "desktop.favorites.list": self.list_favorites,
            "desktop.remove_favorite": self.remove_favorite,
            "audio.set_volume": self.set_volume,
            "system.set_timezone": self.set_timezone,
            "terminal.default_profile.inspect": self.inspect_terminal_default_profile,
            "terminal.default_profile.set_setting": self.set_terminal_default_profile_setting,
            "terminal.show_output": self.show_terminal_output,
            "terminal.launch": self.launch_terminal,
            "window.capture": self.capture_window,
            "document.convert": self.convert_document,
            "archive.create_zip": create_zip,
            "archive.extract_zip": extract_zip,
            "archive.compress_file": self.compress_file,
            "pdf.outline.inspect": inspect_pdf_outline,
            "pdf.form.inspect": inspect_pdf_form,
            "pdf.tables.inspect": inspect_pdf_table,
            "pdf.form.fill": fill_pdf_form,
            "pdf.pages.extract": extract_pdf_pages,
            "pdf.extract_text_batch": self.extract_pdf_text_batch,
            "image.extract_text_batch": self.extract_image_text_batch,
            "command.run": self.run_command,
            "user.ensure_account": self.ensure_account,
            "package.install_snap": self.install_snap,
        }
        handler = handlers.get(action)
        if handler is None:
            raise AdapterError(
                "UNSUPPORTED_ACTION",
                "action is not implemented",
                {"action": action},
                501,
            )
        return handler(params, timeout)
