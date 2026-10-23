from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import AdapterError


def load_json(path: Path, expected_type: type, default: Any) -> Any:
    if not path.exists():
        return default
    if not path.is_file():
        raise AdapterError("INVALID_JSON", f"JSON path is not a file: {path}")
    text = path.read_text(encoding="utf-8")
    attempts = [text]
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("//"):
        attempts.append("\n".join(lines[1:]))
    for candidate in attempts:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, expected_type):
            raise AdapterError(
                "INVALID_JSON",
                f"expected {expected_type.__name__} in {path}",
                {"actual_type": type(value).__name__},
            )
        return value
    raise AdapterError("INVALID_JSON", f"could not parse JSON: {path}")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=4, ensure_ascii=False) + "\n")


def deep_merge(current: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def is_subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and is_subset(value, actual[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return expected == actual
    return expected == actual
