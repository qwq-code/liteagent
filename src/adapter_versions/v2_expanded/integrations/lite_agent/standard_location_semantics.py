"""Generic preservation of explicitly requested standard output directories."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse


_STANDARD_DIRECTORIES = {
    "desktop": "Desktop",
    "documents": "Documents",
    "downloads": "Downloads",
}
_OUTPUT_VERB = re.compile(
    r"(?i)\b(?:convert(?:ed|ing|s)?|creat(?:e|ed|es|ing)|export(?:ed|ing|s)?|"
    r"generat(?:e|ed|es|ing)|plac(?:e|ed|es|ing)|put(?:s|ting)?|"
    r"sav(?:e|ed|es|ing)|stor(?:e|ed|es|ing)|writ(?:e|es|ing|ten))\b"
)
_STANDARD_TARGET = re.compile(
    r"(?i)\b(?:in|into|on|to|under)\s+(?:the\s+)?"
    r"(?P<directory>desktop|documents|downloads)"
    r"(?:\s+(?:directory|folder))?\b"
)

# These public operations create, export, or relocate a final local artifact.
# The map identifies only the model-facing path field; it never supplies a value.
OUTPUT_PATH_FIELDS: dict[str, tuple[str, ...]] = {
    # command.run also supports stdout_path.  Keep it under the same generic
    # standard-directory contract as command.capture_output so a model cannot
    # bypass an explicitly requested Desktop/Documents/Downloads destination by
    # selecting the lower-level command action.
    "command.run": ("stdout_path",),
    "command.capture_output": ("stdout_path",),
    "contacts.export_csv": ("output_path",),
    "document.convert": ("destination",),
    "document.create_from_json_values": ("output_path",),
    "filesystem.move": ("destination",),
    "image.crop": ("output_path",),
    "mail.save_attachment": ("output_path",),
    "media.extract_audio": ("output_path",),
    "media.extract_current_audio": ("output_path",),
    "media.extract_current_frame": ("output_path",),
    "spreadsheet.concatenate_single_columns": ("output_path",),
    "spreadsheet.convert_file": ("output_path",),
    "spreadsheet.create_workbook": ("output_path",),
    "spreadsheet.save": ("output_path",),
    "window.capture": ("output_path",),
    "workbook.save": ("url",),
    "presentation.save": ("url",),
    "document.save": ("url",),
    "image.export": ("output_path",),
}


def requested_standard_output_directory(instruction: str) -> str | None:
    """Return one unambiguous standard directory tied to an output operation."""
    requested: list[str] = []
    # Do not split on the period inside filenames such as report.xlsx.
    for clause in re.split(r"[;!?\n]+|\.(?=\s+[A-Z]|$)", instruction):
        verbs = list(_OUTPUT_VERB.finditer(clause))
        for index, verb in enumerate(verbs):
            end = verbs[index + 1].start() if index + 1 < len(verbs) else len(clause)
            segment = clause[verb.end() : end]
            for match in _STANDARD_TARGET.finditer(segment):
                prefix = segment[: match.start()]
                from_matches = list(re.finditer(r"(?i)\bfrom\b", prefix))
                if from_matches:
                    after_from = prefix[from_matches[-1].end() :]
                    if not re.search(
                        r"(?i)\b(?:as|into|to)\b|\.[a-z0-9]{1,12}\b",
                        after_from,
                    ):
                        continue
                directory = _STANDARD_DIRECTORIES[match.group("directory").casefold()]
                if directory not in requested:
                    requested.append(directory)
    return requested[0] if len(requested) == 1 else None


def path_preserves_standard_directory(path: Any, directory: str) -> bool:
    """Check active-user standard-directory spelling without resolving host paths."""
    if not isinstance(path, str) or not path.strip():
        return False
    raw = path.strip()
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return False
        raw = unquote(parsed.path)
    if raw.startswith("~/"):
        parts = PurePosixPath(raw[2:]).parts
        return bool(parts and parts[0] == directory)
    if not raw.startswith("/"):
        return False
    parts = PurePosixPath(raw).parts
    if len(parts) >= 4 and parts[0] == "/" and parts[1] == "home":
        return parts[3] == directory
    if len(parts) >= 3 and parts[:2] == ("/", "root"):
        return parts[2] == directory
    return False


def output_path_argument(
    action: str, arguments: dict[str, Any]
) -> tuple[str, str] | None:
    for field in OUTPUT_PATH_FIELDS.get(action, ()):
        value = arguments.get(field)
        if isinstance(value, str) and value.strip():
            return field, value
    return None


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject a selected final path that drops a named standard directory."""
    directory = requested_standard_output_directory(
        str(getattr(state, "instruction", ""))
    )
    selected = output_path_argument(action, arguments)
    if directory is None or selected is None:
        return []
    field, path = selected
    if path_preserves_standard_directory(path, directory):
        return []
    return [
        f"the instruction explicitly requires the final output in the active user's "
        f"{directory} directory, but model-selected {field}={path!r} does not preserve "
        f"that directory; choose a {field} under ~/{directory}/ or the corresponding "
        "absolute active-user directory"
    ]


def _strings(value: Any, depth: int = 0) -> list[str]:
    if depth > 8:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for key, item in value.items():
            if key in {"path", "url", "output_path", "destination", "stdout_path"}:
                values.extend(_strings(item, depth + 1))
            elif isinstance(item, (dict, list)):
                values.extend(_strings(item, depth + 1))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_strings(item, depth + 1))
        return values
    return []


def completion_errors(state: Any) -> list[str]:
    """Require observed output evidence to retain a named standard directory."""
    directory = requested_standard_output_directory(
        str(getattr(state, "instruction", ""))
    )
    if directory is None:
        return []
    relevant = [
        event
        for event in getattr(state, "successful_adapter_events", lambda: [])()
        if str(event.proposed.get("action", "")) in OUTPUT_PATH_FIELDS
    ]
    if not relevant:
        return []
    if any(
        path_preserves_standard_directory(path, directory)
        for event in relevant
        for path in _strings(getattr(event, "result", None))
    ):
        return []
    return [
        f"successful output evidence does not reference the active user's {directory} "
        "directory explicitly required by the instruction"
    ]


def constrain_output_tools(
    tools: list[dict[str, Any]], state: Any
) -> list[dict[str, Any]]:
    """Add instruction-local guidance after retrieval without changing schema values."""
    directory = requested_standard_output_directory(
        str(getattr(state, "instruction", ""))
    )
    if directory is None:
        return tools
    tool_actions = {
        "adapter__" + re.sub(r"[^a-zA-Z0-9_]", "_", action): (action, fields)
        for action, fields in OUTPUT_PATH_FIELDS.items()
    }
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name", ""))
        matched = tool_actions.get(name)
        if matched is None:
            continue
        _action, fields = matched
        parameters = function.get("parameters")
        properties = (
            parameters.get("properties") if isinstance(parameters, dict) else None
        )
        if not isinstance(properties, dict):
            continue
        for field in fields:
            schema = properties.get(field)
            if not isinstance(schema, dict):
                continue
            schema["description"] = (
                str(schema.get("description", "")).rstrip()
                + f" The instruction explicitly requires the final output in the active "
                f"user's {directory} directory; preserve it in this model-selected path, "
                f"for example ~/{directory}/filename.ext."
            ).strip()
    return tools


__all__ = [
    "OUTPUT_PATH_FIELDS",
    "argument_contract_errors",
    "completion_errors",
    "constrain_output_tools",
    "output_path_argument",
    "path_preserves_standard_directory",
    "requested_standard_output_directory",
]
