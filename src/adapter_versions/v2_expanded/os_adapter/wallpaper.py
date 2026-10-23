from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

from .command import CommandRunner
from .errors import AdapterError


BACKGROUND_SCHEMA = "org.gnome.desktop.background"
SUPPORTED_IMAGE_SUFFIXES = frozenset(
    {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)


def _gvariant_string(value: str) -> str | None:
    try:
        parsed = ast.literal_eval(value.strip())
    except (SyntaxError, ValueError):
        return None
    return parsed if isinstance(parsed, str) else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _image_format(path: Path) -> str | None:
    with path.open("rb") as source:
        header = source.read(16)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if header.startswith(b"BM"):
        return "bmp"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    return None


def _read_setting(
    runner: CommandRunner, key: str, *, check: bool = True
) -> dict[str, Any]:
    return runner.run(
        ["gsettings", "get", BACKGROUND_SCHEMA, key],
        check=check,
        error_code="WALLPAPER_UNAVAILABLE",
        error_message=f"failed to read GNOME wallpaper setting {key}",
    )


def set_wallpaper(
    runner: CommandRunner, params: dict[str, Any], timeout: float
) -> dict[str, Any]:
    image = Path(params["image_path"]).expanduser()
    if not image.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"wallpaper image does not exist: {image}",
            {"image_path": str(image)},
            404,
        )
    image = image.resolve()
    if image.suffix.casefold() not in SUPPORTED_IMAGE_SUFFIXES:
        raise AdapterError(
            "INVALID_ARGUMENT",
            "desktop wallpaper must be a supported raster image",
            {
                "image_path": str(image),
                "supported_suffixes": sorted(SUPPORTED_IMAGE_SUFFIXES),
            },
            422,
        )
    image_format = _image_format(image)
    if image_format is None:
        raise AdapterError(
            "INVALID_IMAGE",
            "wallpaper path does not contain a supported raster image",
            {"image_path": str(image)},
            422,
        )

    uri = image.as_uri()
    bounded_timeout = max(0.1, min(10.0, timeout))
    runner.run(
        ["gsettings", "set", BACKGROUND_SCHEMA, "picture-uri", uri],
        timeout=bounded_timeout,
        error_code="WALLPAPER_UNAVAILABLE",
        error_message="failed to set GNOME wallpaper",
    )
    dark_update = runner.run(
        ["gsettings", "set", BACKGROUND_SCHEMA, "picture-uri-dark", uri],
        check=False,
        timeout=bounded_timeout,
    )

    observed_primary = _read_setting(runner, "picture-uri")["stdout"].strip()
    if _gvariant_string(observed_primary) != uri:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "GNOME picture-uri did not retain the selected wallpaper",
            {"expected_uri": uri, "observed": observed_primary},
            422,
        )

    settings = [
        {
            "schema": BACKGROUND_SCHEMA,
            "key": "picture-uri",
            "expected_uri": uri,
            "observed": observed_primary,
        }
    ]
    if dark_update.get("returncode") == 0:
        dark_read = _read_setting(runner, "picture-uri-dark", check=False)
        if dark_read.get("returncode") == 0:
            observed_dark = dark_read.get("stdout", "").strip()
            if _gvariant_string(observed_dark) != uri:
                raise AdapterError(
                    "VERIFICATION_FAILED",
                    "GNOME picture-uri-dark did not retain the selected wallpaper",
                    {"expected_uri": uri, "observed": observed_dark},
                    422,
                )
            settings.append(
                {
                    "schema": BACKGROUND_SCHEMA,
                    "key": "picture-uri-dark",
                    "expected_uri": uri,
                    "observed": observed_dark,
                }
            )

    return {
        "image_path": str(image),
        "image_size_bytes": image.stat().st_size,
        "image_format": image_format,
        "image_sha256": _sha256_file(image),
        "wallpaper_uri": uri,
        "settings": settings,
        "verified": True,
    }
