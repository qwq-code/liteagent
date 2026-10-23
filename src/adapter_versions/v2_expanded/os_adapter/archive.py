from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import AdapterError


MAX_ARCHIVE_MEMBERS = 10_000
MAX_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _safe_member_parts(info: zipfile.ZipInfo) -> tuple[str, ...]:
    raw = info.filename
    if not raw or "\x00" in raw or raw.startswith(("/", "\\")) or "\\" in raw:
        raise AdapterError(
            "UNSAFE_ARCHIVE_MEMBER",
            "ZIP contains an absolute, empty, or non-portable member path",
            {"member": raw},
            422,
        )
    parts = raw[:-1].split("/") if raw.endswith("/") else raw.split("/")
    if (
        not parts
        or any(part in {"", ".", ".."} for part in parts)
        or re.match(r"^[A-Za-z]:", parts[0])
    ):
        raise AdapterError(
            "UNSAFE_ARCHIVE_MEMBER",
            "ZIP member path is not a safe relative path",
            {"member": raw},
            422,
        )
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise AdapterError(
            "UNSAFE_ARCHIVE_MEMBER",
            "ZIP symbolic-link members are not extracted",
            {"member": raw},
            422,
        )
    if info.flag_bits & 0x1:
        raise AdapterError(
            "UNSUPPORTED_ARCHIVE",
            "encrypted ZIP members are not supported",
            {"member": raw},
            422,
        )
    return tuple(parts)


def inspect_zip(path: Path) -> list[dict[str, Any]]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise AdapterError(
                    "ARCHIVE_LIMIT_EXCEEDED",
                    f"ZIP contains more than {MAX_ARCHIVE_MEMBERS} members",
                    {"member_count": len(infos)},
                    422,
                )
            total_size = sum(info.file_size for info in infos)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise AdapterError(
                    "ARCHIVE_LIMIT_EXCEEDED",
                    "ZIP uncompressed size exceeds the extraction safety limit",
                    {"uncompressed_bytes": total_size},
                    422,
                )

            seen: set[str] = set()
            members = []
            for info in infos:
                parts = _safe_member_parts(info)
                normalized = PurePosixPath(*parts).as_posix()
                key = normalized.casefold()
                if key in seen:
                    raise AdapterError(
                        "ARCHIVE_MEMBER_CONFLICT",
                        "ZIP contains duplicate or case-colliding member paths",
                        {"member": normalized},
                        422,
                    )
                seen.add(key)
                members.append(
                    {
                        "name": normalized,
                        "kind": "directory" if info.is_dir() else "file",
                        "size_bytes": info.file_size,
                        "compressed_size_bytes": info.compress_size,
                    }
                )

            bad_member = archive.testzip()
            if bad_member is not None:
                raise AdapterError(
                    "ARCHIVE_INTEGRITY_FAILED",
                    "ZIP CRC verification failed",
                    {"member": bad_member},
                    422,
                )
            return members
    except AdapterError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise AdapterError(
            "INVALID_ARCHIVE",
            "archive_path is not a readable ZIP archive",
            {"path": str(path), "error": str(error)},
            422,
        ) from error


def _create_entries(
    input_paths: list[str], base_directory: str | None, archive_path: Path
) -> list[tuple[Path, str]]:
    base = _path(base_directory) if base_directory is not None else None
    if base is not None and (not base.is_dir() or base.is_symlink()):
        raise AdapterError(
            "INVALID_ARGUMENT",
            "base_directory must be an existing non-symlink directory",
            {"base_directory": str(base)},
        )

    entries: list[tuple[Path, str]] = []
    for raw_path in input_paths:
        source = Path(raw_path).expanduser()
        if not source.exists():
            raise AdapterError(
                "PATH_NOT_FOUND",
                f"input path does not exist: {source}",
                http_status=404,
            )
        if source.is_symlink():
            raise AdapterError(
                "UNSAFE_INPUT_PATH",
                "symbolic-link inputs are not archived",
                {"path": str(source)},
                422,
            )
        source = source.resolve()
        if source == archive_path:
            raise AdapterError(
                "INVALID_ARGUMENT",
                "archive_path cannot also be an input path",
                {"path": str(source)},
            )
        if base is not None:
            try:
                prefix = source.relative_to(base)
            except ValueError as error:
                raise AdapterError(
                    "INVALID_ARGUMENT",
                    "every input path must be inside base_directory",
                    {"path": str(source), "base_directory": str(base)},
                ) from error
        else:
            prefix = Path(source.name)

        if source.is_file():
            entries.append((source, prefix.as_posix()))
            continue
        if not source.is_dir():
            raise AdapterError(
                "INVALID_ARGUMENT",
                "input_paths supports only regular files and directories",
                {"path": str(source)},
            )
        for child in sorted(source.rglob("*")):
            if child.is_symlink():
                raise AdapterError(
                    "UNSAFE_INPUT_PATH",
                    "symbolic links below an input directory are not archived",
                    {"path": str(child)},
                    422,
                )
            if child.is_file() and child.resolve() != archive_path:
                member = prefix / child.relative_to(source)
                entries.append((child.resolve(), member.as_posix()))

    if not entries:
        raise AdapterError(
            "NO_MATCHES",
            "input_paths did not contain any regular files",
            http_status=404,
        )
    if len(entries) > MAX_ARCHIVE_MEMBERS:
        raise AdapterError(
            "ARCHIVE_LIMIT_EXCEEDED",
            f"input_paths expands to more than {MAX_ARCHIVE_MEMBERS} files",
            {"file_count": len(entries)},
            422,
        )
    total_size = sum(source.stat().st_size for source, _member in entries)
    if total_size > MAX_UNCOMPRESSED_BYTES:
        raise AdapterError(
            "ARCHIVE_LIMIT_EXCEEDED",
            "input files exceed the archive size safety limit",
            {"uncompressed_bytes": total_size},
            422,
        )

    seen: dict[str, str] = {}
    for _source, member in entries:
        key = member.casefold()
        if key in seen:
            raise AdapterError(
                "ARCHIVE_MEMBER_CONFLICT",
                "multiple inputs map to the same ZIP member path",
                {"first": seen[key], "second": member},
                409,
            )
        seen[key] = member
    return entries


def _create(params: dict[str, Any]) -> dict[str, Any]:
    archive_path = _path(params["archive_path"])
    if archive_path.exists() and not params.get("overwrite", False):
        raise AdapterError(
            "DESTINATION_CONFLICT",
            "archive_path already exists; pass overwrite=true to replace it",
            {"archive_path": str(archive_path)},
            409,
        )
    if archive_path.exists() and not archive_path.is_file():
        raise AdapterError(
            "INVALID_ARGUMENT",
            "archive_path exists and is not a regular file",
            {"archive_path": str(archive_path)},
        )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    entries = _create_entries(
        params["input_paths"], params.get("base_directory"), archive_path
    )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{archive_path.name}.", suffix=".tmp", dir=archive_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            for source, member in entries:
                archive.write(source, arcname=member)
        members = inspect_zip(temporary)
        expected = [member for _source, member in entries]
        if [item["name"] for item in members] != expected:
            raise AdapterError(
                "ARCHIVE_INTEGRITY_FAILED",
                "created ZIP members do not match the selected inputs",
                {
                    "expected_members": expected,
                    "observed_members": [item["name"] for item in members],
                },
                422,
            )
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "mode": "create",
        "archive_path": str(archive_path),
        "archive_size_bytes": archive_path.stat().st_size,
        "input_paths": [str(_path(path)) for path in params["input_paths"]],
        "base_directory": (
            str(_path(params["base_directory"]))
            if params.get("base_directory")
            else None
        ),
        "members": members,
        "member_count": len(members),
        "uncompressed_bytes": sum(item["size_bytes"] for item in members),
        "overwrite": bool(params.get("overwrite", False)),
        "integrity_verified": True,
    }


def _extract(params: dict[str, Any]) -> dict[str, Any]:
    archive_path = _path(params["archive_path"])
    if not archive_path.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"archive_path is not a file: {archive_path}",
            http_status=404,
        )
    destination = _path(params["destination_directory"])
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise AdapterError(
            "INVALID_ARGUMENT",
            "destination_directory must be a directory and not a symbolic link",
            {"destination_directory": str(destination)},
        )
    members = inspect_zip(archive_path)
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()

    planned: list[tuple[dict[str, Any], Path]] = []
    for member in members:
        target = destination.joinpath(*PurePosixPath(member["name"]).parts)
        resolved_target = target.resolve(strict=False)
        if (
            destination != resolved_target
            and destination not in resolved_target.parents
        ):
            raise AdapterError(
                "UNSAFE_ARCHIVE_MEMBER",
                "ZIP member resolves outside destination_directory",
                {"member": member["name"]},
                422,
            )
        if target.exists() and not params.get("overwrite", False):
            raise AdapterError(
                "DESTINATION_CONFLICT",
                "one or more extracted paths already exist",
                {"path": str(target), "member": member["name"]},
                409,
            )
        if member["kind"] == "file" and target.exists() and target.is_dir():
            raise AdapterError(
                "DESTINATION_CONFLICT",
                "a ZIP file member conflicts with an existing directory",
                {"path": str(target), "member": member["name"]},
                409,
            )
        planned.append((member, target))

    extracted_files = []
    with zipfile.ZipFile(archive_path, "r") as archive:
        for member, target in planned:
            if member["kind"] == "directory":
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with (
                archive.open(member["name"], "r") as source,
                target.open("wb") as output,
            ):
                shutil.copyfileobj(source, output)
            extracted_files.append(
                {"path": str(target), "size_bytes": target.stat().st_size}
            )

    return {
        "mode": "extract",
        "archive_path": str(archive_path),
        "archive_size_bytes": archive_path.stat().st_size,
        "destination_directory": str(destination),
        "members": members,
        "member_count": len(members),
        "uncompressed_bytes": sum(item["size_bytes"] for item in members),
        "extracted_files": extracted_files,
        "overwrite": bool(params.get("overwrite", False)),
        "integrity_verified": True,
    }


def create_zip(params: dict[str, Any], _timeout: float) -> dict[str, Any]:
    return _create(params)


def extract_zip(params: dict[str, Any], _timeout: float) -> dict[str, Any]:
    return _extract(params)
