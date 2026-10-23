from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests


CACHE_ENVIRONMENT_VARIABLE = "OSWORLD_VSCODE_EXTENSION_CACHE"
DEFAULT_CACHE_DIRECTORY = Path.home() / ".cache" / "computer_use" / "vscode"


@dataclass(frozen=True)
class OfflineExtension:
    extension_id: str
    version: str
    vscode_engine: str
    url: str
    sha256: str
    filename: str


OFFLINE_EXTENSIONS = (
    OfflineExtension(
        extension_id="ms-python.debugpy",
        version="2024.0.0",
        vscode_engine="^1.78.0",
        url=(
            "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
            "ms-python/vsextensions/debugpy/2024.0.0/vspackage?targetPlatform=linux-x64"
        ),
        sha256="01449500168f494b1fee8cc5cad3b3cee74effea9ec9a0aab9ad12c945e73deb",
        filename="ms-python.debugpy-2024.0.0-linux-x64.vsix",
    ),
    OfflineExtension(
        extension_id="ms-python.python",
        version="2024.0.1",
        vscode_engine="^1.82.0",
        url=(
            "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
            "ms-python/vsextensions/python/2024.0.1/vspackage"
        ),
        sha256="3eaaa4d22c602d5b1783e6239eb434a844f63917f6a23e07cfd3e93040056946",
        filename="ms-python.python-2024.0.1.vsix",
    ),
)

GUEST_OFFLINE_EXTENSION_DIRECTORY = (
    Path(__file__).resolve().parent / "deploy" / "offline_extensions"
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_offline_extension(path: Path, expected: OfflineExtension) -> dict[str, Any]:
    observed_sha256 = file_sha256(path)
    if observed_sha256 != expected.sha256:
        raise ValueError(
            f"VSIX hash mismatch for {expected.extension_id}: {observed_sha256}"
        )
    try:
        with zipfile.ZipFile(path) as archive:
            package = json.loads(archive.read("extension/package.json"))
            bad_member = archive.testzip()
    except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid VSIX for {expected.extension_id}: {exc}") from exc
    if bad_member is not None:
        raise ValueError(
            f"corrupt VSIX member for {expected.extension_id}: {bad_member}"
        )
    observed = {
        "extension_id": (
            f"{str(package.get('publisher', '')).casefold()}."
            f"{str(package.get('name', '')).casefold()}"
        ),
        "version": str(package.get("version", "")),
        "vscode_engine": str((package.get("engines") or {}).get("vscode", "")),
    }
    required = {
        "extension_id": expected.extension_id,
        "version": expected.version,
        "vscode_engine": expected.vscode_engine,
    }
    if observed != required:
        raise ValueError(
            f"VSIX manifest mismatch for {expected.extension_id}: {observed}"
        )
    return {
        **observed,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": observed_sha256,
        "source_url": expected.url,
    }


def offline_extension_path(
    extension_id: str,
    directory: Path | None = None,
) -> Path | None:
    """Return a deployed, pinned VSIX path for a model-selected extension ID."""
    normalized = extension_id.strip().casefold()
    expected = next(
        (item for item in OFFLINE_EXTENSIONS if item.extension_id == normalized),
        None,
    )
    if expected is None:
        return None
    path = (directory or GUEST_OFFLINE_EXTENSION_DIRECTORY) / expected.filename
    return path if path.is_file() else None


def extension_cache_directory() -> Path:
    configured = os.environ.get(CACHE_ENVIRONMENT_VARIABLE)
    return Path(configured).expanduser() if configured else DEFAULT_CACHE_DIRECTORY


def _download(
    expected: OfflineExtension,
    destination: Path,
    session: requests.Session,
) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        response = session.get(expected.url, stream=True, timeout=(15, 180))
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
        verify_offline_extension(temporary, expected)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_offline_extensions(
    *,
    cache_directory: Path | None = None,
    extensions: Iterable[OfflineExtension] = OFFLINE_EXTENSIONS,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    cache = (cache_directory or extension_cache_directory()).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    results = []
    for expected in extensions:
        destination = cache / expected.filename
        if destination.is_file():
            try:
                results.append(verify_offline_extension(destination, expected))
                continue
            except ValueError:
                destination.unlink()
        _download(expected, destination, client)
        results.append(verify_offline_extension(destination, expected))
    return results
