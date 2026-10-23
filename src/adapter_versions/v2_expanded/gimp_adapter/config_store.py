from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .errors import AdapterError


CONFIG_DIR = Path.home() / ".config" / "GIMP" / "2.10"
TOKEN_RE = re.compile(r"^\s*\(([^\s()]+)(?:\s+(.*?))?\)\s*$")


def encode_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise AdapterError("INVALID_ARGUMENT", "config value must be a scalar")


def parse_tokens(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise AdapterError(
            "CONFIG_ERROR", f"failed to read {path}", str(exc), 500
        ) from exc
    result: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#"):
            continue
        match = TOKEN_RE.match(line)
        if match:
            result[match.group(1)] = (match.group(2) or "").strip()
    return result


def update_typed_config(file_name: str, key: str, value: Any) -> dict[str, Any]:
    if file_name not in {"gimprc", "sessionrc"}:
        raise AdapterError("INVALID_ARGUMENT", "unsupported GIMP config file")
    path = CONFIG_DIR / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    token = encode_value(value)
    try:
        original = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise AdapterError(
            "CONFIG_ERROR", f"failed to read {path}", str(exc), 500
        ) from exc

    lines = original.splitlines()
    replacement = f"({key} {token})"
    changed = False
    output: list[str] = []
    for line in lines:
        match = TOKEN_RE.match(line)
        if match and match.group(1) == key:
            if not changed:
                output.append(replacement)
                changed = True
            continue
        output.append(line)
    if not changed:
        output.append(replacement)
    content = "\n".join(output).rstrip("\n") + "\n"

    backup = path.with_suffix(path.suffix + ".osworld-adapter.bak")
    if path.exists():
        backup.write_text(original, encoding="utf-8")
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, delete=False, encoding="utf-8"
        ) as temp:
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
            temporary = Path(temp.name)
        os.chmod(temporary, path.stat().st_mode if path.exists() else 0o600)
        temporary.replace(path)
        observed = parse_tokens(path).get(key)
        if observed != token:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "GIMP config token did not persist",
                {
                    "path": str(path),
                    "key": key,
                    "expected": token,
                    "observed": observed,
                },
                422,
            )
    except Exception:
        if backup.exists():
            backup.replace(path)
        raise
    return {
        "path": str(path),
        "key": key,
        "value": value,
        "token": token,
        "observed_token": observed,
    }
