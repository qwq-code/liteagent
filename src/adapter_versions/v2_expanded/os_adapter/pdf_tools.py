from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .errors import AdapterError
from .local_paths import normalize_local_path


_UNSAFE_FILENAME = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
_MAX_FILENAME_STEM_BYTES = 180
_PDFTOCAIRO = Path("/usr/bin/pdftocairo")
_PORTABLE_PAGE_MIN_SIMILARITY = 0.98
_PORTABLE_DOCUMENT_MIN_SIMILARITY = 0.995


def _source_file(path: str) -> Path:
    source = normalize_local_path(path)
    if not source.exists():
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"PDF does not exist: {source}",
            {"requested_path": path, "resolved_path": str(source)},
            http_status=404,
        )
    if not source.is_file():
        raise AdapterError("INVALID_ARGUMENT", f"PDF path is not a file: {source}")
    if source.suffix.casefold() != ".pdf":
        raise AdapterError("INVALID_ARGUMENT", "input_path must end with .pdf")
    return source.resolve()


def _output_file(path: str) -> Path:
    output = normalize_local_path(path)
    if output.suffix.casefold() != ".pdf":
        raise AdapterError("INVALID_ARGUMENT", "output_path must end with .pdf")
    return output


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _page_text_fingerprints(pages: Iterable[Any]) -> dict[str, Any]:
    extracted: list[str] = []
    for page in pages:
        extracted.append(page.extract_text() or "")
    text = "\n\f\n".join(extracted)
    portable_pages = [_portable_text(item) for item in extracted]
    portable_text = "".join(portable_pages)
    return {
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_character_count": len(text),
        "portable_text_sha256": hashlib.sha256(
            portable_text.encode("ascii")
        ).hexdigest(),
        "portable_text_character_count": len(portable_text),
        "_portable_pages": portable_pages,
    }


def _portable_text(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text).casefold()
        if "a" <= character <= "z" or "0" <= character <= "9"
    )


def _public_text_fingerprints(fingerprints: dict[str, Any]) -> dict[str, Any]:
    return {
        key: fingerprints[key]
        for key in (
            "text_sha256",
            "text_character_count",
            "portable_text_sha256",
            "portable_text_character_count",
        )
    }


def _safe_filename_stem(title: str) -> str:
    stem = _UNSAFE_FILENAME.sub(" ", title)
    stem = re.sub(r"\s+", " ", stem).strip(" .") or "Untitled"
    encoded = stem.encode("utf-8")
    if len(encoded) > _MAX_FILENAME_STEM_BYTES:
        stem = encoded[:_MAX_FILENAME_STEM_BYTES].decode("utf-8", "ignore").rstrip(" .")
    return stem or "Untitled"


def _load_pypdf() -> tuple[Any, Any]:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise AdapterError(
            "PDF_LIBRARY_UNAVAILABLE",
            "the bundled pypdf dependency is not installed",
            {"import_error": str(exc)},
            http_status=503,
        ) from exc
    return PdfReader, PdfWriter


def _read_pdf(source: Path, PdfReader: Any) -> Any:
    try:
        reader = PdfReader(str(source))
        if reader.is_encrypted:
            raise AdapterError(
                "ENCRYPTED_PDF_UNSUPPORTED",
                "input_path is encrypted and cannot be read deterministically",
                http_status=422,
            )
        if len(reader.pages) < 1:
            raise AdapterError(
                "EMPTY_PDF", "input_path contains no pages", http_status=422
            )
        return reader
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "INVALID_PDF",
            "input_path is not a readable PDF",
            {"path": str(source), "error": str(exc)},
            422,
        ) from exc


def _outline_entries(reader: Any, outline_level: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []

    def visit(items: list[Any], level: int) -> None:
        for item in items:
            if isinstance(item, list):
                visit(item, level + 1)
                continue
            if level != outline_level:
                continue
            title = str(getattr(item, "title", None) or item.get("/Title") or "")
            try:
                page_index = reader.get_destination_page_number(item)
            except Exception as exc:
                raise AdapterError(
                    "INVALID_PDF_OUTLINE",
                    "an outline entry does not resolve to a PDF page",
                    {"outline_level": outline_level, "title": title},
                    422,
                ) from exc
            if not isinstance(page_index, int) or not 0 <= page_index < len(
                reader.pages
            ):
                raise AdapterError(
                    "INVALID_PDF_OUTLINE",
                    "an outline entry points outside the PDF",
                    {
                        "outline_level": outline_level,
                        "title": title,
                        "page_index": page_index,
                        "page_count": len(reader.pages),
                    },
                    422,
                )
            selected.append(
                {
                    "title": title.strip() or "Untitled",
                    "page_index": page_index,
                }
            )

    outline = reader.outline
    if not isinstance(outline, list):
        raise AdapterError(
            "PDF_OUTLINE_NOT_FOUND",
            "the PDF does not contain a readable outline",
            {"outline_level": outline_level},
            422,
        )
    visit(outline, 1)
    if not selected:
        raise AdapterError(
            "PDF_OUTLINE_LEVEL_NOT_FOUND",
            f"the PDF has no outline entries at level {outline_level}",
            {"outline_level": outline_level},
            422,
        )
    for previous, current in zip(selected, selected[1:]):
        if current["page_index"] <= previous["page_index"]:
            raise AdapterError(
                "NON_MONOTONIC_PDF_OUTLINE",
                "outline entries at the selected level must start on increasing pages",
                {
                    "outline_level": outline_level,
                    "previous": previous,
                    "current": current,
                },
                422,
            )
    return selected


def inspect_pdf_outline(params: dict[str, Any], _timeout: float) -> dict[str, Any]:
    """Return bounded, exact outline-derived page ranges without naming outputs."""
    PdfReader, _ = _load_pypdf()
    source = _source_file(params["input_path"])
    reader = _read_pdf(source, PdfReader)
    outline_level = int(params["outline_level"])
    offset = int(params.get("offset", 0))
    max_sections = int(params.get("max_sections", 20))
    if offset < 0 or not 1 <= max_sections <= 50:
        raise AdapterError(
            "INVALID_ARGUMENT",
            "offset must be nonnegative and max_sections must be from 1 to 50",
        )
    entries = _outline_entries(reader, outline_level)
    page_count = len(reader.pages)

    sections: list[dict[str, Any]] = []
    for position, entry in enumerate(entries):
        start_page = entry["page_index"] + 1
        end_page = (
            entries[position + 1]["page_index"]
            if position + 1 < len(entries)
            else page_count
        )
        sections.append(
            {
                "index": position + 1,
                "title": entry["title"],
                "start_page": start_page,
                "end_page": end_page,
                "page_count": end_page - start_page + 1,
            }
        )

    returned = sections[offset : offset + max_sections]
    next_offset = offset + len(returned)
    truncated = next_offset < len(sections)
    return {
        "input_path": str(source),
        "source_sha256": _sha256_file(source),
        "source_page_count": page_count,
        "outline_level": outline_level,
        "prefix_page_count": entries[0]["page_index"],
        "section_count": len(sections),
        "offset": offset,
        "max_sections": max_sections,
        "returned_count": len(returned),
        "truncated": truncated,
        "next_offset": next_offset if truncated else None,
        "sections": returned,
    }


def _output_name(*, title: str, number: int, filename_style: str) -> str:
    safe_title = _safe_filename_stem(title)
    if filename_style == "number_and_title":
        return f"{number}. {safe_title}.pdf"
    if filename_style == "title":
        return f"{safe_title}.pdf"
    return f"{number}.pdf"


def _verify_pdf(
    path: Path,
    *,
    expected_page_count: int,
    expected_text_fingerprints: dict[str, Any],
    PdfReader: Any,
) -> dict[str, Any]:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            return {
                "passed": False,
                "reason": "encrypted_output",
                "page_count": None,
                "text_sha256": None,
            }
        page_count = len(reader.pages)
        fingerprints = _page_text_fingerprints(reader.pages)
        metadata = reader.metadata
        producer = str(metadata.get("/Producer", "")) if metadata else ""
    except Exception as exc:
        return {
            "passed": False,
            "reason": "unreadable_output",
            "error": str(exc),
            "page_count": None,
            "text_sha256": None,
        }
    raw_text_match = (
        fingerprints["text_sha256"] == expected_text_fingerprints["text_sha256"]
    )
    portable_text_match = bool(
        expected_text_fingerprints["portable_text_character_count"] >= 256
        and fingerprints["portable_text_character_count"]
        == expected_text_fingerprints["portable_text_character_count"]
        and fingerprints["portable_text_sha256"]
        == expected_text_fingerprints["portable_text_sha256"]
    )
    portable_page_similarities: list[float] = []
    expected_portable_pages = expected_text_fingerprints.get("_portable_pages")
    observed_portable_pages = fingerprints.get("_portable_pages")
    if (
        not raw_text_match
        and not portable_text_match
        and isinstance(expected_portable_pages, list)
        and isinstance(observed_portable_pages, list)
        and len(expected_portable_pages) == len(observed_portable_pages)
        and expected_text_fingerprints["portable_text_character_count"] >= 256
    ):
        portable_page_similarities = [
            SequenceMatcher(None, expected, observed, autojunk=False).ratio()
            for expected, observed in zip(
                expected_portable_pages, observed_portable_pages
            )
        ]
    portable_similarity_mean = (
        sum(portable_page_similarities) / len(portable_page_similarities)
        if portable_page_similarities
        else None
    )
    portable_similarity_min = (
        min(portable_page_similarities) if portable_page_similarities else None
    )
    portable_text_similarity_match = bool(
        portable_similarity_mean is not None
        and portable_similarity_min is not None
        and portable_similarity_mean >= _PORTABLE_DOCUMENT_MIN_SIMILARITY
        and portable_similarity_min >= _PORTABLE_PAGE_MIN_SIMILARITY
    )
    return {
        "passed": page_count == expected_page_count
        and (raw_text_match or portable_text_match or portable_text_similarity_match),
        "reason": None,
        "page_count": page_count,
        **_public_text_fingerprints(fingerprints),
        "producer": producer,
        "portable_page_similarity_mean": portable_similarity_mean,
        "portable_page_similarity_min": portable_similarity_min,
        "match_mode": (
            "raw_extracted_text_sha256"
            if raw_text_match
            else "portable_extracted_text_sha256"
            if portable_text_match
            else "portable_page_text_similarity"
            if portable_text_similarity_match
            else None
        ),
    }


def _producer_family(producer: str) -> str | None:
    normalized = producer.casefold()
    if "cairo" in normalized:
        return "cairo"
    if normalized:
        return "other"
    return None


def _selected_output_backend(
    requested: str, sections: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    producers = sorted(
        {
            str(section["producer"])
            for section in sections
            if section.get("status") == "reused" and section.get("producer")
        }
    )
    if requested != "auto":
        return requested, producers
    families = {_producer_family(producer) for producer in producers}
    families.discard(None)
    return ("cairo" if families == {"cairo"} else "preserve_pages"), producers


def _write_preserved_pages(
    *, reader: Any, start: int, end: int, staged_path: Path, PdfWriter: Any
) -> None:
    writer = PdfWriter()
    for page_index in range(start, end):
        writer.add_page(reader.pages[page_index])
    with staged_path.open("wb") as stream:
        writer.write(stream)
        stream.flush()
        os.fsync(stream.fileno())


def _write_cairo_pages(
    *, source: Path, start: int, end: int, staged_path: Path, deadline: float
) -> None:
    if not _PDFTOCAIRO.is_file() or not os.access(_PDFTOCAIRO, os.X_OK):
        raise AdapterError(
            "PDF_RENDERER_UNAVAILABLE",
            f"required PDF renderer is unavailable: {_PDFTOCAIRO}",
            http_status=503,
        )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AdapterError(
            "OPERATION_TIMEOUT",
            "PDF split deadline expired before Cairo rendering",
            http_status=504,
        )
    try:
        completed = subprocess.run(
            [
                str(_PDFTOCAIRO),
                "-pdf",
                "-f",
                str(start + 1),
                "-l",
                str(end),
                str(source),
                str(staged_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=remaining,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdapterError(
            "OPERATION_TIMEOUT",
            "PDF split deadline expired during Cairo rendering",
            http_status=504,
        ) from exc
    if completed.returncode != 0 or not staged_path.is_file():
        raise AdapterError(
            "PDF_RENDER_FAILED",
            "Cairo could not render the selected PDF page span",
            {
                "returncode": completed.returncode,
                "stderr": completed.stderr[-4000:],
                "source_start_page": start + 1,
                "source_end_page": end,
            },
            422,
        )
    with staged_path.open("rb") as stream:
        os.fsync(stream.fileno())


def extract_pdf_pages(params: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Persist exactly one model-named PDF containing one explicit page range."""
    PdfReader, PdfWriter = _load_pypdf()
    source = _source_file(params["input_path"])
    output = _output_file(params["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    if output == source:
        raise AdapterError(
            "OUTPUT_CONFLICT",
            "output_path must not replace input_path",
            {"path": str(output)},
            409,
        )
    overwrite = bool(params["overwrite"])
    existed_before = output.exists()
    if existed_before and not overwrite:
        raise AdapterError(
            "OUTPUT_EXISTS",
            "output_path already exists; select a different path or set overwrite=true",
            {"output_path": str(output)},
            409,
        )

    reader = _read_pdf(source, PdfReader)
    start_page = int(params["start_page"])
    end_page = int(params["end_page"])
    page_count = len(reader.pages)
    if (
        start_page < 1
        or end_page < 1
        or start_page > end_page
        or end_page > page_count
    ):
        raise AdapterError(
            "PAGE_RANGE_OUT_OF_BOUNDS",
            "start_page and end_page must select an inclusive range within input_path",
            {
                "start_page": start_page,
                "end_page": end_page,
                "source_page_count": page_count,
            },
            422,
        )

    start_index = start_page - 1
    end_index = end_page
    expected_fingerprints = _page_text_fingerprints(reader.pages[start_index:end_index])
    source_sha256 = _sha256_file(source)
    output_backend = params["output_backend"]
    if output_backend not in {"preserve_pages", "cairo"}:
        raise AdapterError(
            "INVALID_ARGUMENT", "output_backend must be preserve_pages or cairo"
        )
    deadline = time.monotonic() + max(0.1, timeout)

    with tempfile.TemporaryDirectory(
        prefix=".osworld-pdf-pages-", dir=output.parent
    ) as temporary_directory:
        staged_path = Path(temporary_directory) / "output.pdf"
        if output_backend == "cairo":
            _write_cairo_pages(
                source=source,
                start=start_index,
                end=end_index,
                staged_path=staged_path,
                deadline=deadline,
            )
        else:
            _write_preserved_pages(
                reader=reader,
                start=start_index,
                end=end_index,
                staged_path=staged_path,
                PdfWriter=PdfWriter,
            )
        staged_verification = _verify_pdf(
            staged_path,
            expected_page_count=end_page - start_page + 1,
            expected_text_fingerprints=expected_fingerprints,
            PdfReader=PdfReader,
        )
        if not staged_verification["passed"]:
            raise AdapterError(
                "PDF_OUTPUT_VERIFICATION_FAILED",
                "the staged PDF did not match the selected source page range",
                {"output_path": str(output), "observed": staged_verification},
                422,
            )
        if _sha256_file(source) != source_sha256:
            raise AdapterError(
                "SOURCE_PDF_CHANGED",
                "input_path changed while pages were being extracted",
                {"input_path": str(source)},
                409,
            )
        if output.exists() and not overwrite:
            raise AdapterError(
                "OUTPUT_EXISTS",
                "output_path appeared while pages were being extracted",
                {"output_path": str(output)},
                409,
            )
        os.replace(staged_path, output)

    observed = _verify_pdf(
        output,
        expected_page_count=end_page - start_page + 1,
        expected_text_fingerprints=expected_fingerprints,
        PdfReader=PdfReader,
    )
    if not observed["passed"]:
        raise AdapterError(
            "PDF_OUTPUT_VERIFICATION_FAILED",
            "the persisted PDF did not match the selected source page range",
            {"output_path": str(output), "observed": observed},
            422,
        )
    return {
        "input_path": str(source),
        "source_sha256": source_sha256,
        "source_page_count": page_count,
        "output_path": str(output),
        "output_sha256": _sha256_file(output),
        "start_page": start_page,
        "end_page": end_page,
        "page_count": end_page - start_page + 1,
        "output_backend": output_backend,
        "status": "overwritten" if existed_before else "created",
        "size_bytes": output.stat().st_size,
        **_public_text_fingerprints(expected_fingerprints),
        "verification": {
            "passed": True,
            "source_unchanged": _sha256_file(source) == source_sha256,
            "match_mode": observed["match_mode"],
            "producer": observed["producer"],
        },
    }


def split_pdf_by_outline(params: dict[str, Any], timeout: float) -> dict[str, Any]:
    PdfReader, PdfWriter = _load_pypdf()
    source = _source_file(params["input_path"])
    output_directory = normalize_local_path(
        params.get("output_directory", str(source.parent))
    )
    if output_directory.exists() and not output_directory.is_dir():
        raise AdapterError(
            "INVALID_ARGUMENT",
            f"output_directory is not a directory: {output_directory}",
        )
    output_directory.mkdir(parents=True, exist_ok=True)
    output_directory = output_directory.resolve()

    outline_level = int(params.get("outline_level", 1))
    filename_style = params.get("filename_style", "number_and_title")
    start_index = int(params.get("start_index", 1))
    include_prefix_pages = bool(params.get("include_prefix_pages", False))
    overwrite = bool(params.get("overwrite", False))
    output_backend_requested = params.get("output_backend", "auto")
    deadline = time.monotonic() + max(0.1, timeout)

    source_sha256 = _sha256_file(source)
    try:
        reader = PdfReader(str(source))
        if reader.is_encrypted:
            raise AdapterError(
                "ENCRYPTED_PDF_UNSUPPORTED",
                "input_path is encrypted and cannot be split deterministically",
                http_status=422,
            )
        page_count = len(reader.pages)
        if page_count < 1:
            raise AdapterError(
                "EMPTY_PDF", "input_path contains no pages", http_status=422
            )
        outline_entries = _outline_entries(reader, outline_level)
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "INVALID_PDF",
            "input_path is not a readable PDF",
            {"path": str(source), "error": str(exc)},
            422,
        ) from exc

    sections: list[dict[str, Any]] = []
    output_keys: set[str] = set()
    for position, entry in enumerate(outline_entries):
        start_page_index = entry["page_index"]
        if position == 0 and include_prefix_pages:
            start_page_index = 0
        end_page_index = (
            outline_entries[position + 1]["page_index"] - 1
            if position + 1 < len(outline_entries)
            else page_count - 1
        )
        output_name = _output_name(
            title=entry["title"],
            number=start_index + position,
            filename_style=filename_style,
        )
        output_path = (output_directory / output_name).resolve()
        if output_path == source:
            raise AdapterError(
                "OUTPUT_CONFLICT",
                "a generated output path would replace input_path",
                {"output_path": str(output_path)},
                409,
            )
        output_key = output_name.casefold()
        if output_key in output_keys:
            raise AdapterError(
                "OUTPUT_NAME_COLLISION",
                "multiple outline entries produce the same output filename",
                {"output_name": output_name},
                409,
            )
        output_keys.add(output_key)
        sections.append(
            {
                "title": entry["title"],
                "source_start_page": start_page_index + 1,
                "source_end_page": end_page_index + 1,
                "page_count": end_page_index - start_page_index + 1,
                "output_path": output_path,
            }
        )

    for section in sections:
        if time.monotonic() >= deadline:
            raise AdapterError(
                "OPERATION_TIMEOUT",
                "PDF split deadline expired during output preflight",
                http_status=504,
            )
        start = section["source_start_page"] - 1
        end = section["source_end_page"]
        section["text_fingerprints"] = _page_text_fingerprints(reader.pages[start:end])
        output_path = section["output_path"]
        section["existed_before"] = output_path.exists()
        if output_path.exists() and not overwrite:
            observed = _verify_pdf(
                output_path,
                expected_page_count=section["page_count"],
                expected_text_fingerprints=section["text_fingerprints"],
                PdfReader=PdfReader,
            )
            if not observed["passed"]:
                raise AdapterError(
                    "OUTPUT_EXISTS",
                    "an output already exists but does not match the source page segment; "
                    "set overwrite=true to replace it",
                    {
                        "output_path": str(output_path),
                        "expected_page_count": section["page_count"],
                        "expected_text_fingerprints": section["text_fingerprints"],
                        "observed": observed,
                    },
                    409,
                )
            section["status"] = "reused"
            section["verification_match_mode"] = observed["match_mode"]
            section["producer"] = observed["producer"]

    output_backend_used, reference_output_producers = _selected_output_backend(
        output_backend_requested, sections
    )

    staged: list[tuple[Path, dict[str, Any]]] = []
    with tempfile.TemporaryDirectory(
        prefix=".osworld-pdf-split-", dir=output_directory
    ) as temporary_directory:
        staging_root = Path(temporary_directory)
        for position, section in enumerate(sections):
            if section.get("status") == "reused":
                continue
            if time.monotonic() >= deadline:
                raise AdapterError(
                    "OPERATION_TIMEOUT",
                    "PDF split deadline expired while writing outputs",
                    http_status=504,
                )
            start = section["source_start_page"] - 1
            end = section["source_end_page"]
            staged_path = staging_root / f"{position:06d}.pdf"
            if output_backend_used == "cairo":
                _write_cairo_pages(
                    source=source,
                    start=start,
                    end=end,
                    staged_path=staged_path,
                    deadline=deadline,
                )
            else:
                _write_preserved_pages(
                    reader=reader,
                    start=start,
                    end=end,
                    staged_path=staged_path,
                    PdfWriter=PdfWriter,
                )
            observed = _verify_pdf(
                staged_path,
                expected_page_count=section["page_count"],
                expected_text_fingerprints=section["text_fingerprints"],
                PdfReader=PdfReader,
            )
            if not observed["passed"]:
                raise AdapterError(
                    "PDF_OUTPUT_VERIFICATION_FAILED",
                    "a staged PDF did not match its source page segment",
                    {
                        "output_path": str(section["output_path"]),
                        "observed": observed,
                    },
                    422,
                )
            staged.append((staged_path, section))

        for staged_path, section in staged:
            output_path = section["output_path"]
            if output_path.exists() and not overwrite:
                raise AdapterError(
                    "OUTPUT_EXISTS",
                    "an output appeared after preflight and overwrite is false",
                    {"output_path": str(output_path)},
                    409,
                )
            os.replace(staged_path, output_path)
            section["status"] = (
                "overwritten" if section["existed_before"] else "created"
            )

    outputs: list[dict[str, Any]] = []
    for section in sections:
        output_path = section["output_path"]
        observed = _verify_pdf(
            output_path,
            expected_page_count=section["page_count"],
            expected_text_fingerprints=section["text_fingerprints"],
            PdfReader=PdfReader,
        )
        if not observed["passed"]:
            raise AdapterError(
                "PDF_OUTPUT_VERIFICATION_FAILED",
                "a committed PDF did not match its source page segment",
                {"output_path": str(output_path), "observed": observed},
                422,
            )
        outputs.append(
            {
                "title": section["title"],
                "source_start_page": section["source_start_page"],
                "source_end_page": section["source_end_page"],
                "page_count": section["page_count"],
                "path": str(output_path),
                "size_bytes": output_path.stat().st_size,
                **_public_text_fingerprints(section["text_fingerprints"]),
                "status": section["status"],
                "verification_match_mode": observed["match_mode"],
                "producer": observed["producer"],
            }
        )

    source_sha256_after = _sha256_file(source)
    if source_sha256_after != source_sha256:
        raise AdapterError(
            "SOURCE_PDF_CHANGED",
            "input_path changed while it was being split",
            {
                "before_sha256": source_sha256,
                "after_sha256": source_sha256_after,
            },
            409,
        )
    return {
        "input_path": str(source),
        "source_sha256": source_sha256,
        "source_page_count": page_count,
        "output_directory": str(output_directory),
        "outline_level": outline_level,
        "filename_style": filename_style,
        "start_index": start_index,
        "include_prefix_pages": include_prefix_pages,
        "overwrite": overwrite,
        "output_backend_requested": output_backend_requested,
        "output_backend_used": output_backend_used,
        "reference_output_producers": reference_output_producers,
        "output_count": len(outputs),
        "created_count": sum(item["status"] == "created" for item in outputs),
        "reused_count": sum(item["status"] == "reused" for item in outputs),
        "overwritten_count": sum(item["status"] == "overwritten" for item in outputs),
        "outputs": outputs,
        "verification": {
            "passed": True,
            "source_unchanged": True,
            "verified_output_count": len(outputs),
            "output_backend": output_backend_used,
        },
    }
