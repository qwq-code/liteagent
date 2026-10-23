from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET
import zipfile

from .errors import AdapterError


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MAX_DOCX_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_XML_BYTES = 5 * 1024 * 1024
MAX_SECTIONS = 500
MAX_CANDIDATE_PATHS = 12
MAX_CANDIDATE_HEADING_PREFIXES = 12


def _local_path(value: str) -> Path:
    if value.startswith("file://"):
        parsed = urlparse(value)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise AdapterError(
                "INVALID_SOURCE_PATH",
                "notes_path must be a local file URL",
                {"notes_path": value},
                422,
            )
        path = Path(unquote(parsed.path))
    else:
        path = Path(value).expanduser()
    return path


def nearby_docx_recovery(path: Path, *, exclude: Path | None = None) -> dict[str, Any]:
    directory = path if path.is_dir() else path.parent
    try:
        directory = directory.resolve(strict=True)
        candidates = sorted(
            candidate.resolve()
            for candidate in directory.iterdir()
            if candidate.is_file()
            and not candidate.name.startswith(".")
            and candidate.suffix.casefold() == ".docx"
            and (exclude is None or candidate.resolve() != exclude)
        )
    except OSError:
        candidates = []
    return {
        "candidate_docx_paths": [
            str(candidate) for candidate in candidates[:MAX_CANDIDATE_PATHS]
        ],
        "candidate_docx_count": len(candidates),
        "candidate_docx_paths_truncated": len(candidates) > MAX_CANDIDATE_PATHS,
        "selection_required": True,
    }


def resolve_docx_path(value: str) -> Path:
    path = _local_path(value)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise AdapterError(
            "SOURCE_NOT_FOUND",
            "the notes document does not exist; select an appropriate candidate_docx_path and retry",
            {"notes_path": value, **nearby_docx_recovery(path)},
            404,
        ) from exc
    if not resolved.is_file() or resolved.suffix.casefold() != ".docx":
        raise AdapterError(
            "INVALID_SOURCE",
            "notes_path must identify a DOCX file; select an appropriate candidate_docx_path and retry",
            {
                "notes_path": str(resolved),
                **nearby_docx_recovery(path, exclude=resolved),
            },
            422,
        )
    if resolved.stat().st_size > MAX_DOCX_BYTES:
        raise AdapterError(
            "SOURCE_TOO_LARGE",
            "the notes document exceeds the 20 MiB limit",
            {"notes_path": str(resolved), "bytes": resolved.stat().st_size},
            422,
        )
    return resolved


def _paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        local_name = node.tag.rsplit("}", 1)[-1]
        if local_name == "t":
            parts.append(node.text or "")
        elif local_name == "tab":
            parts.append("\t")
        elif local_name in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts)


def read_docx_paragraphs(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCUMENT_XML_BYTES:
                raise AdapterError(
                    "SOURCE_TOO_LARGE",
                    "word/document.xml exceeds the 5 MiB limit",
                    {"notes_path": str(path), "document_xml_bytes": info.file_size},
                    422,
                )
            document_xml = archive.read(info)
    except AdapterError:
        raise
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise AdapterError(
            "INVALID_SOURCE",
            "notes_path is not a readable DOCX document",
            {"notes_path": str(path), "error": f"{type(exc).__name__}: {exc}"},
            422,
        ) from exc
    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise AdapterError(
            "INVALID_SOURCE",
            "the DOCX document XML is malformed",
            {"notes_path": str(path), "error": str(exc)},
            422,
        ) from exc
    return [
        _paragraph_text(paragraph) for paragraph in root.iter(f"{{{WORD_NAMESPACE}}}p")
    ]


def _section_text(paragraphs: Sequence[str], *, section_number: int) -> str:
    normalized = [paragraph.strip() for paragraph in paragraphs]
    while normalized and not normalized[0]:
        normalized.pop(0)
    while normalized and not normalized[-1]:
        normalized.pop()
    if not normalized or not any(normalized):
        raise AdapterError(
            "SOURCE_SECTION_EMPTY",
            "a numbered notes section contains no text",
            {"section_number": section_number},
            422,
        )
    return "\n".join(normalized)


def numbered_heading_prefix_recovery(paragraphs: Sequence[str]) -> dict[str, Any]:
    pattern = re.compile(r"^\s*(.+?)\s+([1-9][0-9]*)\s*:\s*$")
    candidates: dict[str, str] = {}
    for paragraph in paragraphs:
        match = pattern.fullmatch(paragraph)
        if not match:
            continue
        prefix = re.sub(r"\s+", " ", match.group(1).strip())
        if not prefix or len(prefix) > 80:
            continue
        candidates.setdefault(prefix.casefold(), prefix)
    values = list(candidates.values())
    return {
        "candidate_heading_prefixes": values[:MAX_CANDIDATE_HEADING_PREFIXES],
        "candidate_heading_prefix_count": len(values),
        "candidate_heading_prefixes_truncated": len(values)
        > MAX_CANDIDATE_HEADING_PREFIXES,
        "heading_prefix_selection_required": True,
    }


def parse_numbered_sections(
    paragraphs: Sequence[str],
    *,
    heading_prefix: str,
    case_sensitive: bool = False,
) -> dict[int, str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(
        rf"^\s*{re.escape(heading_prefix.strip())}\s+([1-9][0-9]*)\s*:\s*$",
        flags,
    )
    raw_sections: dict[int, list[str]] = {}
    current_number: int | None = None
    for paragraph in paragraphs:
        match = pattern.fullmatch(paragraph)
        if match:
            number = int(match.group(1))
            if number in raw_sections:
                raise AdapterError(
                    "SOURCE_SECTION_NOT_UNIQUE",
                    "the notes document contains a duplicate numbered heading",
                    {"heading_prefix": heading_prefix, "section_number": number},
                    422,
                )
            if len(raw_sections) >= MAX_SECTIONS:
                raise AdapterError(
                    "SOURCE_TOO_LARGE",
                    "the notes document contains more than 500 numbered sections",
                    {"heading_prefix": heading_prefix},
                    422,
                )
            raw_sections[number] = []
            current_number = number
            continue
        if current_number is not None:
            raw_sections[current_number].append(paragraph)
    if not raw_sections:
        raise AdapterError(
            "SOURCE_SECTIONS_NOT_FOUND",
            "no numbered notes headings matched heading_prefix; select an appropriate candidate_heading_prefix and retry",
            {
                "heading_prefix": heading_prefix,
                **numbered_heading_prefix_recovery(paragraphs),
            },
            404,
        )
    return {
        number: _section_text(content, section_number=number)
        for number, content in raw_sections.items()
    }


def build_missing_notes_plan(
    presentation: Mapping[str, Any], sections: Mapping[int, str]
) -> dict[str, Any]:
    slide_count = presentation.get("slide_count")
    slides = presentation.get("slides")
    if (
        isinstance(slide_count, bool)
        or not isinstance(slide_count, int)
        or slide_count < 1
        or not isinstance(slides, list)
    ):
        raise AdapterError(
            "PRESENTATION_STATE_INVALID",
            "presentation.inspect returned an invalid slide collection",
            status_code=502,
        )
    notes_by_index: dict[int, str] = {}
    for slide in slides:
        if not isinstance(slide, Mapping):
            continue
        index = slide.get("index")
        notes = slide.get("notes", "")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < slide_count
            or not isinstance(notes, str)
            or index in notes_by_index
        ):
            raise AdapterError(
                "PRESENTATION_STATE_INVALID",
                "presentation.inspect returned an ambiguous slide or notes value",
                {"slide": dict(slide)},
                502,
            )
        notes_by_index[index] = notes
    if set(notes_by_index) != set(range(slide_count)):
        raise AdapterError(
            "PRESENTATION_STATE_INVALID",
            "presentation.inspect did not return every slide exactly once",
            {
                "slide_count": slide_count,
                "returned_indices": sorted(notes_by_index),
            },
            502,
        )
    out_of_range = sorted(
        number for number in sections if number < 1 or number > slide_count
    )
    if out_of_range:
        raise AdapterError(
            "SOURCE_SECTION_OUT_OF_RANGE",
            "numbered notes sections refer to slides outside the active presentation",
            {"slide_count": slide_count, "section_numbers": out_of_range},
            422,
        )
    missing_indices = [
        index for index, notes in sorted(notes_by_index.items()) if not notes.strip()
    ]
    missing_sections = [
        index + 1 for index in missing_indices if index + 1 not in sections
    ]
    if missing_sections:
        raise AdapterError(
            "SOURCE_SECTIONS_MISSING",
            "the notes document lacks one or more sections for blank slides",
            {
                "missing_slide_numbers": missing_sections,
                "available_section_numbers": sorted(sections),
            },
            422,
        )
    return {
        "slide_count": slide_count,
        "notes_before": notes_by_index,
        "updates": [
            {
                "slide_index": index,
                "slide_number": index + 1,
                "text": notes_by_index[index] + sections[index + 1],
            }
            for index in missing_indices
        ],
        "skipped_existing_slide_numbers": [
            index + 1
            for index, notes in sorted(notes_by_index.items())
            if notes.strip()
        ],
    }
