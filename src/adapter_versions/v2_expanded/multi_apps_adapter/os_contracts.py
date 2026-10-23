from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .errors import AdapterError


def _is_explicit_local_path(value: str) -> bool:
    return value.startswith(("/", "~/", "file:///", "file://localhost/"))


def _string(params: Mapping[str, Any], field: str) -> str:
    value = params.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"params.{field} must be a non-empty string"
        )
    return value


def _validate_archive_path(params: Mapping[str, Any]) -> str:
    archive_path = _string(params, "archive_path")
    if not archive_path.startswith(("/", "~/")):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.archive_path must be absolute or begin with ~/",
        )
    if Path(archive_path).suffix.casefold() != ".zip":
        raise AdapterError("INVALID_REQUEST", "params.archive_path must end with .zip")
    return archive_path


def validate_archive_create_zip_params(params: Mapping[str, Any]) -> None:
    allowed = {"archive_path", "input_paths", "base_directory", "overwrite"}
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "archive.create_zip received unsupported parameters; use archive.extract_zip for destination_directory",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    _validate_archive_path(params)
    input_paths = params.get("input_paths")
    if (
        not isinstance(input_paths, list)
        or not 1 <= len(input_paths) <= 256
        or len(set(item for item in input_paths if isinstance(item, str))) != len(input_paths)
        or any(
            not isinstance(path, str)
            or not path
            or not path.startswith(("/", "~/"))
            for path in input_paths
        )
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.input_paths must contain from 1 to 256 unique absolute or ~/ paths",
        )
    if "base_directory" in params:
        base = _string(params, "base_directory")
        if not base.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.base_directory must be absolute or begin with ~/",
            )
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")


def validate_archive_extract_zip_params(params: Mapping[str, Any]) -> None:
    allowed = {"archive_path", "destination_directory", "overwrite"}
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "archive.extract_zip received unsupported parameters; use archive.create_zip for input_paths",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    _validate_archive_path(params)
    destination = _string(params, "destination_directory")
    if not destination.startswith(("/", "~/")):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.destination_directory must be absolute or begin with ~/",
        )
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")

def validate_pdf_split_by_outline_params(params: Mapping[str, Any]) -> None:
    allowed = {
        "input_path",
        "output_directory",
        "outline_level",
        "filename_style",
        "start_index",
        "include_prefix_pages",
        "overwrite",
        "output_backend",
    }
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "pdf.split_by_outline received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    input_path = _string(params, "input_path")
    if not _is_explicit_local_path(input_path):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.input_path must be absolute, begin with ~/, or use a local file URI",
        )
    if Path(input_path).suffix.casefold() != ".pdf":
        raise AdapterError("INVALID_REQUEST", "params.input_path must end with .pdf")
    if "output_directory" in params:
        output_directory = _string(params, "output_directory")
        if not _is_explicit_local_path(output_directory):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.output_directory must be absolute, begin with ~/, or use a local file URI",
            )
    for field, minimum, maximum in (
        ("outline_level", 1, 32),
        ("start_index", 1, 100_000),
    ):
        if field in params:
            value = params[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"params.{field} must be an integer from {minimum} to {maximum}",
                )
    if params.get("filename_style", "number_and_title") not in {
        "number_and_title",
        "title",
        "number",
    }:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.filename_style must be number_and_title, title, or number",
        )
    if params.get("output_backend", "auto") not in {
        "auto",
        "preserve_pages",
        "cairo",
    }:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.output_backend must be auto, preserve_pages, or cairo",
        )
    for field in ("include_prefix_pages", "overwrite"):
        if field in params and not isinstance(params[field], bool):
            raise AdapterError("INVALID_REQUEST", f"params.{field} must be a boolean")


def validate_terminal_show_output_params(params: Mapping[str, Any]) -> None:
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
    argv = params.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise AdapterError(
            "INVALID_REQUEST", "params.argv must be a non-empty string array"
        )
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
    provenance = _string(params, "provenance")
    if provenance not in {"none", "shell_history"}:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.provenance must be none or shell_history",
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


def validate_window_capture_params(params: Mapping[str, Any]) -> None:
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
        raise AdapterError("INVALID_REQUEST", "params.output_path must end with .png")
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")
