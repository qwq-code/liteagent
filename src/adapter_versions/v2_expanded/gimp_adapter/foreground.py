from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from .errors import AdapterError


SUPPORTED_OUTPUT_SUFFIXES = frozenset(
    {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)


def local_path(value: str) -> Path:
    if value.startswith("file://"):
        parsed = urlparse(value)
        if parsed.netloc not in {"", "localhost"}:
            raise AdapterError(
                "INVALID_ARGUMENT",
                "only local file URLs are supported",
                {"path": value},
            )
        value = unquote(parsed.path)
    return Path(value).expanduser()


def validate_image_suffix(value: str, field: str) -> None:
    suffix = local_path(value).suffix.casefold()
    if suffix not in SUPPORTED_OUTPUT_SUFFIXES:
        raise AdapterError(
            "INVALID_ARGUMENT",
            f"{field} must use a supported raster image suffix",
            {
                "field": field,
                "suffix": suffix,
                "supported": sorted(SUPPORTED_OUTPUT_SUFFIXES),
            },
        )
