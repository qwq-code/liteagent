from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .errors import AdapterError
from .local_paths import (
    NON_ROOT_LOCAL_PATH_PATTERN,
    is_protected_local_root,
)


ADAPTER_NAME = "os"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 900_000
DEFAULT_TIMEOUT_MS = 45_000


def _is_explicit_local_path(value: str) -> bool:
    return value.startswith(("/", "~/", "file:///", "file://localhost/"))


ACTIONS = frozenset(
    {
        "filesystem.find",
        "filesystem.create_directory",
        "filesystem.copy",
        "filesystem.copy_to_directories",
        "filesystem.rename",
        "filesystem.set_permissions",
        "clipboard.get",
        "clipboard.set",
        "text.append_each_line",
        "trash.list",
        "trash.restore",
        "notifications.configure",
        "desktop.set_setting",
        "desktop.open_path",
        "desktop.set_wallpaper",
        "desktop.applications.inspect",
        "desktop.mime_associations.set",
        "desktop.set_accessibility_scale",
        "desktop.set_dim_inactive",
        "desktop.favorites.list",
        "desktop.remove_favorite",
        "audio.set_volume",
        "system.set_timezone",
        "terminal.default_profile.inspect",
        "terminal.default_profile.set_setting",
        "terminal.show_output",
        "terminal.launch",
        "window.capture",
        "document.convert",
        "archive.create_zip",
        "archive.extract_zip",
        "archive.compress_file",
        "pdf.outline.inspect",
        "pdf.form.inspect",
        "pdf.tables.inspect",
        "pdf.form.fill",
        "pdf.pages.extract",
        "pdf.extract_text_batch",
        "image.extract_text_batch",
        "command.run",
        "user.ensure_account",
        "package.install_snap",
    }
)

VERIFY_TYPES = frozenset(
    {
        "path",
        "directory",
        "mode_tree",
        "text",
        "archive_layout",
        "zip_archive",
        "clipboard",
        "trash_listing",
        "trash_restored",
        "gsettings",
        "desktop_favorites_listing",
        "mime_association",
        "desktop_applications_query",
        "pdf_outline_query",
        "volume",
        "timezone",
        "terminal",
        "terminal_launch",
        "terminal_size",
        "command_result",
        "user",
        "package",
    }
)


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    adapter: str
    action: str
    timeout_ms: int
    target: dict[str, Any]
    params: dict[str, Any]
    verify: list[dict[str, Any]]

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "timeout_ms": self.timeout_ms,
            "target": self.target,
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


def _validate_rename_explicit_path(value: str, field: str) -> None:
    if re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, value) is None:
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.{field} must be an absolute or ~/ path with a concrete basename",
        )
    try:
        path = Path(value).expanduser()
    except (OSError, RuntimeError):
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} is not a valid local path"
        ) from None
    if is_protected_local_root(path):
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.{field} must not resolve to the filesystem or home root",
        )


def _validate_rename_operand(value: str, field: str) -> None:
    """Accept an exact local path or one concrete basename, never a subpath."""
    if value.startswith(("/", "~/")):
        _validate_rename_explicit_path(value, field)
        return
    if not value or value in {"~", ".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise AdapterError(
            "INVALID_REQUEST",
            f"params.{field} must be an absolute or ~/ path, or one concrete basename",
        )


def _validate_rename_search_roots(params: Mapping[str, Any]) -> None:
    if "search_roots" not in params:
        return
    roots = _string_list(params, "search_roots")
    if not roots or len(roots) > 8 or len(set(roots)) != len(roots):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.search_roots must contain 1 to 8 unique paths",
        )
    if any(root != "~" and not root.startswith(("/", "~/")) for root in roots):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.search_roots paths must be absolute, ~, or begin with ~/",
        )


def _optional_string(data: Mapping[str, Any], field: str) -> None:
    if field in data:
        _string(data, field)


def _bool(data: Mapping[str, Any], field: str) -> None:
    if field in data and not isinstance(data[field], bool):
        raise AdapterError("INVALID_REQUEST", f"params.{field} must be a boolean")


def _number(data: Mapping[str, Any], field: str) -> float:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError("INVALID_REQUEST", f"params.{field} must be a number")
    return float(value)


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


def _string_list(
    data: Mapping[str, Any], field: str, *, allow_empty: bool = False
) -> list[str]:
    value = data.get(field)
    if not isinstance(value, list) or (not value and not allow_empty):
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be a non-empty string array"
        )
    if any(not isinstance(item, str) or not item for item in value):
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must contain only non-empty strings"
        )
    return value


def _verification(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError("INVALID_REQUEST", "verify must be an array")
    checks: list[dict[str, Any]] = []
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
    if action == "filesystem.find":
        patterns = _string_list(params, "name_patterns")
        if len(patterns) > 16 or len(set(patterns)) != len(patterns):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.name_patterns must contain at most 16 unique globs",
            )
        if any(
            Path(pattern).name != pattern
            or any(
                character in pattern for character in ("/", "\\", "\n", "\r", "\x00")
            )
            for pattern in patterns
        ):
            raise AdapterError(
                "INVALID_REQUEST", "params.name_patterns must contain basename globs"
            )
        if "roots" in params:
            roots = _string_list(params, "roots")
            if len(roots) > 8 or len(set(roots)) != len(roots):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.roots must contain at most 8 unique paths",
                )
            if any(root != "~" and not root.startswith(("/", "~/")) for root in roots):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.roots paths must be absolute, ~, or begin with ~/",
                )
        if params.get("kind", "file") not in {"file", "directory", "any"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.kind must be file, directory, or any"
            )
        _bool(params, "recursive")
        _bool(params, "include_hidden")
        if "max_depth" in params:
            _integer(params, "max_depth", 1, 8)
        if "max_results" in params:
            _integer(params, "max_results", 1, 200)
    elif action == "filesystem.create_directory":
        allowed = {"path", "parents"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "filesystem.create_directory received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        path = _string(params, "path")
        if not path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST", "params.path must be absolute or begin with ~/"
            )
        _bool(params, "parents")
    elif action == "filesystem.copy":
        allowed = {"source", "destination", "replace", "create_parents"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "filesystem.copy received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        for field in ("source", "destination"):
            path = _string(params, field)
            if not path.startswith(("/", "~/")):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be absolute or begin with ~/",
                )
        _bool(params, "replace")
        _bool(params, "create_parents")
    elif action == "filesystem.copy_to_directories":
        allowed = {"source", "destinations"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "filesystem.copy_to_directories received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        source = _string(params, "source")
        destinations = _string_list(params, "destinations")
        if len(destinations) > 64 or len(set(destinations)) != len(destinations):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.destinations must contain at most 64 unique paths",
            )
        if source in {"/", "~/"}:
            raise AdapterError(
                "INVALID_REQUEST", "params.source must identify a regular file"
            )
    elif action == "filesystem.rename":
        allowed = {"source", "destination", "replace", "search_roots", "source_query", "new_name"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "filesystem.rename received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        has_explicit_pair = "source" in params or "destination" in params
        has_legacy_pair = "source_query" in params or "new_name" in params
        if has_explicit_pair and has_legacy_pair:
            raise AdapterError(
                "INVALID_REQUEST",
                "filesystem.rename accepts either source/destination or source_query/new_name, not both",
            )
        if has_explicit_pair:
            if "source" not in params or "destination" not in params:
                raise AdapterError("INVALID_REQUEST", "filesystem.rename requires both source and destination")
            _validate_rename_operand(_string(params, "source"), "source")
            _validate_rename_operand(_string(params, "destination"), "destination")
        elif has_legacy_pair:
            if "source_query" not in params or "new_name" not in params:
                raise AdapterError("INVALID_REQUEST", "filesystem.rename requires both source_query and new_name")
            _validate_rename_operand(_string(params, "source_query"), "source_query")
            _validate_rename_operand(_string(params, "new_name"), "new_name")
        else:
            raise AdapterError(
                "INVALID_REQUEST",
                "filesystem.rename requires source/destination or source_query/new_name",
            )
        _validate_rename_search_roots(params)
        _bool(params, "replace")
    elif action == "filesystem.set_permissions":
        allowed = {"path", "mode"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "filesystem.set_permissions received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        path = _string(params, "path")
        if re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, path) is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.path must be an absolute or ~/ path to one concrete file",
            )
        if is_protected_local_root(Path(path).expanduser()):
            raise AdapterError(
                "INVALID_REQUEST", "params.path must not resolve to a protected root"
            )
        mode = _string(params, "mode")
        if re.fullmatch(r"[0-7]{3,4}", mode) is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.mode must be a three- or four-digit octal string",
            )
    elif action == "clipboard.set":
        unexpected = sorted(set(params) - {"text"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "clipboard.set received unsupported parameters",
                {"unexpected": unexpected, "allowed": ["text"]},
            )
        text = params.get("text")
        if not isinstance(text, str):
            raise AdapterError(
                "INVALID_REQUEST", "params.text must be a string, including empty"
            )
        if len(text) > 1_000_000:
            raise AdapterError(
                "INVALID_REQUEST", "params.text must contain at most 1000000 characters"
            )
    elif action == "clipboard.get":
        unexpected = sorted(set(params) - {"max_chars"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "clipboard.get received unsupported parameters",
                {"unexpected": unexpected, "allowed": ["max_chars"]},
            )
        if "max_chars" in params:
            _integer(params, "max_chars", 1, 1_000_000)
    elif action == "text.append_each_line":
        _string(params, "output_path")
        _string(params, "suffix")
        if "lines" in params:
            _string_list(params, "lines", allow_empty=True)
        elif "input_path" in params:
            _string(params, "input_path")
        else:
            raise AdapterError("INVALID_REQUEST", "params requires lines or input_path")
    elif action == "trash.list":
        unexpected = sorted(set(params) - {"offset", "max_results"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "trash.list received unsupported parameters",
                {"unexpected": unexpected, "allowed": ["max_results", "offset"]},
            )
        if "offset" in params:
            _integer(params, "offset", 0, 100_000)
        if "max_results" in params:
            _integer(params, "max_results", 1, 200)
    elif action == "trash.restore":
        unexpected = sorted(set(params) - {"trash_uri", "original_path"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "trash.restore received unsupported parameters",
                {
                    "unexpected": unexpected,
                    "allowed": ["original_path", "trash_uri"],
                },
            )
        trash_uri = _string(params, "trash_uri")
        if re.fullmatch(r"trash:///.+", trash_uri) is None:
            raise AdapterError(
                "INVALID_REQUEST", "params.trash_uri must be an exact trash:/// URI"
            )
        original_path = _string(params, "original_path")
        if not original_path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.original_path must be absolute or begin with ~/",
            )
    elif action == "notifications.configure":
        if not isinstance(params.get("do_not_disturb"), bool):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.do_not_disturb must be a boolean",
            )
    elif action == "terminal.default_profile.inspect":
        if set(params) - {"key"}:
            raise AdapterError("INVALID_REQUEST", "only the optional key parameter is accepted")
        if "key" in params:
            _string(params, "key")
    elif action in {"desktop.set_setting", "terminal.default_profile.set_setting"}:
        if action == "desktop.set_setting":
            _string(params, "schema")
        elif set(params) - {"key", "value"}:
            raise AdapterError("INVALID_REQUEST", "only key and value parameters are accepted")
        _string(params, "key")
        if "value" not in params or not isinstance(
            params["value"], (str, bool, int, float)
        ):
            raise AdapterError("INVALID_REQUEST", "params.value must be a scalar")
    elif action == "desktop.open_path":
        path = _string(params, "path")
        if not path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.path must be absolute or begin with ~/",
            )
        if "wait_seconds" in params:
            wait_seconds = _number(params, "wait_seconds")
            if not 0 <= wait_seconds <= 10:
                raise AdapterError(
                    "INVALID_REQUEST", "params.wait_seconds must be from 0 to 10"
                )
    elif action == "desktop.set_wallpaper":
        allowed = {"image_path"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.set_wallpaper received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        image_path = _string(params, "image_path")
        if not image_path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.image_path must be absolute or begin with ~/",
            )
        if Path(image_path).suffix.casefold() not in {
            ".bmp",
            ".gif",
            ".jpeg",
            ".jpg",
            ".png",
            ".tif",
            ".tiff",
            ".webp",
        }:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.image_path must identify a supported raster image",
            )
    elif action == "desktop.applications.inspect":
        allowed = {
            "query",
            "mime_type_prefixes",
            "max_results",
            "mime_offset",
            "max_mime_types_per_application",
        }
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.applications.inspect received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        _optional_string(params, "query")
        prefixes = _string_list(params, "mime_type_prefixes")
        if any(
            re.fullmatch(r"^[a-z0-9][a-z0-9.+-]*$", value.casefold()) is None
            for value in prefixes
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.mime_type_prefixes contains an invalid MIME category",
            )
        if "max_results" in params:
            _integer(params, "max_results", 1, 100)
        if "mime_offset" in params:
            _integer(params, "mime_offset", 0, 100000)
        if "max_mime_types_per_application" in params:
            _integer(params, "max_mime_types_per_application", 1, 20)
    elif action == "desktop.mime_associations.set":
        allowed = {"desktop_id", "mime_types", "mime_type_prefixes"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.mime_associations.set received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        desktop_id = _string(params, "desktop_id")
        if "/" in desktop_id or not desktop_id.casefold().endswith(".desktop"):
            raise AdapterError(
                "INVALID_REQUEST", "params.desktop_id must be an exact Desktop Entry ID"
            )
        if ("mime_types" in params) == ("mime_type_prefixes" in params):
            raise AdapterError(
                "INVALID_REQUEST", "select exactly one of mime_types or mime_type_prefixes"
            )
        field = "mime_types" if "mime_types" in params else "mime_type_prefixes"
        values = _string_list(params, field)
        pattern = (
            r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$"
            if field == "mime_types"
            else r"^[a-z0-9][a-z0-9.+-]*$"
        )
        if (
            len(values) > 20
            or len(values) != len(set(values))
            or any(
                re.fullmatch(pattern, value.casefold() if field == "mime_types" else value)
                is None
                for value in values
            )
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.{field} must contain unique valid MIME selectors (at most 20)",
            )
    elif action == "desktop.set_accessibility_scale":
        if "magnifier_factor" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.magnifier_factor is unsupported: call desktop.set_setting separately for org.gnome.desktop.a11y.applications/screen-magnifier-enabled and org.gnome.desktop.a11y.magnifier/mag-factor",
            )
        text_factor = _number(params, "text_factor")
        if not 0.5 <= text_factor <= 3.0:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.text_factor must be between 0.5 and 3.0",
            )
    elif action == "desktop.set_dim_inactive":
        selected = [field for field in ("idle_delay", "idle_dim") if field in params]
        if len(selected) != 1:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.set_dim_inactive requires exactly one of idle_delay or idle_dim; do not combine a delay change with a dimming toggle in one call",
            )
        if "idle_delay" in params:
            _integer(params, "idle_delay", 0, 2**32 - 1)
        else:
            if not isinstance(params.get("idle_dim"), bool):
                raise AdapterError(
                    "INVALID_REQUEST", "params.idle_dim must be a boolean"
                )
    elif action == "desktop.favorites.list":
        unexpected = sorted(set(params) - {"offset", "max_results"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.favorites.list received unsupported parameters",
                {"unexpected": unexpected, "allowed": ["max_results", "offset"]},
            )
        if "offset" in params:
            _integer(params, "offset", 0, 10_000)
        if "max_results" in params:
            _integer(params, "max_results", 1, 200)
    elif action == "desktop.remove_favorite":
        unexpected = sorted(set(params) - {"desktop_id"})
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "desktop.remove_favorite received unsupported parameters",
                {"unexpected": unexpected, "allowed": ["desktop_id"]},
            )
        desktop_id = _string(params, "desktop_id")
        if re.fullmatch(r"[^/]+\.desktop", desktop_id) is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.desktop_id must be an exact Desktop Entry ID ending in .desktop",
            )
    elif action == "audio.set_volume":
        allowed = {"percent", "sink"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "audio.set_volume received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        percent = _number(params, "percent")
        if not 0 <= percent <= 150:
            raise AdapterError(
                "INVALID_REQUEST", "params.percent must be from 0 to 150"
            )
        _optional_string(params, "sink")
    elif action == "system.set_timezone":
        _string(params, "timezone")
    elif action == "terminal.show_output":
        allowed = {
            "argv",
            "cwd_source",
            "cwd_path",
            "expected_returncodes",
            "provenance",
        }
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "terminal.show_output received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        _string_list(params, "argv")
        cwd_source = _string(params, "cwd_source")
        if cwd_source not in {"active_context", "active_terminal", "home", "explicit"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_source must be active_context, active_terminal, home, or explicit",
            )
        if cwd_source == "explicit":
            cwd_path = _string(params, "cwd_path")
            if not Path(cwd_path).is_absolute():
                raise AdapterError(
                    "INVALID_REQUEST", "params.cwd_path must be an absolute path"
                )
        elif "cwd_path" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_path is valid only with cwd_source=explicit",
            )
        if "expected_returncodes" in params:
            returncodes = params["expected_returncodes"]
            if (
                not isinstance(returncodes, list)
                or not returncodes
                or len(set(returncodes)) != len(returncodes)
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or not -255 <= value <= 255
                    for value in returncodes
                )
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.expected_returncodes must be a non-empty unique integer array",
                )
        provenance = _string(params, "provenance")
        if provenance not in {"none", "shell_history"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.provenance must be none or shell_history",
            )
    elif action == "terminal.launch":
        _string_list(params, "argv")
        _optional_string(params, "cwd")
        _bool(params, "record_shell_history")
    elif action == "window.capture":
        allowed = {"title_contains", "output_path", "overwrite"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "window.capture received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        title = _string(params, "title_contains")
        if len(title) > 256:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.title_contains must contain at most 256 characters",
            )
        output_path = _string(params, "output_path")
        if not output_path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.output_path must be absolute or begin with ~/",
            )
        if Path(output_path).suffix.casefold() != ".png":
            raise AdapterError(
                "INVALID_REQUEST", "params.output_path must end with .png"
            )
        _bool(params, "overwrite")
    elif action == "document.convert":
        allowed = {"source", "destination", "overwrite"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "document.convert received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        for field in ("source", "destination"):
            path = _string(params, field)
            if re.fullmatch(NON_ROOT_LOCAL_PATH_PATTERN, path) is None:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be an absolute or ~/ path to one concrete file",
                )
            if is_protected_local_root(Path(path).expanduser()):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must not resolve to a protected root",
                )
        output_format = Path(_string(params, "destination")).suffix.lstrip(".").casefold()
        if output_format not in {
            "pdf",
            "docx",
            "odt",
            "xlsx",
            "ods",
            "pptx",
            "odp",
            "csv",
            "txt",
            "html",
        }:
            raise AdapterError(
                "INVALID_REQUEST", "params.destination has an unsupported extension"
            )
        _bool(params, "overwrite")
    elif action == "archive.create_zip":
        allowed = {"archive_path", "input_paths", "base_directory", "overwrite"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "archive.create_zip received unsupported parameters; use archive.extract_zip for destination_directory",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        archive_path = _string(params, "archive_path")
        if not archive_path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.archive_path must be absolute or begin with ~/",
            )
        if Path(archive_path).suffix.casefold() != ".zip":
            raise AdapterError(
                "INVALID_REQUEST", "params.archive_path must end with .zip"
            )
        input_paths = _string_list(params, "input_paths")
        if len(input_paths) > 256 or len(set(input_paths)) != len(input_paths):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.input_paths must contain at most 256 unique paths",
            )
        if any(not path.startswith(("/", "~/")) for path in input_paths):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.input_paths must contain absolute or ~/ paths",
            )
        if "base_directory" in params:
            base_directory = _string(params, "base_directory")
            if not base_directory.startswith(("/", "~/")):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.base_directory must be absolute or begin with ~/",
                )
        _bool(params, "overwrite")
    elif action == "archive.extract_zip":
        allowed = {"archive_path", "destination_directory", "overwrite"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "archive.extract_zip received unsupported parameters; use archive.create_zip for input_paths",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        archive_path = _string(params, "archive_path")
        if not archive_path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.archive_path must be absolute or begin with ~/",
            )
        if Path(archive_path).suffix.casefold() != ".zip":
            raise AdapterError(
                "INVALID_REQUEST", "params.archive_path must end with .zip"
            )
        destination = _string(params, "destination_directory")
        if not destination.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.destination_directory must be absolute or begin with ~/",
            )
        _bool(params, "overwrite")
    elif action == "archive.compress_file":
        allowed = {"source", "destination", "remove_source", "overwrite"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "archive.compress_file received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        for field in ("source", "destination"):
            path = _string(params, field)
            if not path.startswith(("/", "~/")):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be absolute or begin with ~/",
                )
        if not _string(params, "destination").casefold().endswith(".gz"):
            raise AdapterError(
                "INVALID_REQUEST", "params.destination must end with .gz"
            )
        _bool(params, "remove_source")
        _bool(params, "overwrite")
    elif action in {"pdf.form.inspect", "pdf.form.fill", "pdf.tables.inspect"}:
        from .tool_manifest import STRICT_ACTION_PARAM_SCHEMAS

        contract = STRICT_ACTION_PARAM_SCHEMAS[action]
        unexpected = sorted(set(params) - set(contract["properties"]))
        if unexpected:
            raise AdapterError("INVALID_REQUEST", f"{action} received unsupported parameters", {"unexpected": unexpected})
        paths = ("input_path", "output_path") if action == "pdf.form.fill" else ("input_path",)
        for field in paths:
            path = _string(params, field)
            if re.fullmatch(contract["properties"][field]["pattern"], path) is None:
                raise AdapterError("INVALID_REQUEST", f"params.{field} must be an absolute, ~/ or local file URI PDF path")
        if action in {"pdf.form.inspect", "pdf.tables.inspect"}:
            integer_fields = (
                ("page", "table_index", "row_offset", "max_rows")
                if action == "pdf.tables.inspect"
                else ("field_offset", "max_fields")
            )
            for field in integer_fields:
                if field in params:
                    spec = contract["properties"][field]
                    _integer(params, field, spec["minimum"], spec["maximum"])
        else:
            _bool(params, "overwrite")
            fields = params.get("fields")
            spec = contract["properties"]["fields"]
            if not isinstance(fields, list) or not spec["minItems"] <= len(fields) <= spec["maxItems"]:
                raise AdapterError("INVALID_REQUEST", "params.fields must contain 1 to 128 explicit field/value pairs")
            for index, item in enumerate(fields):
                prefix = f"params.fields[{index}]"
                if not isinstance(item, Mapping) or set(item) != {"field_name", "value"}:
                    raise AdapterError("INVALID_REQUEST", f"{prefix} must contain only field_name and value")
                _string(item, "field_name", prefix)
                if not isinstance(item["value"], str):
                    raise AdapterError("INVALID_REQUEST", f"{prefix}.value must be a string; an empty string clears the field")
    elif action == "pdf.outline.inspect":
        allowed = {"input_path", "outline_level", "offset", "max_sections"}
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "pdf.outline.inspect received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        input_path = _string(params, "input_path")
        if not _is_explicit_local_path(input_path):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.input_path must be absolute, begin with ~/, or use a local file URI",
            )
        if Path(input_path).suffix.casefold() != ".pdf":
            raise AdapterError(
                "INVALID_REQUEST", "params.input_path must end with .pdf"
            )
        _integer(params, "outline_level", 1, 32)
        if "offset" in params:
            _integer(params, "offset", 0, 100_000)
        if "max_sections" in params:
            _integer(params, "max_sections", 1, 50)
    elif action == "pdf.pages.extract":
        allowed = {
            "input_path",
            "output_path",
            "start_page",
            "end_page",
            "overwrite",
            "output_backend",
        }
        unexpected = sorted(set(params) - allowed)
        if unexpected:
            raise AdapterError(
                "INVALID_REQUEST",
                "pdf.pages.extract received unsupported parameters",
                {"unexpected": unexpected, "allowed": sorted(allowed)},
            )
        input_path = _string(params, "input_path")
        output_path = _string(params, "output_path")
        for name, value in (("input_path", input_path), ("output_path", output_path)):
            if not _is_explicit_local_path(value):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{name} must be absolute, begin with ~/, or use a local file URI",
                )
            if Path(value).suffix.casefold() != ".pdf":
                raise AdapterError(
                    "INVALID_REQUEST", f"params.{name} must end with .pdf"
                )
        start_page = _integer(params, "start_page", 1, 1_000_000)
        end_page = _integer(params, "end_page", 1, 1_000_000)
        if start_page > end_page:
            raise AdapterError(
                "INVALID_REQUEST", "params.start_page must not exceed params.end_page"
            )
        output_backend = _string(params, "output_backend")
        if output_backend not in {"preserve_pages", "cairo"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.output_backend must be preserve_pages or cairo",
            )
        if not isinstance(params.get("overwrite"), bool):
            raise AdapterError(
                "INVALID_REQUEST", "params.overwrite must be an explicit boolean"
            )
    elif action == "pdf.extract_text_batch":
        pattern = _string(params, "input_pattern")
        if Path(pattern).name != pattern or any(
            character in pattern for character in ("/", "\\", "\n", "\r", "\x00")
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.input_pattern must be a basename or basename glob",
            )
        cwd_source = _string(params, "cwd_source")
        if cwd_source not in {"active_terminal", "home", "explicit"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_source must be active_terminal, home, or explicit",
            )
        if cwd_source == "explicit":
            if not _string(params, "cwd_path").startswith("/"):
                raise AdapterError(
                    "INVALID_REQUEST", "params.cwd_path must be an absolute path"
                )
        elif "cwd_path" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_path is valid only with cwd_source=explicit",
            )
        if "start_page" in params:
            _integer(params, "start_page", 1, 100_000)
        if "page_count" in params:
            _integer(params, "page_count", 1, 100_000)
        if "max_chars_per_file" in params:
            _integer(params, "max_chars_per_file", 1, 20_000)
        if "start_char" in params:
            _integer(params, "start_char", 0, 100_000_000)
        _bool(params, "include_hidden")
        _bool(params, "preserve_layout")
    elif action == "image.extract_text_batch":
        pattern = _string(params, "input_pattern")
        if Path(pattern).name != pattern or any(
            character in pattern for character in ("/", "\\", "\n", "\r", "\x00")
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.input_pattern must be a basename or basename glob",
            )
        cwd_source = _string(params, "cwd_source")
        if cwd_source not in {"active_terminal", "home", "explicit"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_source must be active_terminal, home, or explicit",
            )
        if cwd_source == "explicit":
            if not _string(params, "cwd_path").startswith("/"):
                raise AdapterError(
                    "INVALID_REQUEST", "params.cwd_path must be an absolute path"
                )
        elif "cwd_path" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_path is valid only with cwd_source=explicit",
            )
        if "max_chars_per_file" in params:
            _integer(params, "max_chars_per_file", 1, 20_000)
        if "start_char" in params:
            _integer(params, "start_char", 0, 100_000_000)
        if "max_pages_per_pdf" in params:
            _integer(params, "max_pages_per_pdf", 1, 20)
        if "max_files" in params:
            _integer(params, "max_files", 1, 200)
        _bool(params, "include_hidden")
    elif action == "command.run":
        _string_list(params, "argv")
        cwd_source = _string(params, "cwd_source")
        if cwd_source not in {"active_terminal", "home", "explicit"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_source must be active_terminal, home, or explicit",
            )
        if cwd_source == "explicit":
            cwd_path = _string(params, "cwd_path")
            if not Path(cwd_path).is_absolute():
                raise AdapterError(
                    "INVALID_REQUEST", "params.cwd_path must be an absolute path"
                )
        elif "cwd_path" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.cwd_path is valid only with cwd_source=explicit",
            )
        provenance = _string(params, "provenance")
        if provenance not in {"none", "shell_history"}:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.provenance must be none or shell_history",
            )
        if "input" in params and not isinstance(params["input"], str):
            raise AdapterError("INVALID_REQUEST", "params.input must be a string")
        _optional_string(params, "stdout_path")
        _bool(params, "append_stdout")
        # Accepted only for older callers; current model schemas use provenance.
        _bool(params, "record_shell_history")
        _bool(params, "terminal")
        if params.get("append_stdout") and "stdout_path" not in params:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.append_stdout requires params.stdout_path",
            )
        if "expected_returncodes" in params:
            returncodes = params["expected_returncodes"]
            if (
                not isinstance(returncodes, list)
                or not returncodes
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or not -255 <= value <= 255
                    for value in returncodes
                )
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    "params.expected_returncodes must be a non-empty integer array",
                )
        for field in (
            "stdout_contains",
            "stdout_excludes",
            "stderr_contains",
            "stderr_excludes",
        ):
            if field in params:
                _string_list(params, field, allow_empty=True)
        if params.get("terminal"):
            unsupported = [
                field
                for field in (
                    "input",
                    "stdout_path",
                    "append_stdout",
                    "stdout_contains",
                    "stdout_excludes",
                    "stderr_contains",
                    "stderr_excludes",
                )
                if field in params
            ]
            if unsupported:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "terminal command mode cannot capture input or stdout/stderr assertions",
                    {"unsupported_fields": unsupported},
                )
        if "stdout_path" in params:
            unsupported = [
                field
                for field in ("stdout_contains", "stdout_excludes")
                if field in params
            ]
            if unsupported:
                raise AdapterError(
                    "INVALID_REQUEST",
                    "redirected stdout cannot also use stdout assertions",
                    {"unsupported_fields": unsupported},
                )
    elif action == "user.ensure_account":
        username = _string(params, "username")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
            raise AdapterError("INVALID_REQUEST", "params.username is invalid")
        _string(params, "password")
        _string(params, "home")
        _optional_string(params, "shell")
        if "mode" in params:
            _integer(params, "mode", 0, 0o777)
    elif action == "package.install_snap":
        package = _string(params, "package")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", package):
            raise AdapterError("INVALID_REQUEST", "params.package is invalid")
        _optional_string(params, "channel")


def parse_action_request(raw: Any) -> ActionRequest:
    data = _mapping(raw, "request")
    request_id = data.get("request_id") or str(uuid4())
    if not isinstance(request_id, str) or not request_id.strip():
        raise AdapterError("INVALID_REQUEST", "request_id must be a non-empty string")
    adapter = data.get("adapter", ADAPTER_NAME)
    if adapter != ADAPTER_NAME:
        raise AdapterError("INVALID_REQUEST", f"adapter must be {ADAPTER_NAME}")
    action = data.get("action")
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_ACTION", "action is not supported", {"action": action}, 404
        )
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
    target = _mapping(data.get("target"), "target")
    if action == "command.run" and target:
        raise AdapterError(
            "INVALID_REQUEST",
            "command.run does not accept target fields; put command options "
            "such as stdout_path inside params alongside argv. No command was executed.",
            {"unsupported_target_fields": sorted(target)},
        )
    validate_action_params(action, params)
    return ActionRequest(
        request_id=request_id,
        adapter=adapter,
        action=action,
        timeout_ms=timeout_ms,
        target=target,
        params=params,
        verify=_verification(data.get("verify")),
    )
