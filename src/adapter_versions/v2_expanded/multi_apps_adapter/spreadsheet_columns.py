from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

from .errors import AdapterError


SUPPORTED_INPUT_SUFFIXES = frozenset({".csv", ".ods", ".xlsx"})
SEPARATOR_STYLES = {
    "no_separator": "",
    "single_space": " ",
    "single_tab": "\t",
    "single_hyphen": "-",
    "single_slash": "/",
    "slash_surrounded_by_spaces": " / ",
    "single_pipe": "|",
    "pipe_surrounded_by_spaces": " | ",
    "single_comma": ",",
    "comma_followed_by_space": ", ",
    "single_semicolon": ";",
    "semicolon_followed_by_space": "; ",
}

SPREADSHEET_CONCATENATE_SCHEMA: dict[str, Any] = {
    "description": (
        "In a visible terminal, read the single used column from each selected CSV, "
        "ODS, or XLSX file, concatenate corresponding displayed row strings in input "
        "order, and atomically write one CSV column. Every path, the separator, and "
        "overwrite choice are supplied by the model; this action does not open the "
        "result in a desktop application."
    ),
    "properties": {
        "input_paths": {
            "type": "array",
            "minItems": 2,
            "maxItems": 16,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "pattern": (
                    "^(?:/|~/|file:///).+\\.(?:[cC][sS][vV]|[oO][dD][sS]|"
                    "[xX][lL][sS][xX])$"
                ),
            },
            "description": (
                "Two to sixteen existing local spreadsheets in exact left-to-right "
                "concatenation order. Each file must contain exactly one used column "
                "and the files must contain the same number of used rows."
            ),
        },
        "output_path": {
            "type": "string",
            "minLength": 1,
            "pattern": "^(?:/|~/|file:///).+\\.[cC][sS][vV]$",
            "description": (
                "Exact local CSV destination selected by the model. The output has one "
                "field per row even when a concatenated value contains a comma."
            ),
        },
        "separator_style": {
            "type": "string",
            "enum": [*SEPARATOR_STYLES],
            "description": (
                "Exact named text inserted between row values. Choose no_separator for "
                "direct concatenation, single_space for exactly one literal space, or "
                "the fully named punctuation form. A value whose name says surrounded "
                "by spaces includes one space on both sides."
            ),
        },
        "overwrite": {
            "type": "boolean",
            "description": (
                "Whether an existing output file may be atomically replaced; defaults "
                "to false."
            ),
        },
    },
    "required": ["input_paths", "output_path", "separator_style"],
}

SPREADSHEET_TERMINAL_OPEN_SCHEMA: dict[str, Any] = {
    "description": (
        "Open one existing CSV, ODS, or XLSX file in an isolated LibreOffice Calc "
        "process launched from a visible terminal. The model supplies the exact file "
        "path; the Adapter adds only the reusable isolation flags needed to prevent an "
        "unrelated running LibreOffice process from swallowing the terminal launch."
    ),
    "properties": {
        "path": {
            "type": "string",
            "minLength": 1,
            "pattern": (
                "^(?:/|~/|file:///).+\\.(?:[cC][sS][vV]|[oO][dD][sS]|[xX][lL][sS][xX])$"
            ),
            "description": (
                "Exact existing local spreadsheet selected by the model and opened in "
                "LibreOffice Calc from the terminal."
            ),
        }
    },
    "required": ["path"],
}


class AdapterCaller(Protocol):
    def call_adapter(
        self, params: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]: ...

    @staticmethod
    def _downstream_result(call: dict[str, Any]) -> dict[str, Any]: ...


def _local_path(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path))
    elif parsed.scheme:
        raise AdapterError(
            "INVALID_REQUEST",
            "spreadsheet paths must be local paths or file URLs",
            {"path": value},
        )
    else:
        path = Path(value).expanduser()
    if not path.is_absolute():
        raise AdapterError(
            "INVALID_REQUEST",
            "spreadsheet paths must be absolute, begin with ~/, or use a file URL",
            {"path": value},
        )
    return path


def validate_concatenate_params(params: dict[str, Any]) -> None:
    allowed = {
        "input_paths",
        "output_path",
        "separator_style",
        "overwrite",
    }
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "spreadsheet.concatenate_single_columns received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    input_paths = params.get("input_paths")
    if (
        not isinstance(input_paths, list)
        or not 2 <= len(input_paths) <= 16
        or any(not isinstance(value, str) or not value.strip() for value in input_paths)
        or len(set(input_paths)) != len(input_paths)
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.input_paths must contain 2 to 16 unique non-empty local paths",
        )
    normalized_inputs = [_local_path(value) for value in input_paths]
    invalid_inputs = [
        str(path)
        for path in normalized_inputs
        if path.suffix.casefold() not in SUPPORTED_INPUT_SUFFIXES
    ]
    if invalid_inputs:
        raise AdapterError(
            "INVALID_REQUEST",
            "input spreadsheets must end in .csv, .ods, or .xlsx",
            {"invalid_paths": invalid_inputs},
        )
    output_value = params.get("output_path")
    if not isinstance(output_value, str) or not output_value.strip():
        raise AdapterError("INVALID_REQUEST", "params.output_path must be non-empty")
    output_path = _local_path(output_value)
    if output_path.suffix.casefold() != ".csv":
        raise AdapterError(
            "INVALID_REQUEST",
            "params.output_path must end in .csv",
        )
    if output_path in normalized_inputs:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.output_path must differ from every input path",
        )
    separator_style = params.get("separator_style")
    if separator_style not in SEPARATOR_STYLES:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.separator_style is unsupported",
        )
    if "overwrite" in params and not isinstance(params["overwrite"], bool):
        raise AdapterError("INVALID_REQUEST", "params.overwrite must be a boolean")


def validate_terminal_open_params(params: dict[str, Any]) -> None:
    if set(params) != {"path"}:
        raise AdapterError(
            "INVALID_REQUEST",
            "spreadsheet.open_in_terminal requires exactly one parameter: path",
        )
    value = params.get("path")
    if not isinstance(value, str) or not value.strip():
        raise AdapterError("INVALID_REQUEST", "params.path must be non-empty")
    path = _local_path(value)
    if path.suffix.casefold() not in SUPPORTED_INPUT_SUFFIXES:
        raise AdapterError(
            "INVALID_REQUEST",
            "params.path must end in .csv, .ods, or .xlsx",
        )


def _result_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("operation") == (
            "spreadsheet.concatenate_single_columns"
        ):
            return parsed
    raise AdapterError(
        "DOWNSTREAM_FAILED",
        "the command-line spreadsheet helper returned no structured summary",
        {"output_tail": output[-2000:]},
        502,
    )


def _separator(params: dict[str, Any]) -> str:
    return SEPARATOR_STYLES[params["separator_style"]]


def _verify_single_column_csv(path: Path) -> tuple[int, str, int]:
    if not path.is_file():
        raise AdapterError(
            "OUTPUT_NOT_FOUND",
            "the command-line spreadsheet helper did not create the requested output",
            {"path": str(path)},
            502,
        )
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    invalid_rows = [index + 1 for index, row in enumerate(rows) if len(row) != 1]
    if invalid_rows:
        raise AdapterError(
            "OUTPUT_VERIFICATION_FAILED",
            "the generated CSV is not a single-column file",
            {"path": str(path), "invalid_rows": invalid_rows[:20]},
            502,
        )
    return len(rows), digest.hexdigest(), size


def concatenate_single_columns(
    caller: AdapterCaller,
    params: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    validate_concatenate_params(params)
    input_paths = [str(_local_path(value)) for value in params["input_paths"]]
    output_path = _local_path(params["output_path"])
    separator = _separator(params)
    helper = Path(__file__).with_name("spreadsheet_columns_cli.py")
    argv = [
        "/usr/bin/python3",
        str(helper),
        "--output",
        str(output_path),
        "--separator-json",
        json.dumps(separator, ensure_ascii=True),
    ]
    if params.get("overwrite", False):
        argv.append("--overwrite")
    for path in input_paths:
        argv.extend(["--input", path])
    call = caller.call_adapter(
        {
            "adapter": "os",
            "action": "terminal.show_output",
            "payload": {
                "params": {
                    "argv": argv,
                    "cwd_source": "home",
                    "expected_returncodes": [0],
                    "provenance": "shell_history",
                }
            },
        },
        timeout_seconds,
    )
    downstream = caller._downstream_result(call)
    combined_output = downstream.get("combined_output") or downstream.get("stdout")
    if not isinstance(combined_output, str):
        raise AdapterError(
            "DOWNSTREAM_FAILED",
            "the visible terminal action returned no command output",
            downstream,
            502,
        )
    summary = _result_json(combined_output)
    row_count, digest, size = _verify_single_column_csv(output_path)
    if summary.get("row_count") != row_count or summary.get("sha256") != digest:
        raise AdapterError(
            "OUTPUT_VERIFICATION_FAILED",
            "the command summary does not match the generated CSV",
            {
                "path": str(output_path),
                "summary": summary,
                "observed_row_count": row_count,
                "observed_sha256": digest,
            },
            502,
        )
    return {
        "input_paths": input_paths,
        "output_path": str(output_path),
        "separator_style": params["separator_style"],
        "separator": separator,
        "row_count": row_count,
        "source_count": len(input_paths),
        "size": size,
        "sha256": digest,
        "terminal": downstream.get("terminal"),
        "provenance": downstream.get("provenance"),
        "verification": {
            "passed": True,
            "single_column": True,
            "row_count": row_count,
            "sha256": digest,
        },
    }


def open_in_terminal(
    caller: AdapterCaller,
    params: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    validate_terminal_open_params(params)
    path = _local_path(params["path"])
    if not path.is_file():
        raise AdapterError(
            "FILE_NOT_FOUND",
            "the selected spreadsheet does not exist",
            {"path": str(path)},
            404,
        )
    profile = Path("/tmp") / (
        "osworld-terminal-calc-" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    )
    argv = [
        "libreoffice",
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--norestore",
        "--calc",
        str(path),
    ]
    call = caller.call_adapter(
        {
            "adapter": "os",
            "action": "terminal.launch",
            "payload": {
                "params": {
                    "argv": argv,
                    "cwd": str(path.parent),
                    "record_shell_history": True,
                }
            },
        },
        timeout_seconds,
    )
    downstream = caller._downstream_result(call)
    terminal = downstream.get("terminal")
    if not isinstance(terminal, dict) or terminal.get("launched") is not True:
        raise AdapterError(
            "DOWNSTREAM_FAILED",
            "LibreOffice Calc was not observably launched from a terminal",
            downstream,
            502,
        )
    return {
        "path": str(path),
        "argv": argv,
        "terminal": terminal,
        "provenance": downstream.get("provenance"),
        "verification": {"passed": True, "terminal_launched": True},
    }


__all__ = [
    "SPREADSHEET_CONCATENATE_SCHEMA",
    "SPREADSHEET_TERMINAL_OPEN_SCHEMA",
    "concatenate_single_columns",
    "open_in_terminal",
    "validate_concatenate_params",
    "validate_terminal_open_params",
]
