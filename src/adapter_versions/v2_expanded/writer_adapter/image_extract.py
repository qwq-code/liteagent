from __future__ import annotations

import hashlib
import mimetypes
import os
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from .errors import AdapterError


MAX_IMAGE_REFERENCES = 256
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
DOCX_DOCUMENT_PART = "word/document.xml"
DOCX_RELATIONSHIPS_PART = "word/_rels/document.xml.rels"
ODT_CONTENT_PART = "content.xml"
ODT_MANIFEST_PART = "META-INF/manifest.xml"


def _local_path(value: str, field: str) -> Path:
    if value.startswith(("/", "~/")):
        return Path(value).expanduser()
    parsed = urlparse(value)
    if (
        parsed.scheme == "file"
        and parsed.netloc in {"", "localhost"}
        and unquote(parsed.path).startswith("/")
    ):
        return Path(unquote(parsed.path))
    raise AdapterError(
        "INVALID_ARGUMENT",
        f"{field} must be an absolute, ~/, or local file URL path",
    )


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _parse_xml(archive: zipfile.ZipFile, member: str) -> ET.Element:
    try:
        return ET.fromstring(archive.read(member))
    except KeyError as error:
        raise AdapterError(
            "INVALID_DOCUMENT",
            f"document package is missing {member}",
            {"missing_member": member},
            422,
        ) from error
    except ET.ParseError as error:
        raise AdapterError(
            "INVALID_DOCUMENT",
            f"document package contains invalid XML in {member}",
            {"member": member, "error": str(error)},
            422,
        ) from error


def _normalized_member(base_part: str, target: str) -> str:
    decoded = unquote(target).replace("\\", "/")
    if decoded.startswith("/"):
        normalized = posixpath.normpath(decoded.lstrip("/"))
    else:
        normalized = posixpath.normpath(
            posixpath.join(posixpath.dirname(base_part), decoded)
        )
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        raise AdapterError(
            "INVALID_DOCUMENT",
            "document image reference escapes the package root",
            {"base_part": base_part, "target": target},
            422,
        )
    return normalized


def _docx_references(archive: zipfile.ZipFile) -> list[str]:
    relationships = _parse_xml(archive, DOCX_RELATIONSHIPS_PART)
    image_targets: dict[str, str] = {}
    for relationship in relationships:
        relationship_type = relationship.attrib.get("Type", "")
        if not relationship_type.rstrip("/").endswith("/image"):
            continue
        if relationship.attrib.get("TargetMode", "").casefold() == "external":
            continue
        relationship_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if relationship_id and target:
            image_targets[relationship_id] = _normalized_member(
                DOCX_DOCUMENT_PART, target
            )

    document = _parse_xml(archive, DOCX_DOCUMENT_PART)
    references: list[str] = []
    for element in document.iter():
        for attribute, relationship_id in element.attrib.items():
            if _local_name(attribute) not in {"embed", "id"}:
                continue
            member = image_targets.get(relationship_id)
            if member is not None:
                references.append(member)
    return references


def _odt_references(archive: zipfile.ZipFile) -> list[str]:
    content = _parse_xml(archive, ODT_CONTENT_PART)
    references: list[str] = []
    for element in content.iter():
        if _local_name(element.tag) != "image":
            continue
        href = next(
            (
                value
                for attribute, value in element.attrib.items()
                if _local_name(attribute) == "href"
            ),
            None,
        )
        if not href or urlparse(href).scheme:
            continue
        references.append(_normalized_member(ODT_CONTENT_PART, href))
    return references


def _docx_media_types(archive: zipfile.ZipFile) -> dict[str, str]:
    root = _parse_xml(archive, "[Content_Types].xml")
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for element in root:
        if _local_name(element.tag) == "Default":
            extension = element.attrib.get("Extension", "").casefold()
            content_type = element.attrib.get("ContentType", "")
            if extension and content_type:
                defaults[extension] = content_type
        elif _local_name(element.tag) == "Override":
            member = element.attrib.get("PartName", "").lstrip("/")
            content_type = element.attrib.get("ContentType", "")
            if member and content_type:
                overrides[member] = content_type
    return {
        member: overrides.get(
            member,
            defaults.get(PurePosixPath(member).suffix.lstrip(".").casefold(), ""),
        )
        for member in archive.namelist()
    }


def _odt_media_types(archive: zipfile.ZipFile) -> dict[str, str]:
    if ODT_MANIFEST_PART not in archive.namelist():
        return {}
    root = _parse_xml(archive, ODT_MANIFEST_PART)
    media_types: dict[str, str] = {}
    for element in root.iter():
        if _local_name(element.tag) != "file-entry":
            continue
        path = next(
            (
                value
                for attribute, value in element.attrib.items()
                if _local_name(attribute) == "full-path"
            ),
            "",
        )
        media_type = next(
            (
                value
                for attribute, value in element.attrib.items()
                if _local_name(attribute) == "media-type"
            ),
            "",
        )
        if path and media_type:
            media_types[posixpath.normpath(path)] = media_type
    return media_types


def _safe_extension(member: str, media_type: str) -> str:
    extension = PurePosixPath(member).suffix.casefold()
    if re.fullmatch(r"\.[a-z0-9]{1,10}", extension):
        return extension
    guessed = mimetypes.guess_extension(media_type or "") or ".bin"
    return ".jpg" if guessed == ".jpe" else guessed


def _output_stem(source: Path) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip("-._")
    return normalized or "document"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_document_images(params: dict[str, Any]) -> dict[str, Any]:
    source = _local_path(params["source_path"], "params.source_path")
    if not source.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"source document does not exist: {source}",
            {"source_path": str(source)},
            404,
        )
    source = source.resolve()
    document_format = source.suffix.casefold().lstrip(".")
    if document_format not in {"docx", "odt"}:
        raise AdapterError(
            "INVALID_ARGUMENT",
            "source document must be a DOCX or ODT package",
            {"source_path": str(source)},
            422,
        )

    try:
        with zipfile.ZipFile(source) as archive:
            if document_format == "docx":
                references = _docx_references(archive)
                media_types = _docx_media_types(archive)
            else:
                references = _odt_references(archive)
                media_types = _odt_media_types(archive)
            if len(references) > MAX_IMAGE_REFERENCES:
                raise AdapterError(
                    "DOCUMENT_LIMIT_EXCEEDED",
                    "document contains too many image references",
                    {
                        "reference_count": len(references),
                        "maximum": MAX_IMAGE_REFERENCES,
                    },
                    422,
                )
            if not references:
                raise AdapterError(
                    "NO_EMBEDDED_IMAGES",
                    "document contains no embedded images in its main content",
                    {"source_path": str(source)},
                    422,
                )

            selected = (
                references[:1]
                if params.get("selection", "all") == "first"
                else references
            )
            names = set(archive.namelist())
            missing = [member for member in selected if member not in names]
            if missing:
                raise AdapterError(
                    "INVALID_DOCUMENT",
                    "document references missing embedded image members",
                    {"missing_members": missing},
                    422,
                )
            infos = [archive.getinfo(member) for member in selected]
            oversized = [
                {"member": info.filename, "size_bytes": info.file_size}
                for info in infos
                if info.file_size > MAX_IMAGE_BYTES
            ]
            total_bytes = sum(info.file_size for info in infos)
            if oversized or total_bytes > MAX_TOTAL_BYTES:
                raise AdapterError(
                    "DOCUMENT_LIMIT_EXCEEDED",
                    "embedded image extraction exceeds the bounded size limit",
                    {
                        "oversized_members": oversized,
                        "total_bytes": total_bytes,
                        "maximum_total_bytes": MAX_TOTAL_BYTES,
                    },
                    422,
                )
            payloads = [archive.read(member) for member in selected]
    except zipfile.BadZipFile as error:
        raise AdapterError(
            "INVALID_DOCUMENT",
            "source is not a valid DOCX or ODT package",
            {"source_path": str(source)},
            422,
        ) from error

    output_directory = _local_path(
        params["output_directory"], "params.output_directory"
    )
    if output_directory.exists() and not output_directory.is_dir():
        raise AdapterError(
            "INVALID_ARGUMENT",
            "output_directory exists but is not a directory",
            {"output_directory": str(output_directory)},
            422,
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    output_directory = output_directory.resolve()

    destinations = [
        output_directory
        / f"{_output_stem(source)}-image-{index:03d}{_safe_extension(member, media_types.get(member, ''))}"
        for index, member in enumerate(selected, start=1)
    ]
    if not params.get("overwrite", True):
        existing = [str(path) for path in destinations if path.exists()]
        if existing:
            raise AdapterError(
                "DESTINATION_EXISTS",
                "one or more extracted image destinations already exist",
                {"paths": existing},
                409,
            )

    images: list[dict[str, Any]] = []
    for index, (member, payload, destination) in enumerate(
        zip(selected, payloads, destinations, strict=True), start=1
    ):
        with tempfile.NamedTemporaryFile(
            dir=output_directory,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
        digest = _sha256_bytes(payload)
        observed_digest = _sha256_file(destination)
        if observed_digest != digest or destination.stat().st_size != len(payload):
            raise AdapterError(
                "VERIFICATION_FAILED",
                "extracted image did not match the embedded document member",
                {"path": str(destination), "expected_sha256": digest},
                422,
            )
        media_type = media_types.get(member) or mimetypes.guess_type(member)[0]
        images.append(
            {
                "index": index,
                "archive_member": member,
                "output_path": str(destination),
                "media_type": media_type,
                "size_bytes": len(payload),
                "sha256": digest,
            }
        )

    return {
        "source_path": str(source),
        "source_sha256": _sha256_file(source),
        "document_format": document_format,
        "selection": params.get("selection", "all"),
        "reference_count": len(references),
        "extracted_count": len(images),
        "output_directory": str(output_directory),
        "images": images,
    }
