from __future__ import annotations

import hashlib
import json
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Iterable


WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PACKAGE_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
OFFICE_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
MAX_SOURCE_BYTES = 20_000_000
MAX_SELECTED_VALUES = 2_000
MAX_OUTPUT_CHARACTERS = 5_000_000

ET.register_namespace("w", WORD_NAMESPACE)


class JsonDocumentError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _matches_key(
    candidate: str,
    selected: str,
    *,
    mode: str,
    case_sensitive: bool,
) -> bool:
    if not case_sensitive:
        candidate = candidate.casefold()
        selected = selected.casefold()
    return candidate == selected if mode == "exact" else selected in candidate


def collect_string_values(
    value: Any,
    *,
    value_key: str,
    key_match_mode: str,
    key_case_sensitive: bool,
) -> tuple[list[str], list[str]]:
    selected: list[str] = []
    available_string_keys: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if isinstance(child, str):
                    available_string_keys.add(str(key))
                    if _matches_key(
                        str(key),
                        value_key,
                        mode=key_match_mode,
                        case_sensitive=key_case_sensitive,
                    ):
                        selected.append(child)
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return selected, sorted(available_string_keys, key=lambda item: item.casefold())


def collect_provider_responses(
    value: Any,
    *,
    provider_name: str,
    key_match_mode: str,
    key_case_sensitive: bool,
    response_field: str | None,
) -> tuple[list[str], list[str], list[str]]:
    selected: list[str] = []
    available_provider_keys: set[str] = set()
    unresolved_object_keys: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                key_text = str(key)
                if isinstance(child, (str, dict, list)):
                    available_provider_keys.add(key_text)
                if _matches_key(
                    key_text,
                    provider_name,
                    mode=key_match_mode,
                    case_sensitive=key_case_sensitive,
                ):
                    if isinstance(child, str):
                        selected.append(child)
                    elif isinstance(child, (dict, list)):
                        if response_field is None:
                            unresolved_object_keys.append(key_text)
                        else:
                            nested, _available = collect_string_values(
                                child,
                                value_key=response_field,
                                key_match_mode="exact",
                                key_case_sensitive=False,
                            )
                            if nested:
                                selected.extend(nested)
                            else:
                                unresolved_object_keys.append(key_text)
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return (
        selected,
        sorted(available_provider_keys, key=lambda item: item.casefold()),
        unresolved_object_keys,
    )


def render_json_string_literal(value: str) -> str:
    """Return the characters between the JSON string's quotes verbatim."""
    encoded = json.dumps(value, ensure_ascii=False)
    return encoded[1:-1]


def _highlight_pattern(
    terms: list[str], case_sensitive: bool
) -> re.Pattern[str] | None:
    if not terms:
        return None
    ordered = sorted(terms, key=lambda value: (-len(value), value.casefold(), value))
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile("|".join(re.escape(term) for term in ordered), flags)


def _paragraph_runs(
    text: str,
    *,
    pattern: re.Pattern[str] | None,
) -> Iterable[tuple[str, bool]]:
    if pattern is None:
        if text:
            yield text, False
        return
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            yield text[cursor : match.start()], False
        yield match.group(0), True
        cursor = match.end()
    if cursor < len(text):
        yield text[cursor:], False


def _document_xml(
    paragraphs: list[str],
    *,
    highlight_terms: list[str],
    highlight_case_sensitive: bool,
) -> bytes:
    document = ET.Element(f"{{{WORD_NAMESPACE}}}document")
    body = ET.SubElement(document, f"{{{WORD_NAMESPACE}}}body")
    pattern = _highlight_pattern(highlight_terms, highlight_case_sensitive)
    for text in paragraphs:
        paragraph = ET.SubElement(body, f"{{{WORD_NAMESPACE}}}p")
        for value, highlighted in _paragraph_runs(text, pattern=pattern):
            run = ET.SubElement(paragraph, f"{{{WORD_NAMESPACE}}}r")
            if highlighted:
                properties = ET.SubElement(run, f"{{{WORD_NAMESPACE}}}rPr")
                ET.SubElement(
                    properties,
                    f"{{{WORD_NAMESPACE}}}highlight",
                    {f"{{{WORD_NAMESPACE}}}val": "yellow"},
                )
            node = ET.SubElement(run, f"{{{WORD_NAMESPACE}}}t")
            node.set(f"{{{XML_NAMESPACE}}}space", "preserve")
            node.text = value
    section = ET.SubElement(body, f"{{{WORD_NAMESPACE}}}sectPr")
    ET.SubElement(
        section,
        f"{{{WORD_NAMESPACE}}}pgSz",
        {
            f"{{{WORD_NAMESPACE}}}w": "12240",
            f"{{{WORD_NAMESPACE}}}h": "15840",
        },
    )
    return ET.tostring(document, encoding="utf-8", xml_declaration=True)


def _content_types_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Types xmlns="{CONTENT_TYPES_NAMESPACE}">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/>'
        "</Types>"
    ).encode("utf-8")


def _package_relationships_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_RELATIONSHIPS_NAMESPACE}">'
        f'<Relationship Id="rId1" Type="{OFFICE_RELATIONSHIPS_NAMESPACE}/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    ).encode("utf-8")


def _document_relationships_xml() -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_RELATIONSHIPS_NAMESPACE}"/>'
    ).encode("utf-8")


def _write_member(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, content)


def _read_document_state(path: Path) -> tuple[list[str], list[str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise JsonDocumentError(
                    "DOCX_VERIFICATION_FAILED",
                    "generated DOCX contains a corrupt member",
                )
            names = sorted(archive.namelist())
            document = ET.fromstring(archive.read("word/document.xml"))
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise JsonDocumentError(
            "DOCX_VERIFICATION_FAILED",
            "generated output is not a readable DOCX package",
            {"error": f"{type(exc).__name__}: {exc}"},
        ) from exc
    paragraphs = []
    body = document.find(f"{{{WORD_NAMESPACE}}}body")
    if body is None:
        raise JsonDocumentError(
            "DOCX_VERIFICATION_FAILED", "generated DOCX has no document body"
        )
    for paragraph in body.findall(f"{{{WORD_NAMESPACE}}}p"):
        paragraphs.append(
            "".join(
                node.text or "" for node in paragraph.iter(f"{{{WORD_NAMESPACE}}}t")
            )
        )
    return paragraphs, names


def _highlight_counts(
    paragraphs: list[str], terms: list[str], *, case_sensitive: bool
) -> dict[str, int]:
    flags = 0 if case_sensitive else re.IGNORECASE
    return {
        term: sum(
            len(re.findall(re.escape(term), paragraph, flags))
            for paragraph in paragraphs
        )
        for term in terms
    }


def create_docx_from_json_values(params: dict[str, Any]) -> dict[str, Any]:
    source_path = Path(params["source_path"]).expanduser()
    output_path = Path(params["output_path"]).expanduser()
    if not source_path.is_file():
        raise JsonDocumentError(
            "JSON_SOURCE_NOT_FOUND",
            "the selected JSON source file does not exist",
            {"source_path": str(source_path)},
        )
    source_size = source_path.stat().st_size
    if source_size > MAX_SOURCE_BYTES:
        raise JsonDocumentError(
            "JSON_SOURCE_TOO_LARGE",
            "the selected JSON source exceeds the deterministic size limit",
            {"source_bytes": source_size, "max_source_bytes": MAX_SOURCE_BYTES},
        )
    try:
        data = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsonDocumentError(
            "JSON_SOURCE_INVALID",
            "the selected source is not valid UTF-8 JSON",
            {"error": f"{type(exc).__name__}: {exc}"},
        ) from exc

    values, available_keys, unresolved_object_keys = collect_provider_responses(
        data,
        provider_name=params["provider_name"],
        key_match_mode=params.get("key_match_mode", "exact"),
        key_case_sensitive=params.get("key_case_sensitive", False),
        response_field=params.get("response_field"),
    )
    if unresolved_object_keys:
        raise JsonDocumentError(
            "JSON_PROVIDER_RESPONSE_FIELD_REQUIRED",
            "the selected provider has object-valued responses; explicitly select the "
            "nested response_field and retry",
            {
                "provider_name": params["provider_name"],
                "object_matches": len(unresolved_object_keys),
                "available_provider_keys": available_keys[:100],
                "explicit_retry_required": True,
            },
        )
    if not values:
        raise JsonDocumentError(
            "JSON_PROVIDER_RESPONSES_NOT_FOUND",
            "no string responses matched the model-selected provider name",
            {
                "provider_name": params["provider_name"],
                "available_provider_keys": available_keys[:100],
                "explicit_retry_required": True,
            },
        )
    if len(values) > MAX_SELECTED_VALUES:
        raise JsonDocumentError(
            "TOO_MANY_JSON_VALUES",
            "the selected key matched too many string values",
            {"selected_values": len(values), "maximum": MAX_SELECTED_VALUES},
        )

    rendered = [render_json_string_literal(value) for value in values]
    if sum(map(len, rendered)) > MAX_OUTPUT_CHARACTERS:
        raise JsonDocumentError(
            "DOCUMENT_CONTENT_TOO_LARGE",
            "the selected strings exceed the deterministic document size limit",
            {"maximum_characters": MAX_OUTPUT_CHARACTERS},
        )
    paragraphs: list[str] = []
    for index, value in enumerate(rendered):
        if index and params.get("blank_paragraph_between", True):
            paragraphs.append("")
        paragraphs.append(value)

    if output_path.exists() and not params.get("overwrite", False):
        raise JsonDocumentError(
            "OUTPUT_EXISTS",
            "the selected output path already exists; explicitly allow overwrite to replace it",
            {"output_path": str(output_path), "explicit_retry_required": True},
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document_xml = _document_xml(
        paragraphs,
        highlight_terms=params.get("highlight_terms", []),
        highlight_case_sensitive=params.get("highlight_case_sensitive", True),
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
        with zipfile.ZipFile(temporary_path, "w") as archive:
            _write_member(archive, "[Content_Types].xml", _content_types_xml())
            _write_member(archive, "_rels/.rels", _package_relationships_xml())
            _write_member(archive, "word/document.xml", document_xml)
            _write_member(
                archive,
                "word/_rels/document.xml.rels",
                _document_relationships_xml(),
            )
        observed_paragraphs, members = _read_document_state(temporary_path)
        if observed_paragraphs != paragraphs:
            raise JsonDocumentError(
                "DOCX_VERIFICATION_FAILED",
                "generated paragraph text does not match the selected JSON values",
            )
        temporary_path.replace(output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    highlight_terms = params.get("highlight_terms", [])
    counts = _highlight_counts(
        paragraphs,
        highlight_terms,
        case_sensitive=params.get("highlight_case_sensitive", True),
    )
    return {
        "source_path": str(source_path),
        "output_path": str(output_path),
        "provider_name": params["provider_name"],
        "response_field": params.get("response_field"),
        "selected_values": len(values),
        "paragraph_count": len(paragraphs),
        "blank_paragraph_count": len(paragraphs) - len(values),
        "string_representation": "json_literal",
        "highlight_counts": counts,
        "output_bytes": output_path.stat().st_size,
        "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "verification": {
            "passed": True,
            "checks": [
                {"type": "docx_package", "passed": True, "members": members},
                {
                    "type": "paragraph_text",
                    "passed": True,
                    "paragraph_count": len(paragraphs),
                },
                {
                    "type": "highlight_occurrences",
                    "passed": True,
                    "counts": counts,
                },
            ],
            "expected_state": {
                "selected_values": len(values),
                "paragraph_count": len(paragraphs),
                "highlight_counts": counts,
            },
            "observed_state": {
                "selected_values": len(values),
                "paragraph_count": len(observed_paragraphs),
                "highlight_counts": counts,
            },
        },
    }
