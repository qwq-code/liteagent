from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from .errors import AdapterError


# Keep the public schema compatible with guided-schema engines. The runtime
# canonicalizes paths and rejects lexical aliases of protected roots.
NON_ROOT_LOCAL_PATH_PATTERN = r"^(?:/.+|~/.+)$"


def is_protected_local_root(path: Path, *, home: Path | None = None) -> bool:
    """Return whether a path resolves to a filesystem or user-home root."""
    try:
        resolved = path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    home_path = (home or Path.home()).resolve()
    return resolved == Path("/").resolve() or resolved in {
        home_path,
        *home_path.parents,
    }


def normalize_local_path(value: str, *, home: Path | None = None) -> Path:
    """Convert an explicit public local-path representation into a filesystem path."""
    if not isinstance(value, str) or not value:
        raise AdapterError("INVALID_ARGUMENT", "local path must be a non-empty string")

    if value.startswith("file://"):
        parsed = urlparse(value)
        if (
            parsed.scheme != "file"
            or parsed.netloc not in {"", "localhost"}
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise AdapterError(
                "INVALID_ARGUMENT",
                "file URI must reference the local host without params, query, or fragment",
                {"path": value},
            )
        decoded = unquote(parsed.path)
    else:
        decoded = unquote(value)

    if "\x00" in decoded:
        raise AdapterError("INVALID_ARGUMENT", "local path contains a null byte")
    if decoded == "/~":
        decoded = "~"
    elif decoded.startswith("/~/"):
        decoded = decoded[1:]

    home_path = (home or Path.home()).resolve()
    if decoded == "~":
        return home_path
    if decoded.startswith("~/"):
        return home_path / decoded[2:]

    path = Path(decoded)
    if not path.is_absolute():
        raise AdapterError(
            "INVALID_ARGUMENT",
            "local path must be absolute, begin with ~/, or use a local file URI",
            {"path": value},
        )
    return path


__all__ = [
    "NON_ROOT_LOCAL_PATH_PATTERN",
    "is_protected_local_root",
    "normalize_local_path",
]
