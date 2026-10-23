from __future__ import annotations

from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlparse

from .errors import AdapterError


EXPORT_FORMAT_SUFFIXES: Final[dict[str, tuple[str, ...]]] = {
    "pptx": (".pptx",),
    "odp": (".odp",),
    "pdf": (".pdf",),
    "png": (".png",),
    "jpg": (".jpg", ".jpeg"),
}


def export_destination_suffix(path_or_url: str) -> str:
    """Return the lowercase suffix of a local path or encoded file URL."""
    if not isinstance(path_or_url, str) or not path_or_url.strip():
        raise AdapterError(
            "INVALID_REQUEST", "params.url must be a non-empty local path or file URL"
        )
    parsed = urlparse(path_or_url)
    if parsed.scheme and parsed.scheme != "file":
        raise AdapterError(
            "INVALID_REQUEST", "params.url must be a local path or file URL"
        )
    local_path = unquote(parsed.path) if parsed.scheme == "file" else path_or_url
    return Path(local_path).suffix.casefold()


def validate_export_destination(format_name: str, path_or_url: str) -> None:
    """Reject output paths whose extension contradicts the selected format."""
    normalized_format = str(format_name).casefold()
    allowed = EXPORT_FORMAT_SUFFIXES.get(normalized_format)
    if allowed is None:
        raise AdapterError("INVALID_REQUEST", "params.format is unsupported")
    actual = export_destination_suffix(path_or_url)
    if actual in allowed:
        return
    expected = " or ".join(allowed)
    observed = actual or "no extension"
    raise AdapterError(
        "INVALID_REQUEST",
        (
            f"params.url must end with {expected} when params.format is "
            f"{normalized_format}; got {observed}"
        ),
        {
            "format": normalized_format,
            "allowed_extensions": list(allowed),
            "actual_extension": actual or None,
        },
    )
