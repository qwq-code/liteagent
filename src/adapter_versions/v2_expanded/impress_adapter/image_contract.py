from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .errors import AdapterError


SUPPORTED_IMAGE_SUFFIXES = frozenset(
    {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".tif", ".tiff", ".webp"}
)

# JSON Schema has no portable case-insensitive flag. Spell out the suffixes so
# the model-visible schema and Adapter validation enforce the same contract.
IMAGE_PATH_PATTERN = (
    r"^(?:/|~/).+\."
    r"(?:[Bb][Mm][Pp]|[Gg][Ii][Ff]|[Jj][Pp][Ee][Gg]|[Jj][Pp][Gg]|"
    r"[Pp][Nn][Gg]|[Ss][Vv][Gg]|[Tt][Ii][Ff]|[Tt][Ii][Ff][Ff]|"
    r"[Ww][Ee][Bb][Pp])$"
)
IMAGE_PATH_OR_FILE_URL_PATTERN = (
    r"^(?:(?:file://)?/|~/).+\."
    r"(?:[Bb][Mm][Pp]|[Gg][Ii][Ff]|[Jj][Pp][Ee][Gg]|[Jj][Pp][Gg]|"
    r"[Pp][Nn][Gg]|[Ss][Vv][Gg]|[Tt][Ii][Ff]|[Tt][Ii][Ff][Ff]|"
    r"[Ww][Ee][Bb][Pp])$"
)


def validate_image_path_suffixes(image_paths: Iterable[str]) -> None:
    unsupported = []
    for raw_path in image_paths:
        suffix = Path(raw_path).suffix.casefold()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            unsupported.append({"path": raw_path, "suffix": suffix or None})
    if unsupported:
        raise AdapterError(
            "INVALID_REQUEST",
            "image operations accept supported image files only",
            {
                "unsupported_paths": unsupported,
                "supported_suffixes": sorted(SUPPORTED_IMAGE_SUFFIXES),
                "mutation_started": False,
            },
            422,
        )


def validate_local_image_path(path: str) -> None:
    """Reject relative and non-local image inputs before any document mutation."""
    if not path.startswith(("/", "~/", "file:///")):
        raise AdapterError(
            "INVALID_REQUEST",
            "image path must be an absolute path, ~/ path, or local file URL",
        )
    validate_image_path_suffixes([path])
