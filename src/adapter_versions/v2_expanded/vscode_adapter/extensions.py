from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .errors import AdapterError


MAX_MANIFEST_BYTES = 1_048_576


def _member_bytes(archive: ZipFile, candidates: tuple[str, ...]) -> bytes | None:
    names = {name.casefold(): name for name in archive.namelist()}
    for candidate in candidates:
        member = names.get(candidate.casefold())
        if member is None:
            continue
        info = archive.getinfo(member)
        if info.file_size > MAX_MANIFEST_BYTES:
            raise AdapterError(
                "INVALID_VSIX",
                f"VSIX metadata member is too large: {member}",
            )
        return archive.read(member)
    return None


def _manifest_identity(raw: bytes) -> tuple[str, str] | None:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise AdapterError("INVALID_VSIX", "VSIX manifest is not valid XML") from exc
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "Identity":
            continue
        extension_name = (
            element.attrib.get("Id") or element.attrib.get("ID") or ""
        ).strip()
        publisher = (element.attrib.get("Publisher") or "").strip()
        if extension_name and publisher:
            return publisher, extension_name
    return None


def _package_identity(raw: bytes) -> tuple[str, str] | None:
    try:
        package = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError(
            "INVALID_VSIX", "VSIX package.json is not valid JSON"
        ) from exc
    if not isinstance(package, dict):
        return None
    extension_name = str(package.get("name") or "").strip()
    publisher = str(package.get("publisher") or "").strip()
    if extension_name and publisher:
        return publisher, extension_name
    return None


def vsix_extension_id(path: Path) -> str:
    try:
        with ZipFile(path) as archive:
            manifest = _member_bytes(archive, ("extension.vsixmanifest",))
            identity = _manifest_identity(manifest) if manifest is not None else None
            if identity is None:
                package = _member_bytes(
                    archive, ("extension/package.json", "package.json")
                )
                identity = _package_identity(package) if package is not None else None
    except (BadZipFile, OSError) as exc:
        raise AdapterError("INVALID_VSIX", f"cannot read VSIX archive: {path}") from exc

    if identity is None:
        raise AdapterError(
            "INVALID_VSIX",
            "VSIX metadata does not identify both publisher and extension name",
        )
    publisher, extension_name = identity
    return f"{publisher}.{extension_name}"


def resolve_installed_extension_id(
    metadata_extension_id: str,
    before_ids: list[str],
    after_ids: list[str],
) -> str | None:
    expected = metadata_extension_id.casefold()
    before = {extension_id.casefold() for extension_id in before_ids}
    after = {extension_id.casefold() for extension_id in after_ids}
    if expected in after:
        return expected

    new_ids = sorted(after - before)
    extension_name = expected.rsplit(".", 1)[-1]
    matching_new = [
        extension_id
        for extension_id in new_ids
        if extension_id.rsplit(".", 1)[-1] == extension_name
    ]
    if len(matching_new) == 1:
        return matching_new[0]
    if len(new_ids) == 1:
        return new_ids[0]

    matching_installed = [
        extension_id
        for extension_id in sorted(after)
        if extension_id.rsplit(".", 1)[-1] == extension_name
    ]
    if len(matching_installed) == 1:
        return matching_installed[0]
    return None
