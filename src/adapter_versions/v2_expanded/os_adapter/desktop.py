from __future__ import annotations

import configparser
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .command import CommandRunner
from .errors import AdapterError


@dataclass(frozen=True)
class DesktopApplication:
    desktop_id: str
    name: str
    path: Path
    mime_types: tuple[str, ...]


def application_directories() -> tuple[Path, ...]:
    return (
        Path.home() / ".local/share/applications",
        Path("/usr/local/share/applications"),
        Path("/usr/share/applications"),
    )


def _tokens(value: str) -> set[str]:
    ignored = {"app", "application", "com", "desktop", "gnome", "org"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if token not in ignored
    }


def _read_entry(path: Path, root: Path) -> DesktopApplication | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with path.open(encoding="utf-8", errors="replace") as source:
            parser.read_file(source)
    except (OSError, configparser.Error):
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    section = parser["Desktop Entry"]
    if section.get("Hidden", "false").casefold() == "true":
        return None
    relative = path.relative_to(root)
    desktop_id = "-".join(relative.parts)
    mime_types = tuple(
        sorted({value for value in section.get("MimeType", "").split(";") if value})
    )
    return DesktopApplication(
        desktop_id=desktop_id,
        name=section.get("Name", path.stem),
        path=path,
        mime_types=mime_types,
    )


def installed_applications(
    directories: Iterable[Path] | None = None,
) -> tuple[DesktopApplication, ...]:
    entries: dict[str, DesktopApplication] = {}
    for root in directories or application_directories():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.desktop")):
            entry = _read_entry(path, root)
            if entry is not None:
                entries.setdefault(entry.desktop_id.casefold(), entry)
    return tuple(entries.values())


def inspect_applications(
    params: dict[str, Any],
    directories: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """List matching Desktop Entries without selecting a mutation target."""
    query = str(params.get("query", "")).strip()
    requested = _tokens(query)
    prefixes = tuple(
        f"{prefix.casefold()}/" for prefix in params.get("mime_type_prefixes", [])
    )
    max_results = int(params.get("max_results", 20))
    mime_offset = int(params.get("mime_offset", 0))
    mime_page_size = int(params.get("max_mime_types_per_application", 12))
    matches: list[dict[str, Any]] = []
    for entry in sorted(
        installed_applications(directories), key=lambda item: item.desktop_id
    ):
        searchable = _tokens(f"{entry.desktop_id} {entry.name}")
        if requested and not requested.issubset(searchable):
            continue
        relevant_types = [
            mime_type
            for mime_type in entry.mime_types
            if not prefixes or mime_type.casefold().startswith(prefixes)
        ]
        if prefixes and not relevant_types:
            continue
        mime_page = relevant_types[mime_offset : mime_offset + mime_page_size]
        next_mime_offset = (
            mime_offset + len(mime_page)
            if mime_offset + len(mime_page) < len(relevant_types)
            else None
        )
        matches.append(
            {
                "desktop_id": entry.desktop_id,
                "name": entry.name,
                "desktop_file": str(entry.path),
                "mime_types": mime_page,
                "advertised_mime_type_count": len(entry.mime_types),
                "matching_mime_type_count": len(relevant_types),
                "mime_offset": mime_offset,
                "returned_mime_type_count": len(mime_page),
                "mime_types_truncated": next_mime_offset is not None,
                "next_mime_offset": next_mime_offset,
            }
        )
    return {
        "query": query or None,
        "mime_type_prefixes": list(params.get("mime_type_prefixes", [])),
        "max_results": max_results,
        "mime_offset": mime_offset,
        "max_mime_types_per_application": mime_page_size,
        "match_count": len(matches),
        "truncated": len(matches) > max_results,
        "applications": matches[:max_results],
    }


def resolve_application(
    application: str,
    directories: Iterable[Path] | None = None,
) -> DesktopApplication:
    entries = installed_applications(directories)
    exact_id = [
        entry
        for entry in entries
        if entry.desktop_id.casefold() == application.casefold()
    ]
    if len(exact_id) == 1:
        return exact_id[0]
    requested = _tokens(application)
    ranked: list[tuple[int, int, int, str, DesktopApplication]] = []
    for entry in entries:
        candidates = (_tokens(entry.desktop_id), _tokens(entry.name))
        scores = [
            (
                int(requested == candidate),
                int(bool(requested) and requested.issubset(candidate)),
                len(requested.intersection(candidate)),
            )
            for candidate in candidates
        ]
        score = max(scores)
        if score[2]:
            ranked.append((*score, entry.desktop_id, entry))
    if not ranked:
        raise AdapterError(
            "APPLICATION_NOT_FOUND",
            f"no installed desktop application matches: {application}",
            {"available": sorted(entry.desktop_id for entry in entries)},
            404,
        )
    ranked.sort(reverse=True)
    best_score = ranked[0][:3]
    matches = [
        entry for *score, _desktop_id, entry in ranked if tuple(score) == best_score
    ]
    if len(matches) != 1:
        raise AdapterError(
            "AMBIGUOUS_APPLICATION",
            f"multiple installed applications match: {application}",
            {"matches": sorted(entry.desktop_id for entry in matches)},
            409,
        )
    return matches[0]


def mime_association_state(
    runner: CommandRunner,
    mime_types: Iterable[str],
) -> dict[str, str]:
    return {
        mime_type: runner.run(["xdg-mime", "query", "default", mime_type], check=False)[
            "stdout"
        ].strip()
        for mime_type in sorted(set(mime_types))
    }


def set_mime_associations(
    runner: CommandRunner,
    params: dict[str, Any],
    timeout: float,
    directories: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Set model-selected exact types or advertised categories for one Desktop ID."""
    desktop_id = params["desktop_id"]
    matches = [
        entry
        for entry in installed_applications(directories)
        if entry.desktop_id.casefold() == desktop_id.casefold()
    ]
    if len(matches) != 1:
        raise AdapterError(
            "APPLICATION_NOT_FOUND",
            f"no unique installed Desktop Entry has ID: {desktop_id}",
            {"desktop_id": desktop_id},
            404,
        )
    entry = matches[0]
    if "mime_types" in params:
        selected = sorted(set(params["mime_types"]))
    else:
        prefixes = tuple(f"{prefix}/" for prefix in params["mime_type_prefixes"])
        selected = sorted(mime for mime in entry.mime_types if mime.startswith(prefixes))
    if not selected:
        raise AdapterError(
            "MIME_TYPES_NOT_ADVERTISED",
            "the selected Desktop Entry advertises no matching MIME types",
            {"desktop_id": entry.desktop_id},
            422,
        )
    advertised = set(entry.mime_types)
    unsupported = sorted(set(selected) - advertised)
    if unsupported:
        raise AdapterError(
            "MIME_TYPES_NOT_ADVERTISED",
            "one or more exact MIME types are not advertised by the selected Desktop Entry",
            {
                "desktop_id": entry.desktop_id,
                "unsupported_mime_types": unsupported,
                "advertised_mime_types": list(entry.mime_types),
            },
            422,
        )
    before = mime_association_state(runner, selected)
    for mime_type in selected:
        runner.run(
            ["xdg-mime", "default", entry.desktop_id, mime_type],
            timeout=timeout,
            error_code="DEFAULT_APPLICATION_FAILED",
            error_message=f"failed to set the default application for {mime_type}",
        )
    observed = mime_association_state(runner, selected)
    return {
        "application": entry.name,
        "desktop_id": entry.desktop_id,
        "desktop_file": str(entry.path),
        "mime_types": selected,
        "before": before,
        "observed": observed,
    }


def set_default_application(
    runner: CommandRunner,
    params: dict[str, Any],
    timeout: float,
    directories: Iterable[Path] | None = None,
) -> dict[str, Any]:
    entry = resolve_application(params["application"], directories)
    if "mime_types" in params:
        selected = sorted(set(params["mime_types"]))
    else:
        prefixes = tuple(f"{prefix}/" for prefix in params["mime_type_prefixes"])
        selected = sorted(
            mime_type
            for mime_type in entry.mime_types
            if mime_type.startswith(prefixes)
        )
    if not selected:
        raise AdapterError(
            "MIME_TYPES_NOT_ADVERTISED",
            "the selected application advertises no matching MIME types",
            {
                "desktop_id": entry.desktop_id,
                "advertised_mime_types": list(entry.mime_types),
            },
            422,
        )
    before = mime_association_state(runner, selected)
    for mime_type in selected:
        runner.run(
            ["xdg-mime", "default", entry.desktop_id, mime_type],
            timeout=timeout,
            error_code="DEFAULT_APPLICATION_FAILED",
            error_message=f"failed to set the default application for {mime_type}",
        )
    observed = mime_association_state(runner, selected)
    return {
        "application": entry.name,
        "desktop_id": entry.desktop_id,
        "desktop_file": str(entry.path),
        "mime_types": selected,
        "before": before,
        "observed": observed,
    }
