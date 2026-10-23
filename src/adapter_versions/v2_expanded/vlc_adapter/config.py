from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .errors import AdapterError


VLC_CONFIG_PATH = Path("/home/user/.config/vlc/vlcrc")


def read_config(path: Path = VLC_CONFIG_PATH) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
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


def update_config(
    values: dict[str, str], path: Path = VLC_CONFIG_PATH
) -> dict[str, Any]:
    if path.exists() and not path.is_file():
        raise AdapterError("INVALID_CONFIG", f"VLC config path is not a file: {path}")
    before = read_config(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, value in values.items():
        pattern = re.compile(rf"(?m)^[ \t]*#?[ \t]*{re.escape(key)}=.*$")
        replacement = f"{key}={value}"
        if pattern.search(text):
            text = pattern.sub(replacement, text)
        else:
            if text and not text.endswith("\n"):
                text += "\n"
            text += replacement + "\n"
    _atomic_write(path, text)
    after = read_config(path)
    missing = {key: value for key, value in values.items() if after.get(key) != value}
    if missing:
        raise AdapterError(
            "INVALID_CONFIG",
            "VLC config did not persist requested values",
            {"path": str(path), "missing": missing, "observed": after},
            422,
        )
    return {"path": str(path), "values": values, "before": before, "after": after}
