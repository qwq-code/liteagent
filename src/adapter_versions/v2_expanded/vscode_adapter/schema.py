from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .debugging import (
    DEBUG_OPEN_MODES,
    DEBUG_WAIT_STATES,
    DEBUGGING_SETTING_FIELDS,
    INLINE_VALUE_MODES,
    INTERNAL_CONSOLE_MODES,
)
from .diagnostics import DIAGNOSTIC_SEVERITIES, DIAGNOSTIC_SETTING_KEYS
from .editor import (
    EDITOR_BOOLEAN_SETTINGS,
    EDITOR_ENUM_SETTINGS,
    EDITOR_INTEGER_SETTINGS,
    EDITOR_SETTING_FIELDS,
)
from .errors import AdapterError
from .explorer import EXCLUSION_SCOPES
from .files import (
    AUTO_SAVE_MODES,
    FILES_BOOLEAN_SETTINGS,
    FILES_SETTING_FIELDS,
    HOT_EXIT_MODES,
)
from .keybindings import KEYBINDING_OPERATION_COMMANDS


ADAPTER_NAME = "vs_code"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 900_000
DEFAULT_TIMEOUT_MS = 45_000

ACTIONS = frozenset(
    {
        "debugging.configure",
        "diagnostics.configure",
        "editor.configure",
        "files.configure",
        "settings.update",
        "keybindings.ensure",
        "extension.install",
        "workspace.inspect",
        "workspace.open",
        "workspace.find_files",
        "workspace.write",
        "workspace.set_folders",
        "workspace.add_folders",
        "file.create",
        "file.read_text",
        "file.replace_literal",
        "file.indent_lines",
        "explorer.set_exclusion",
        "editor.open_file",
        "ui.open_view",
        "ui.expand_section",
        "debug.breakpoint.set",
        "debug.start",
        "debug.session.wait",
        "debug.continue",
        "debug.stop",
        "debug.variables.read",
    }
)

VERIFY_TYPES = frozenset(
    {
        "file",
        "text",
        "json_subset",
        "keybinding",
        "extension",
        "workspace_open",
        "accessibility",
        "vscode_debug_session",
        "vscode_debug_variables",
    }
)


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    adapter: str
    action: str
    timeout_ms: int
    params: dict[str, Any]
    verify: list[dict[str, Any]]

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "timeout_ms": self.timeout_ms,
            "params": self.params,
            "verify": self.verify,
        }


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"{field} must be an object")
    return dict(value)


def _string(data: Mapping[str, Any], field: str, prefix: str = "params") -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-empty string"
        )
    return value


def _bool(data: Mapping[str, Any], field: str) -> None:
    if field in data and not isinstance(data[field], bool):
        raise AdapterError("INVALID_REQUEST", f"params.{field} must be a boolean")


def _integer(data: Mapping[str, Any], field: str, minimum: int, maximum: int) -> int:
    value = data.get(field)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.{field} must be an integer from {minimum} to {maximum}",
        )
    return value


def _string_list(data: Mapping[str, Any], field: str) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or not value:
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be a non-empty string array"
        )
    if any(not isinstance(item, str) or not item for item in value):
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must contain non-empty strings"
        )
    return value


def _object(data: Mapping[str, Any], field: str) -> dict[str, Any]:
    value = data.get(field)
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"params.{field} must be an object")
    return dict(value)


def _folders(data: Mapping[str, Any]) -> list[dict[str, str]]:
    value = data.get("folders")
    if not isinstance(value, list) or not value:
        raise AdapterError(
            "INVALID_REQUEST", "params.folders must be a non-empty array"
        )
    folders = []
    for index, item in enumerate(value):
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("path"), str)
            or not item["path"]
        ):
            raise AdapterError(
                "INVALID_REQUEST", f"params.folders[{index}].path is required"
            )
        folder = {"path": item["path"]}
        if "name" in item:
            if not isinstance(item["name"], str) or not item["name"]:
                raise AdapterError(
                    "INVALID_REQUEST", f"params.folders[{index}].name is invalid"
                )
            folder["name"] = item["name"]
        folders.append(folder)
    return folders


def _verification(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError("INVALID_REQUEST", "verify must be an array")
    checks = []
    for index, raw in enumerate(value):
        check = _mapping(raw, f"verify[{index}]")
        if check.get("type") not in VERIFY_TYPES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"verify[{index}].type is unsupported",
                {"type": check.get("type")},
            )
        checks.append(check)
    return checks


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    if action == "settings.update":
        _object(params, "values")
        if "path" in params:
            _string(params, "path")
    elif action == "debugging.configure":
        selected = set(params).intersection(DEBUGGING_SETTING_FIELDS)
        if not selected:
            raise AdapterError(
                "INVALID_REQUEST",
                "params must include exactly one documented debugging setting",
                {"setting_fields": sorted(DEBUGGING_SETTING_FIELDS)},
            )
        if len(selected) != 1:
            raise AdapterError(
                "INVALID_REQUEST",
                "debugging.configure accepts exactly one semantic setting per call",
                {
                    "fields": sorted(selected),
                    "retry": "Call debugging.configure once for each independent setting",
                },
            )
        for field in (
            "focus_editor_on_break",
            "show_breakpoints_in_overview_ruler",
            "show_inline_breakpoint_candidates",
        ):
            _bool(params, field)
        enum_fields = {
            "inline_values": INLINE_VALUE_MODES,
            "internal_console": INTERNAL_CONSOLE_MODES,
            "open_debug_view": DEBUG_OPEN_MODES,
        }
        for field, choices in enum_fields.items():
            if field not in params:
                continue
            value = _string(params, field)
            if value not in choices:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be one of {sorted(choices)}",
                )
        if "path" in params:
            _string(params, "path")
    elif action == "diagnostics.configure":
        language = _string(params, "language")
        diagnostic = _string(params, "diagnostic")
        severity = _string(params, "severity")
        if language not in DIAGNOSTIC_SETTING_KEYS:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.language must be one of {sorted(DIAGNOSTIC_SETTING_KEYS)}",
            )
        if diagnostic not in DIAGNOSTIC_SETTING_KEYS[language]:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.diagnostic is unsupported for the selected language",
                {
                    "language": language,
                    "supported": sorted(DIAGNOSTIC_SETTING_KEYS[language]),
                },
            )
        if severity not in DIAGNOSTIC_SEVERITIES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.severity must be one of {sorted(DIAGNOSTIC_SEVERITIES)}",
            )
        if "path" in params:
            _string(params, "path")
    elif action == "editor.configure":
        selected = set(params).intersection(EDITOR_SETTING_FIELDS)
        if not selected:
            raise AdapterError(
                "INVALID_REQUEST",
                "params must include exactly one documented editor setting",
                {"setting_fields": sorted(EDITOR_SETTING_FIELDS)},
            )
        if len(selected) != 1 and selected != {"word_wrap", "word_wrap_column"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "editor.configure accepts one semantic setting or the related word-wrap mode and column per call",
                {
                    "fields": sorted(selected),
                    "retry": "Call editor.configure once for each independent setting",
                },
            )
        for field in EDITOR_BOOLEAN_SETTINGS:
            _bool(params, field)
        for field, (_, choices) in EDITOR_ENUM_SETTINGS.items():
            if field in params and _string(params, field) not in choices:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be one of {sorted(choices)}",
                )
        for field in EDITOR_INTEGER_SETTINGS:
            if field in params:
                _integer(params, field, 1, 1000)
        if "path" in params:
            path = _string(params, "path")
            if not path.startswith(("/", "~/", "file://localhost/", "file:///")):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.path must be an absolute or ~/ settings.json path; omit it for active user settings",
                )
    elif action == "files.configure":
        selected = set(params).intersection(FILES_SETTING_FIELDS)
        if not selected:
            raise AdapterError(
                "INVALID_REQUEST",
                "params must include exactly one semantic files setting",
            )
        groups = (
            {"auto_save", "auto_save_delay_ms"},
            {"hot_exit"},
            {"insert_final_newline"},
            {"trim_final_newlines"},
            {"trim_trailing_whitespace"},
        )
        if sum(bool(group & selected) for group in groups) != 1:
            raise AdapterError(
                "INVALID_REQUEST",
                "files.configure accepts exactly one semantic setting per call; "
                "auto_save and auto_save_delay_ms may be paired",
                {"fields": sorted(selected)},
            )
        for field in FILES_BOOLEAN_SETTINGS:
            _bool(params, field)
        if (
            "auto_save" in params
            and _string(params, "auto_save") not in AUTO_SAVE_MODES
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.auto_save must be one of {sorted(AUTO_SAVE_MODES)}",
            )
        if "auto_save_delay_ms" in params:
            _integer(params, "auto_save_delay_ms", 1, 3_600_000)
        if "hot_exit" in params and _string(params, "hot_exit") not in HOT_EXIT_MODES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.hot_exit must be one of {sorted(HOT_EXIT_MODES)}",
            )
        if "path" in params:
            _string(params, "path")
    elif action == "keybindings.ensure":
        if "binding" in params:
            if set(params).intersection(
                {"key", "operation", "context", "command", "when", "disabled"}
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.binding cannot be combined with flat keybinding fields",
                )
            binding = _object(params, "binding")
            _string(binding, "key", "params.binding")
            _string(binding, "command", "params.binding")
            if "when" in binding:
                _string(binding, "when", "params.binding")
        elif "operation" in params:
            unexpected = sorted(set(params) - {"key", "operation", "disabled", "path"})
            if unexpected:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "semantic keybinding operation received unsupported parameters",
                    {"unexpected": unexpected},
                )
            _string(params, "key")
            operation = _string(params, "operation")
            if operation not in KEYBINDING_OPERATION_COMMANDS:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.operation is unsupported",
                    {"supported": sorted(KEYBINDING_OPERATION_COMMANDS)},
                )
            if "disabled" not in params:
                raise AdapterError(
                    "INVALID_REQUEST", "params.disabled must be a boolean"
                )
            _bool(params, "disabled")
        elif "context" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.context is encoded by the selected semantic operation",
            )
        else:
            _string(params, "key")
            _string(params, "command")
            _string(params, "when")
            if "disabled" not in params:
                raise AdapterError(
                    "INVALID_REQUEST", "params.disabled must be a boolean"
                )
            _bool(params, "disabled")
        if "path" in params:
            _string(params, "path")
    elif action == "extension.install":
        has_semantic_source = "source" in params or "source_type" in params
        if has_semantic_source:
            _string(params, "source")
            source_type = _string(params, "source_type")
            if source_type not in {"marketplace", "vsix"}:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.source_type must be marketplace or vsix",
                )
            if "extension" in params or "vsix_path" in params:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "semantic source cannot be combined with extension or vsix_path",
                )
        else:
            has_extension = isinstance(params.get("extension"), str) and bool(
                params["extension"].strip()
            )
            has_vsix = isinstance(params.get("vsix_path"), str) and bool(
                params["vsix_path"].strip()
            )
            if has_extension == has_vsix:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params requires exactly one of extension or vsix_path",
                )
        if "expected_id" in params:
            _string(params, "expected_id")
        _bool(params, "force")
    elif action == "workspace.inspect":
        if params:
            raise AdapterError(
                "INVALID_REQUEST", "workspace.inspect does not accept parameters"
            )
    elif action == "workspace.open":
        _string(params, "path")
        _bool(params, "reuse_window")
        _bool(params, "close_existing")
    elif action == "workspace.find_files":
        allowed = {
            "name_patterns",
            "kind",
            "recursive",
            "include_hidden",
            "max_depth",
            "max_results",
        }
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "workspace.find_files received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        patterns = _string_list(params, "name_patterns")
        if len(patterns) > 16 or len(set(patterns)) != len(patterns):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.name_patterns must contain at most 16 unique globs",
            )
        if params.get("kind", "file") not in {"file", "directory", "any"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.kind must be file, directory, or any"
            )
        for field in ("recursive", "include_hidden"):
            _bool(params, field)
        if "max_depth" in params:
            _integer(params, "max_depth", 1, 8)
        if "max_results" in params:
            _integer(params, "max_results", 1, 200)
    elif action in {
        "workspace.write",
        "workspace.set_folders",
        "workspace.add_folders",
    }:
        path = _string(params, "path")
        if action in {"workspace.write", "workspace.set_folders"} and not path.casefold().endswith(
            ".code-workspace"
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.path must be the complete .code-workspace filename, not a directory: {path}",
            )
        if action in {"workspace.write", "workspace.set_folders"} and not Path(path).is_absolute():
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.path must be an absolute .code-workspace filename: {path}",
            )
        _folders(params)
    elif action == "file.create":
        _string(params, "path")
        if "content" in params and not isinstance(params["content"], str):
            raise AdapterError("INVALID_REQUEST", "params.content must be a string")
        _bool(params, "overwrite")
        _bool(params, "open")
    elif action == "file.read_text":
        _string(params, "path")
        if "start_char" in params and (
            type(params["start_char"]) is not int or params["start_char"] < 0
        ):
            raise AdapterError("INVALID_REQUEST", "params.start_char must be a nonnegative integer")
        if "max_chars" in params:
            _integer(params, "max_chars", 1, 100_000)
    elif action == "file.replace_literal":
        _string(params, "path")
        old = params.get("old")
        if not isinstance(old, str) or not old:
            raise AdapterError("INVALID_REQUEST", "params.old must be a non-empty string")
        if not isinstance(params.get("new"), str):
            raise AdapterError("INVALID_REQUEST", "params.new must be a string")
    elif action == "file.indent_lines":
        _string(params, "path")
        start = _integer(params, "start_line", 1, 1_000_000)
        end = _integer(params, "end_line", 1, 1_000_000)
        if end < start:
            raise AdapterError(
                "INVALID_REQUEST", "params.end_line must be >= start_line"
            )
        has_indent = "indent" in params
        has_levels = "levels" in params
        if has_indent == has_levels:
            raise AdapterError(
                "INVALID_REQUEST",
                "params requires exactly one of indent or levels",
            )
        if has_indent:
            if not isinstance(params["indent"], str) or not params["indent"]:
                raise AdapterError(
                    "INVALID_REQUEST", "params.indent must be a non-empty string"
                )
        else:
            _integer(params, "levels", 1, 16)
    elif action == "explorer.set_exclusion":
        _string(params, "pattern")
        scope = _string(params, "scope")
        if scope not in EXCLUSION_SCOPES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.scope must be one of {sorted(EXCLUSION_SCOPES)}",
            )
        if "hidden" not in params:
            raise AdapterError("INVALID_REQUEST", "params.hidden must be a boolean")
        _bool(params, "hidden")
        if "path" in params:
            _string(params, "path")
    elif action == "editor.open_file":
        allowed = {"path", "reuse_window"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "editor.open_file received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        path = _string(params, "path")
        if not path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST", "params.path must be absolute or begin with ~/"
            )
        _bool(params, "reuse_window")
    elif action == "ui.open_view":
        allowed = {"window_id", "view"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "ui.open_view received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        window_id = _string(params, "window_id")
        if re.fullmatch(r"0x[0-9A-Fa-f]+", window_id) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.window_id must be a wmctrl ID"
            )
        if _string(params, "view") not in {
            "explorer",
            "search",
            "source_control",
            "run_and_debug",
            "extensions",
        }:
            raise AdapterError("INVALID_REQUEST", "params.view is unsupported")
    elif action == "ui.expand_section":
        allowed = {"window_id", "name"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "ui.expand_section received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        window_id = _string(params, "window_id")
        if re.fullmatch(r"0x[0-9A-Fa-f]+", window_id) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.window_id must be a wmctrl ID"
            )
        name = _string(params, "name")
        if len(name) > 256:
            raise AdapterError(
                "INVALID_REQUEST", "params.name must contain at most 256 characters"
            )
    elif action == "debug.breakpoint.set":
        allowed = {"window_id", "path", "line"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "debug.breakpoint.set received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        window_id = _string(params, "window_id")
        if re.fullmatch(r"0x[0-9A-Fa-f]+", window_id) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.window_id must be a wmctrl ID"
            )
        path = _string(params, "path")
        if not path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST", "params.path must be absolute or begin with ~/"
            )
        _integer(params, "line", 1, 1_000_000)
    elif action == "debug.start":
        allowed = {"window_id"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "debug.start received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        window_id = _string(params, "window_id")
        if re.fullmatch(r"0x[0-9A-Fa-f]+", window_id) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.window_id must be a wmctrl ID"
            )
    elif action == "debug.session.wait":
        allowed = {"window_id", "state"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "debug.session.wait received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        window_id = _string(params, "window_id")
        if re.fullmatch(r"0x[0-9A-Fa-f]+", window_id) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.window_id must be a wmctrl ID"
            )
        if _string(params, "state") not in DEBUG_WAIT_STATES:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.state must be paused or running",
            )
    elif action in {"debug.continue", "debug.stop"}:
        allowed = {"window_id"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                f"{action} received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        window_id = _string(params, "window_id")
        if re.fullmatch(r"0x[0-9A-Fa-f]+", window_id) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.window_id must be a wmctrl ID"
            )
    elif action == "debug.variables.read":
        allowed = {"window_id", "max_items"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "debug.variables.read received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        window_id = _string(params, "window_id")
        if re.fullmatch(r"0x[0-9A-Fa-f]+", window_id) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.window_id must be a wmctrl ID"
            )
        if "max_items" in params:
            _integer(params, "max_items", 1, 1024)


def parse_action_request(raw: Any) -> ActionRequest:
    data = _mapping(raw, "request")
    action = data.get("action")
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_ACTION", "unsupported VS Code action", {"action": action}
        )
    adapter = data.get("adapter", ADAPTER_NAME)
    if adapter != ADAPTER_NAME:
        raise AdapterError("INVALID_REQUEST", f"adapter must be {ADAPTER_NAME}")
    request_id = data.get("request_id") or str(uuid4())
    if not isinstance(request_id, str) or not request_id.strip():
        raise AdapterError("INVALID_REQUEST", "request_id must be a non-empty string")
    timeout_ms = data.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, int)
        or not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            f"timeout_ms must be from {MIN_TIMEOUT_MS} to {MAX_TIMEOUT_MS}",
        )
    params = _mapping(data.get("params"), "params")
    validate_action_params(action, params)
    return ActionRequest(
        request_id=request_id,
        adapter=adapter,
        action=action,
        timeout_ms=timeout_ms,
        params=params,
        verify=_verification(data.get("verify")),
    )
