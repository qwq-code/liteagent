from __future__ import annotations

from pathlib import Path


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


__all__ = ["NON_ROOT_LOCAL_PATH_PATTERN", "is_protected_local_root"]
