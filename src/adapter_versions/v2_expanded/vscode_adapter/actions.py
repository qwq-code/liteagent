from __future__ import annotations

import re
import time
from math import gcd
from pathlib import Path
from typing import Any

from .accessibility_state import (
    expand_accessible_section,
    inspect_debug_variables,
    wait_for_active_window,
    wait_for_debug_session,
    wait_for_debug_state,
)
from .command import CommandRunner
from .controller_accessibility import (
    wait_for_breakpoints_view,
    wait_for_source_breakpoint,
)
from .debug_control import continue_debug_session, stop_debug_session
from .debugging import DEBUGGING_SETTING_FIELDS, debugging_settings
from .diagnostics import diagnostic_setting
from .editor import EDITOR_SETTING_FIELDS, editor_settings
from .errors import AdapterError
from .explorer import exclusion_setting
from .extensions import resolve_installed_extension_id, vsix_extension_id
from .offline_extensions import offline_extension_path
from .files import FILES_SETTING_FIELDS, file_settings
from .jsonfiles import atomic_write_json, atomic_write_text, deep_merge, load_json
from .keybindings import normalize_binding
from .verifier import extension_state, window_state
from .workspace_discovery import (
    find_workspace_files,
    resolve_active_workspace,
    resolve_active_workspace_file,
)


SETTINGS_PATH = Path("/home/user/.config/Code/User/settings.json")
KEYBINDINGS_PATH = Path("/home/user/.config/Code/User/keybindings.json")
SIBLING_FILE_LIMIT = 16
VIEW_HOTKEYS = {
    "explorer": ("ctrl", "shift", "e"),
    "search": ("ctrl", "shift", "f"),
    "source_control": ("ctrl", "shift", "g"),
    "run_and_debug": ("ctrl", "shift", "d"),
    "extensions": ("ctrl", "shift", "x"),
}
DEBUG_START_KEY = "f5"
DEBUG_SET_BREAKPOINT_KEY = "f9"


def _file(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"file does not exist: {target}. For a file in the active VS Code project, "
            "use workspace.find_files with name_patterns to get its exact path; "
            "use tools_search if this action is not exposed. Do not guess the workspace root.",
            http_status=404,
        )
    return target


def _path(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.exists():
        raise AdapterError(
            "PATH_NOT_FOUND", f"path does not exist: {target}", http_status=404
        )
    return target


def _sibling_file_paths(path: Path) -> tuple[list[str], int, bool]:
    candidates: list[Path] = []
    try:
        entries = path.parent.iterdir()
        for entry in entries:
            if entry == path or entry.name.startswith("."):
                continue
            try:
                if entry.is_file():
                    candidates.append(entry)
            except OSError:
                continue
    except OSError:
        return [], 0, False
    candidates.sort(key=lambda item: (item.name.casefold(), item.name))
    returned = candidates[:SIBLING_FILE_LIMIT]
    return (
        [str(candidate) for candidate in returned],
        len(candidates),
        len(candidates) > len(returned),
    )


class VscodeActions:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def settings_update(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        path = Path(params.get("path", SETTINGS_PATH)).expanduser()
        before = load_json(path, dict, {})
        values = dict(params["values"])
        after = deep_merge(before, values)
        atomic_write_json(path, after)
        return {"path": str(path), "values": values, "before": before, "after": after}

    def explorer_set_exclusion(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        exclusion_key, values = exclusion_setting(
            str(params["pattern"]),
            str(params["scope"]),
            bool(params["hidden"]),
        )
        update_params: dict[str, Any] = {"values": values}
        if "path" in params:
            update_params["path"] = params["path"]
        result = self.settings_update(update_params, timeout)
        return {
            **result,
            "pattern": params["pattern"],
            "scope": params["scope"],
            "hidden": params["hidden"],
            "exclusion_key": exclusion_key,
        }

    def diagnostics_configure(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        language = str(params["language"])
        diagnostic = str(params["diagnostic"])
        severity = str(params["severity"])
        setting_key, values = diagnostic_setting(language, diagnostic, severity)
        update_params: dict[str, Any] = {"values": values}
        if "path" in params:
            update_params["path"] = params["path"]
        result = self.settings_update(update_params, timeout)
        return {
            **result,
            "language": language,
            "diagnostic": diagnostic,
            "severity": severity,
            "setting_key": setting_key,
        }

    def debugging_configure(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        values = debugging_settings(params)
        update_params: dict[str, Any] = {"values": values}
        if "path" in params:
            update_params["path"] = params["path"]
        result = self.settings_update(update_params, timeout)
        return {
            **result,
            "configured": {
                field: params[field]
                for field in DEBUGGING_SETTING_FIELDS
                if field in params
            },
        }

    def editor_configure(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        values = editor_settings(params)
        update_params: dict[str, Any] = {"values": values}
        if "path" in params:
            update_params["path"] = params["path"]
        result = self.settings_update(update_params, timeout)
        return {
            **result,
            "configured": {
                field: params[field]
                for field in EDITOR_SETTING_FIELDS
                if field in params
            },
        }

    def files_configure(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        values = file_settings(params)
        update_params: dict[str, Any] = {"values": values}
        if "path" in params:
            update_params["path"] = params["path"]
        result = self.settings_update(update_params, timeout)
        return {
            **result,
            "configured": {
                field: params[field]
                for field in FILES_SETTING_FIELDS
                if field in params
            },
        }

    def keybindings_ensure(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        path = Path(params.get("path", KEYBINDINGS_PATH)).expanduser()
        bindings = load_json(path, list, [])
        binding = normalize_binding(params)
        already_present = binding in bindings
        if not already_present:
            bindings.append(binding)
            atomic_write_json(path, bindings)
        command = str(binding.get("command", ""))
        return {
            "path": str(path),
            "binding": binding,
            "disabled": command.startswith("-"),
            "effective_command": command.removeprefix("-"),
            "already_present": already_present,
            "bindings": bindings,
        }

    def extension_install(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        source_type = params.get("source_type")
        selected_source = params.get("source")
        requested_source: str | None = None
        resolution = "explicit"
        if source_type == "marketplace":
            extension = str(selected_source)
            requested_source = extension
            vsix_path = None
            cached_path = offline_extension_path(extension)
            if cached_path is not None:
                vsix_path = str(cached_path)
                resolution = "verified_offline_cache"
        elif source_type == "vsix":
            extension = None
            vsix_path = str(selected_source)
        else:
            extension = params.get("extension")
            vsix_path = params.get("vsix_path")

        source = vsix_path or extension
        if vsix_path:
            source = str(_file(str(vsix_path)))
        metadata_extension_id = params.get("expected_id") or extension
        if not metadata_extension_id and vsix_path:
            metadata_extension_id = vsix_extension_id(Path(str(source)))
        before = extension_state(self.runner, str(metadata_extension_id))
        installed_extension_id = (
            resolve_installed_extension_id(
                str(metadata_extension_id),
                before["ids"],
                before["ids"],
            )
            if vsix_path
            else (
                str(metadata_extension_id).casefold() if before["installed"] else None
            )
        )
        if installed_extension_id:
            return {
                "extension_id": installed_extension_id,
                "metadata_extension_id": str(metadata_extension_id),
                "source": source,
                "source_type": "vsix" if vsix_path else "marketplace",
                "already_installed": True,
                **({"requested_source": requested_source, "resolution": resolution} if requested_source else {}),
            }
        argv = ["code", "--install-extension", str(source)]
        if params.get("force", True):
            argv.append("--force")
        result = self.runner.run(
            argv,
            timeout=timeout,
            error_code="EXTENSION_INSTALL_FAILED",
            error_message="VS Code extension installation failed",
        )
        observed = extension_state(self.runner, str(metadata_extension_id))
        installed_extension_id = (
            resolve_installed_extension_id(
                str(metadata_extension_id),
                before["ids"],
                observed["ids"],
            )
            if vsix_path
            else (
                str(metadata_extension_id).casefold() if observed["installed"] else None
            )
        )
        if not installed_extension_id:
            raise AdapterError(
                "EXTENSION_INSTALL_FAILED",
                "extension was not present after installation",
                {
                    "command": result,
                    "metadata_extension_id": metadata_extension_id,
                    "before": before,
                    "observed": observed,
                },
                422,
            )
        return {
            "extension_id": installed_extension_id,
            "metadata_extension_id": str(metadata_extension_id),
            "source": str(source),
            "source_type": "vsix" if vsix_path else "marketplace",
            "already_installed": False,
            "stdout": result["stdout"],
            **({"requested_source": requested_source, "resolution": resolution} if requested_source else {}),
        }

    def workspace_open(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        path = _path(params["path"]).resolve()
        if params.get("close_existing", False):
            current = self.runner.run(["wmctrl", "-lx"], check=False, timeout=10)[
                "stdout"
            ]
            for line in current.splitlines():
                if "code.Code" in line:
                    self.runner.run(
                        ["wmctrl", "-ic", line.split()[0]], check=False, timeout=5
                    )
            deadline = time.monotonic() + min(timeout, 10)
            while time.monotonic() < deadline:
                remaining = self.runner.run(["wmctrl", "-lx"], check=False, timeout=5)[
                    "stdout"
                ]
                if "code.Code" not in remaining:
                    break
                time.sleep(0.25)
            else:
                self.runner.run(
                    [
                        "pkill",
                        "-TERM",
                        "-u",
                        str(Path.home().stat().st_uid),
                        "-x",
                        "code",
                    ],
                    check=False,
                    timeout=10,
                )
                time.sleep(1)
        argv = [
            "code",
            "--reuse-window" if params.get("reuse_window", True) else "--new-window",
            str(path),
        ]
        self.runner.run(
            argv,
            timeout=min(timeout, 60),
            error_code="VSCODE_NOT_READY",
            error_message="failed to open VS Code workspace",
        )
        expected_name = path.stem if path.suffix == ".code-workspace" else path.name
        deadline = time.monotonic() + min(timeout, 30)
        observed = window_state(self.runner, expected_name)
        while not observed["matches"] and time.monotonic() < deadline:
            time.sleep(0.25)
            observed = window_state(self.runner, expected_name)
        if not observed["matches"]:
            raise AdapterError(
                "WINDOW_NOT_FOUND",
                "VS Code did not expose the expected workspace window",
                observed,
                422,
            )
        window_id = observed["matches"][0].split()[0]
        if params.get("close_existing", False):
            for line in observed["windows"]:
                candidate_id = line.split()[0]
                if candidate_id != window_id:
                    self.runner.run(
                        ["wmctrl", "-ic", candidate_id], check=False, timeout=5
                    )
            time.sleep(0.5)
            observed = window_state(self.runner, expected_name)
        self.runner.run(["wmctrl", "-ia", window_id], check=False, timeout=5)
        return {
            "path": str(path),
            "expected_name": expected_name,
            "window_id": window_id,
            "window": observed,
        }

    def workspace_find_files(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        workspace = resolve_active_workspace(self.runner)
        return find_workspace_files(workspace, params)

    def workspace_inspect(
        self, _params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        observed = resolve_active_workspace(self.runner)
        try:
            saved = resolve_active_workspace_file(self.runner)
        except AdapterError:
            return observed
        if saved.get("window_id") != observed.get("window_id"):
            return observed
        return {**observed, "workspace_file": saved["workspace_file"]}

    def workspace_write(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        path = Path(params["path"]).expanduser()
        value = {
            "folders": self._portable_workspace_folders(path, params["folders"]),
            "settings": {},
        }
        atomic_write_json(path, value)
        return {"path": str(path), "workspace": value}

    def workspace_set_folders(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        path = Path(params["path"]).expanduser()
        current = load_json(path, dict, {})
        current["folders"] = self._portable_workspace_folders(path, params["folders"])
        atomic_write_json(path, current)
        return {"path": str(path), "workspace": current}

    def workspace_add_folders(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        requested_path = Path(params["path"]).expanduser().resolve()
        active_workspace: dict[str, Any] | None = None
        if requested_path.is_dir():
            try:
                active_workspace = resolve_active_workspace_file(self.runner)
            except AdapterError as error:
                raise AdapterError(
                    error.code,
                    "workspace.add_folders.path is a directory. Pass the exact "
                    "workspace_file returned by workspace.inspect; the directory can "
                    "only be resolved when it is the unique active workspace root and "
                    "a saved .code-workspace file is observable. "
                    f"Resolution failed: {error.message}",
                    error.details,
                    error.http_status,
                ) from error
            roots = {
                Path(root).expanduser().resolve()
                for root in active_workspace.get("workspace_roots", [])
                if isinstance(root, str)
            }
            if requested_path not in roots:
                raise AdapterError(
                    "INVALID_ARGUMENT",
                    "workspace.add_folders.path is a directory but is not an "
                    "observed root of the active workspace. Use the exact "
                    "workspace_file returned by workspace.inspect.",
                    {
                        "path": str(requested_path),
                        "active_workspace_roots": sorted(str(root) for root in roots),
                        "workspace_file": active_workspace.get("workspace_file"),
                    },
                    422,
                )
            path = _file(str(active_workspace["workspace_file"])).resolve()
        else:
            path = _file(str(requested_path)).resolve()
        current = load_json(path, dict, {})
        existing = current.get("folders", [])
        if not isinstance(existing, list):
            raise AdapterError(
                "INVALID_JSON",
                f"workspace folders must be an array: {path}",
            )

        # VS Code displays a folder's basename when no custom name is set.
        # A matching explicit name has no effect and only makes the saved
        # workspace JSON less portable across tools that compare folder entries.
        requested_additions = []
        for folder in params["folders"]:
            item = dict(folder)
            if item.get("name") == Path(item["path"]).expanduser().name:
                item.pop("name")
            requested_additions.append(item)
        additions = self._portable_workspace_folders(path, requested_additions)
        seen = {
            identity
            for folder in existing
            if isinstance(folder, dict)
            if (identity := self._workspace_folder_identity(path, folder)) is not None
        }
        added: list[dict[str, Any]] = []
        already_present: list[dict[str, Any]] = []
        for folder in additions:
            identity = self._workspace_folder_identity(path, folder)
            if identity is not None and identity in seen:
                already_present.append(folder)
                continue
            added.append(folder)
            if identity is not None:
                seen.add(identity)

        current["folders"] = [*existing, *added]
        if added:
            atomic_write_json(path, current)
        result = {
            "path": str(path),
            "workspace": current,
            "added_folders": added,
            "already_present_folders": already_present,
        }
        if active_workspace is not None:
            result["active_workspace"] = active_workspace
            result["resolution_source"] = "active_workspace_root"
        return result

    @staticmethod
    def _workspace_folder_identity(
        workspace_path: Path,
        folder: dict[str, Any],
    ) -> str | None:
        raw_path = folder.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return None
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_path.resolve().parent / candidate
        return str(candidate.resolve())

    @staticmethod
    def _portable_workspace_folders(
        workspace_path: Path,
        folders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        base = workspace_path.resolve().parent
        normalized = []
        for folder in folders:
            item = dict(folder)
            candidate = Path(item["path"]).expanduser()
            if candidate.is_absolute():
                try:
                    item["path"] = candidate.resolve().relative_to(base).as_posix()
                except ValueError:
                    item["path"] = str(candidate)
            normalized.append(item)
        return normalized

    def file_create(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        path = Path(params["path"]).expanduser()
        content = params.get("content", "")
        already_present = path.is_file() and path.read_text(encoding="utf-8") == content
        if path.exists() and not path.is_file():
            raise AdapterError("INVALID_ARGUMENT", f"target is not a file: {path}")
        if not already_present:
            if path.exists() and not params.get("overwrite", False):
                raise AdapterError(
                    "DESTINATION_CONFLICT",
                    f"file already exists: {path}",
                    http_status=409,
                )
            atomic_write_text(path, content)
        opened = None
        if params.get("open", False):
            opened = self.workspace_open(
                {"path": str(path), "reuse_window": True}, timeout
            )
        return {
            "path": str(path),
            "content": content,
            "already_present": already_present,
            "opened": opened,
        }

    def file_read_text(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        path = _file(params["path"])
        content = path.read_text(encoding="utf-8")
        start_char = params.get("start_char", 0)
        if start_char > len(content):
            raise AdapterError(
                "INVALID_REQUEST",
                "start_char exceeds the source text length",
                {"path": str(path), "start_char": start_char, "source_total_chars": len(content)},
            )
        max_chars = int(params.get("max_chars", 20_000))
        end_char = min(start_char + max_chars, len(content))
        returned = content[start_char:end_char]
        sibling_file_paths, sibling_file_count, sibling_files_truncated = (
            _sibling_file_paths(path)
        )
        return {
            "path": str(path),
            "content": returned,
            "total_chars": len(content),
            "total_lines": len(content.splitlines()),
            "truncated": end_char < len(content),
            "source_start_char": start_char,
            "source_end_char": end_char,
            "source_total_chars": len(content),
            "next_start_char": end_char if end_char < len(content) else None,
            "offset_basis": "unicode_characters",
            "source_truncated": end_char < len(content),
            "sibling_file_paths": sibling_file_paths,
            "sibling_file_count": sibling_file_count,
            "sibling_files_truncated": sibling_files_truncated,
        }

    def file_replace_literal(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        path = _file(params["path"])
        content = path.read_text(encoding="utf-8")
        old = params["old"]
        new = params["new"]
        count = content.count(old)
        if count == 0:
            raise AdapterError(
                "TEXT_NOT_FOUND",
                f"literal was not found in {path}; the file was not changed. "
                "old must match exactly, including whitespace and newlines. "
                "Read the current text with file.read_text and choose old from "
                "that observation; multiline replacement is supported.",
                {"literal": old},
                404,
            )
        updated = content.replace(old, new)
        atomic_write_text(path, updated)
        return {
            "path": str(path),
            "content": updated,
            "replacement_count": count,
            "already_applied": False,
        }

    def file_indent_lines(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        path = _file(params["path"])
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        start = int(params["start_line"])
        end = int(params["end_line"])
        if start > len(lines):
            raise AdapterError("INVALID_ARGUMENT", "start_line is beyond end of file")
        levels = params.get("levels")
        if levels is None:
            indent = params["indent"]
            indentation_unit = indent
            indentation_source = "explicit_legacy_indent"
        else:
            indentation_unit, indentation_source = self._editor_indentation_unit(
                content
            )
            indent = indentation_unit * int(levels)
        for index in range(start - 1, min(end, len(lines))):
            lines[index] = indent + lines[index]
        updated = "".join(lines)
        atomic_write_text(path, updated)
        return {
            "path": str(path),
            "content": updated,
            "start_line": start,
            "end_line": min(end, len(lines)),
            "indent": indent,
            "levels": levels,
            "indentation_unit": indentation_unit,
            "indentation_source": indentation_source,
            "repeat_effect": "repeating adds another indent",
        }

    @staticmethod
    def _editor_indentation_unit(content: str) -> tuple[str, str]:
        prefixes = re.findall(r"(?m)^([ \t]+)\S", content)
        tab_prefixes = [prefix for prefix in prefixes if "\t" in prefix]
        space_counts = [len(prefix) for prefix in prefixes if not prefix.strip(" ")]
        if tab_prefixes and len(tab_prefixes) >= len(space_counts):
            return "\t", "detected_tabs"
        if space_counts:
            width = gcd(*space_counts)
            if width > 8:
                width = 4 if all(count % 4 == 0 for count in space_counts) else 8
            return " " * max(1, width), "detected_spaces"
        return "    ", "default_four_spaces"

    def editor_open_file(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        path = _file(params["path"]).resolve()
        self.runner.run(
            [
                "code",
                "--reuse-window"
                if params.get("reuse_window", True)
                else "--new-window",
                "--goto",
                f"{path}:1:1",
            ],
            timeout=min(timeout, 60),
            error_code="VSCODE_NOT_READY",
            error_message="failed to open the selected file in VS Code",
        )
        deadline = time.monotonic() + min(timeout, 30)
        windows = window_state(self.runner, path.name)
        while not windows["matches"] and time.monotonic() < deadline:
            time.sleep(0.25)
            windows = window_state(self.runner, path.name)
        if not windows["matches"]:
            raise AdapterError(
                "WINDOW_NOT_FOUND",
                "VS Code file window was not ready",
                windows,
                422,
            )
        window_id = windows["matches"][0].split()[0]
        self.runner.run(["wmctrl", "-ia", window_id], check=False, timeout=5)
        return {
            "path": str(path),
            "expected_name": path.name,
            "window_id": window_id,
            "windows": windows["matches"],
            "reuse_window": bool(params.get("reuse_window", True)),
        }

    def ui_open_view(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        window_id = params["window_id"]
        view = params["view"]
        hotkey = VIEW_HOTKEYS[view]
        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        self.runner.run(
            [
                "python3",
                "-c",
                "import pyautogui,time; "
                f"pyautogui.hotkey({','.join(repr(key) for key in hotkey)}); "
                "time.sleep(1)",
            ],
            timeout=10,
            error_code="VSCODE_NOT_READY",
            error_message=f"failed to open VS Code {view} view",
        )
        return {
            "window_id": window.window_id,
            "window_title": window.title,
            "view": view,
            "hotkey": list(hotkey),
        }

    def ui_expand_section(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        window_id = params["window_id"]
        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        section = expand_accessible_section(
            self.runner,
            window.window_id,
            params["name"],
            timeout,
        )
        return {
            "window_id": window.window_id,
            "window_title": window.title,
            "section": section,
        }

    def debug_start(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        started = time.monotonic()
        window_id = params["window_id"]
        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        self.runner.run(
            [
                "python3",
                "-c",
                "import pyautogui; pyautogui.press('f5')",
            ],
            timeout=10,
            error_code="VSCODE_NOT_READY",
            error_message="failed to start VS Code debugging",
        )
        session = wait_for_debug_session(
            self.runner,
            window.window_id,
            max(0.1, timeout - (time.monotonic() - started)),
        )
        return {
            "window_id": window.window_id,
            "window_title": window.title,
            "key": DEBUG_START_KEY,
            "session": session,
        }

    def debug_breakpoint_set(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        started = time.monotonic()
        window_id = params["window_id"]
        path = _file(params["path"]).resolve()
        line = int(params["line"])
        source_lines = path.read_text(encoding="utf-8").splitlines()
        if line > max(1, len(source_lines)):
            raise AdapterError(
                "INVALID_ARGUMENT",
                "breakpoint line is beyond end of file",
                {"path": str(path), "line": line, "line_count": len(source_lines)},
            )

        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        self.runner.run(
            [
                "python3",
                "-c",
                "import pyautogui,time; pyautogui.hotkey('ctrl','shift','d'); time.sleep(1)",
            ],
            timeout=10,
            error_code="VSCODE_NOT_READY",
            error_message="failed to open the VS Code Run and Debug view",
        )
        before = wait_for_breakpoints_view(
            window.window_id,
            window.title,
            path,
            line,
            min(10, max(0.1, timeout - (time.monotonic() - started))),
        )
        if before["match_count"] == 1 and before["checked_count"] == 1:
            return {
                "window_id": window.window_id,
                "window_title": window.title,
                "path": str(path),
                "expected_name": path.name,
                "line": line,
                "line_text": source_lines[line - 1] if source_lines else "",
                "key": None,
                "already_set": True,
                "before": before,
                "after": before,
            }
        if before["match_count"] or before["checked_count"]:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "existing breakpoint state is ambiguous for the requested path and line",
                before,
                422,
            )
        self.runner.run(
            ["code", "--reuse-window", "--goto", f"{path}:{line}:1"],
            timeout=min(60, max(0.1, timeout - (time.monotonic() - started))),
            error_code="VSCODE_NOT_READY",
            error_message="failed to select the requested breakpoint location",
        )
        self.runner.run(["wmctrl", "-ia", window.window_id], timeout=10)
        selected_window = wait_for_active_window(
            self.runner,
            window.window_id,
            min(10, max(0.1, timeout - (time.monotonic() - started))),
        )
        if path.name.casefold() not in selected_window.title.casefold():
            raise AdapterError(
                "WINDOW_NOT_FOUND",
                "requested file did not become active in the selected VS Code window",
                {
                    "window_id": selected_window.window_id,
                    "window_title": selected_window.title,
                    "path": str(path),
                },
                422,
            )
        self.runner.run(
            [
                "python3",
                "-c",
                "import pyautogui; pyautogui.press('f9')",
            ],
            timeout=10,
            error_code="VSCODE_NOT_READY",
            error_message="failed to toggle the VS Code breakpoint",
        )
        after = wait_for_source_breakpoint(
            selected_window.window_id,
            selected_window.title,
            path,
            line,
            min(10, max(0.1, timeout - (time.monotonic() - started))),
        )
        return {
            "window_id": selected_window.window_id,
            "window_title": selected_window.title,
            "path": str(path),
            "expected_name": path.name,
            "line": line,
            "line_text": source_lines[line - 1] if source_lines else "",
            "key": DEBUG_SET_BREAKPOINT_KEY,
            "already_set": False,
            "before": before,
            "after": after,
        }

    def debug_variables_read(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        window_id = params["window_id"]
        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        variables = inspect_debug_variables(
            self.runner,
            window.window_id,
            int(params.get("max_items", 256)),
        )
        return {
            "window_id": window.window_id,
            "window_title": window.title,
            "variables": variables,
        }

    def debug_session_wait(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        started = time.monotonic()
        window_id = params["window_id"]
        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        session = wait_for_debug_state(
            self.runner,
            window.window_id,
            params["state"],
            max(0.1, timeout - (time.monotonic() - started)),
        )
        return {
            "window_id": window.window_id,
            "window_title": window.title,
            "state": params["state"],
            "session": session,
        }

    def debug_continue(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        started = time.monotonic()
        window_id = params["window_id"]
        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        transition = continue_debug_session(
            self.runner,
            window.window_id,
            max(0.1, timeout - (time.monotonic() - started)),
        )
        return {
            "window_id": window.window_id,
            "window_title": window.title,
            **transition,
        }

    def debug_stop(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        started = time.monotonic()
        window_id = params["window_id"]
        self.runner.run(["wmctrl", "-ia", window_id], timeout=10)
        window = wait_for_active_window(self.runner, window_id, min(timeout, 10))
        transition = stop_debug_session(
            self.runner,
            window.window_id,
            max(0.1, timeout - (time.monotonic() - started)),
        )
        return {
            "window_id": window.window_id,
            "window_title": window.title,
            **transition,
        }

    def dispatch(
        self, action: str, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        method_name = action.replace(".", "_")
        method = getattr(self, method_name, None)
        if method is None:
            raise AdapterError(
                "UNSUPPORTED_ACTION", f"unsupported VS Code action: {action}"
            )
        return method(params, timeout)
