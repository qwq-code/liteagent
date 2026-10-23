from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import time
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile

from .errors import AdapterError


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

WORD_P = f"{{{WORD_NS}}}p"
WORD_TEXT_NODES = frozenset(
    {
        f"{{{WORD_NS}}}t",
        f"{{{WORD_NS}}}instrText",
    }
)
WORD_SPACING_NODES = frozenset(
    {
        f"{{{WORD_NS}}}tab",
        f"{{{WORD_NS}}}br",
        f"{{{WORD_NS}}}cr",
    }
)

PDF_TEXT_BLOCK_RE = re.compile(
    rb"BT\s+([-+0-9.]+)\s+([-+0-9.]+)\s+Td\s+/([A-Za-z0-9_.-]+)\s+"
    rb"([-+0-9.]+)\s+Tf(?P<body>.*?)\s+ET",
    re.DOTALL,
)


@dataclass(frozen=True)
class DocxTextSources:
    body: tuple[str, ...]
    headers: dict[str, tuple[str, ...]]
    footers: dict[str, tuple[str, ...]]
    even_and_odd: bool
    title_page: bool


def _collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _leaf_paragraph_texts(root: ET.Element) -> tuple[str, ...]:
    paragraphs = []
    for paragraph in root.iter(WORD_P):
        if sum(1 for _item in paragraph.iter(WORD_P)) > 1:
            continue
        chunks = []
        for node in paragraph.iter():
            if node.tag in WORD_TEXT_NODES and node.text:
                chunks.append(node.text)
            elif node.tag in WORD_SPACING_NODES:
                chunks.append(" ")
        text = _collapse_text("".join(chunks))
        if text:
            paragraphs.append(text)
    return tuple(paragraphs)


def _part_path(target: str) -> str | None:
    path = PurePosixPath(target.lstrip("/"))
    if not target.startswith("/"):
        path = PurePosixPath("word") / path
    normalized = PurePosixPath(os.path.normpath(str(path)))
    if (
        not normalized.parts
        or normalized.parts[0] != "word"
        or ".." in normalized.parts
    ):
        return None
    return str(normalized)


def _unique_part_texts(
    archive: zipfile.ZipFile,
    targets: dict[str, set[str]],
) -> dict[str, tuple[str, ...]]:
    result = {}
    names = set(archive.namelist())
    for kind, candidates in targets.items():
        if len(candidates) != 1:
            continue
        path = _part_path(next(iter(candidates)))
        if path is None or path not in names:
            continue
        result[kind] = _leaf_paragraph_texts(ET.fromstring(archive.read(path)))
    return result


def load_docx_text_sources(path: Path | None) -> DocxTextSources | None:
    if path is None or path.suffix.lower() != ".docx" or not path.is_file():
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                return None
            document = ET.fromstring(archive.read("word/document.xml"))
            relationships = {}
            relationship_path = "word/_rels/document.xml.rels"
            if relationship_path in names:
                relationship_root = ET.fromstring(archive.read(relationship_path))
                relationships = {
                    item.attrib["Id"]: item.attrib["Target"]
                    for item in relationship_root.iter(
                        f"{{{PACKAGE_REL_NS}}}Relationship"
                    )
                    if "Id" in item.attrib and "Target" in item.attrib
                }

            related: dict[str, dict[str, set[str]]] = {
                "header": defaultdict(set),
                "footer": defaultdict(set),
            }
            title_page = False
            for section in document.iter(f"{{{WORD_NS}}}sectPr"):
                title_page = title_page or any(
                    item.tag == f"{{{WORD_NS}}}titlePg" for item in section
                )
                for role in ("header", "footer"):
                    for reference in section.iter(f"{{{WORD_NS}}}{role}Reference"):
                        kind = reference.attrib.get(f"{{{WORD_NS}}}type", "default")
                        relation_id = reference.attrib.get(f"{{{OFFICE_REL_NS}}}id")
                        target = relationships.get(str(relation_id))
                        if target:
                            related[role][kind].add(target)

            even_and_odd = False
            if "word/settings.xml" in names:
                settings = ET.fromstring(archive.read("word/settings.xml"))
                even_and_odd = any(
                    item.tag == f"{{{WORD_NS}}}evenAndOddHeaders"
                    for item in settings.iter()
                )
            return DocxTextSources(
                body=_leaf_paragraph_texts(document),
                headers=_unique_part_texts(archive, related["header"]),
                footers=_unique_part_texts(archive, related["footer"]),
                even_and_odd=even_and_odd,
                title_page=title_page,
            )
    except (ET.ParseError, KeyError, OSError, zipfile.BadZipFile):
        return None


def _page_part_kind(sources: DocxTextSources, page_index: int) -> str:
    if page_index == 0 and sources.title_page:
        return "first"
    if sources.even_and_odd and (page_index + 1) % 2 == 0:
        return "even"
    return "default"


def _page_text_corpus(
    sources: DocxTextSources,
    page_index: int,
) -> tuple[str, ...]:
    kind = _page_part_kind(sources, page_index)
    header = sources.headers.get(kind) or sources.headers.get("default", ())
    footer = sources.footers.get(kind) or sources.footers.get("default", ())
    return (*sources.body, *header, *footer)


def _soft_wrap_line_targets(
    lines: Iterable[str],
    paragraphs: Iterable[str],
) -> Counter[str]:
    line_list = list(lines)
    paragraph_list = tuple(paragraphs)
    targets: Counter[str] = Counter()
    for current, following in zip(line_list, line_list[1:]):
        if not current or not following or current.endswith((" ", "\u00a0")):
            continue
        joined = _collapse_text(f"{current} {following}")
        if joined and any(joined in paragraph for paragraph in paragraph_list):
            targets[current] += 1
    return targets


def _derive_soft_wrap_targets(
    document: Any,
    sources: DocxTextSources,
) -> Counter[tuple[int, str]]:
    targets: Counter[tuple[int, str]] = Counter()
    for page_index, page in enumerate(document):
        for text, count in _soft_wrap_line_targets(
            page.get_text().splitlines(),
            _page_text_corpus(sources, page_index),
        ).items():
            targets[(page_index, text)] += count
    return targets


def _append_pdf_space_code(body: bytes, code: bytes) -> bytes:
    if re.search(rb"\]\s*TJ\s*$", body):
        return re.sub(rb"\]\s*TJ\s*$", b"<" + code + b">]TJ", body)
    if re.search(rb">\s*Tj\s*$", body):
        return re.sub(rb">\s*Tj\s*$", code + b">Tj", body)
    raise AdapterError(
        "PDF_NORMALIZATION_FAILED",
        "unsupported PDF text-show operator while preserving a soft-wrap space",
    )


def _pdf_space_code(document: Any, font_xref: int) -> bytes:
    font_object = document.xref_object(font_xref)
    match = re.search(r"/ToUnicode\s+(\d+)\s+0\s+R", font_object)
    if not match:
        raise AdapterError(
            "PDF_NORMALIZATION_FAILED",
            "PDF font has no ToUnicode map for preserving soft-wrap spaces",
        )
    cmap = document.xref_stream(int(match.group(1)))
    match = re.search(rb"<([0-9A-Fa-f]+)>\s*<0020>", cmap)
    if not match:
        raise AdapterError(
            "PDF_NORMALIZATION_FAILED",
            "PDF font has no encoded space glyph",
        )
    return match.group(1).upper()


def _pending_pdf_lines(
    document: Any,
    targets: Counter[tuple[int, str]],
) -> dict[int, list[tuple[float, float, str, str]]]:
    remaining = targets.copy()
    pending: dict[int, list[tuple[float, float, str, str]]] = defaultdict(list)
    for page_index, page in enumerate(document):
        resource_by_font = {
            font[3].split("+", 1)[-1]: font[4] for font in page.get_fonts(full=True)
        }
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"])
                key = (page_index, text)
                if remaining[key] <= 0:
                    continue
                if not line["spans"]:
                    continue
                span = line["spans"][-1]
                resource = resource_by_font.get(span["font"])
                if not resource:
                    raise AdapterError(
                        "PDF_NORMALIZATION_FAILED",
                        "could not resolve a PDF font resource for a soft-wrap line",
                        {"page": page_index},
                    )
                pending[page_index].append(
                    (
                        float(span["origin"][0]),
                        float(page.rect.height - span["origin"][1]),
                        resource,
                        text,
                    )
                )
                remaining[key] -= 1
    if sum(remaining.values()):
        raise AdapterError(
            "PDF_NORMALIZATION_FAILED",
            "could not locate every derived soft-wrap line in the PDF layout",
            {"missing_count": sum(remaining.values())},
        )
    return dict(pending)


def _patch_pdf_lines(
    document: Any,
    pending: dict[int, list[tuple[float, float, str, str]]],
) -> int:
    patched = 0
    for page_index, wanted in pending.items():
        page = document[page_index]
        font_xrefs = {font[4]: int(font[0]) for font in page.get_fonts(full=True)}
        matched: set[int] = set()
        for content_xref in page.get_contents():
            stream = document.xref_stream(content_xref)
            replacements = []
            for match in PDF_TEXT_BLOCK_RE.finditer(stream):
                x = float(match.group(1))
                y = float(match.group(2))
                resource = match.group(3).decode("ascii")
                candidates = [
                    index
                    for index, item in enumerate(wanted)
                    if index not in matched
                    and item[2] == resource
                    and abs(item[0] - x) < 0.25
                    and abs(item[1] - y) < 0.25
                ]
                if len(candidates) != 1:
                    continue
                index = candidates[0]
                code = _pdf_space_code(document, font_xrefs[resource])
                replacements.append(
                    (
                        match.start("body"),
                        match.end("body"),
                        _append_pdf_space_code(match.group("body"), code),
                    )
                )
                matched.add(index)
            for start, end, replacement in reversed(replacements):
                stream = stream[:start] + replacement + stream[end:]
                patched += 1
            if replacements:
                document.update_stream(content_xref, stream)
        if len(matched) != len(wanted):
            raise AdapterError(
                "PDF_NORMALIZATION_FAILED",
                "could not match every derived soft-wrap line to a PDF text operation",
                {"page": page_index, "missing_count": len(wanted) - len(matched)},
            )
    return patched


def preserve_docx_soft_wrap_spaces(
    source_path: Path | None,
    pdf_path: Path,
) -> dict[str, Any]:
    sources = load_docx_text_sources(source_path)
    if sources is None:
        return {
            "status": "not_applicable",
            "source_format": source_path.suffix.lower() if source_path else None,
            "target_count": 0,
            "patched_trailing_spaces": 0,
        }
    try:
        import fitz
    except ImportError as exc:
        raise AdapterError(
            "PDF_NORMALIZATION_FAILED",
            "PyMuPDF is required to preserve DOCX soft-wrap spaces",
            str(exc),
            503,
        ) from exc

    document = fitz.open(pdf_path)
    temporary = pdf_path.with_name(
        f".{pdf_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        targets = _derive_soft_wrap_targets(document, sources)
        if not targets:
            return {
                "status": "no_changes",
                "source_format": ".docx",
                "target_count": 0,
                "patched_trailing_spaces": 0,
            }
        pending = _pending_pdf_lines(document, targets)
        patched = _patch_pdf_lines(document, pending)
        if patched != sum(targets.values()):
            raise AdapterError(
                "PDF_NORMALIZATION_FAILED",
                "soft-wrap space patch count differs from the derived target count",
                {"target_count": sum(targets.values()), "patched_count": patched},
            )
        document.save(temporary, garbage=4, deflate=True)
    finally:
        document.close()

    try:
        normalized = fitz.open(temporary)
        try:
            observed: Counter[tuple[int, str]] = Counter()
            for page_index, page in enumerate(normalized):
                for line in page.get_text().splitlines():
                    if line.endswith(" "):
                        observed[(page_index, line[:-1])] += 1
            missing = sum(
                max(0, count - observed[key]) for key, count in targets.items()
            )
        finally:
            normalized.close()
        if missing:
            raise AdapterError(
                "PDF_NORMALIZATION_FAILED",
                "saved PDF did not preserve every derived soft-wrap space",
                {"missing_count": missing},
            )
        temporary.replace(pdf_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "status": "applied",
        "source_format": ".docx",
        "target_count": sum(targets.values()),
        "patched_trailing_spaces": patched,
    }
