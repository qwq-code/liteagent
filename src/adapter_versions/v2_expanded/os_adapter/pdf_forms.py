from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .errors import AdapterError
from .pdf_tools import _load_pypdf, _output_file, _read_pdf, _sha256_file, _source_file


def _fields(reader: Any) -> dict[str, dict[str, Any]]:
    """Read qualified /T names, without substituting optional /TM mapping names."""
    form = reader.root_object.get("/AcroForm", {})
    form = form.get_object() if hasattr(form, "get_object") else form
    found: dict[str, dict[str, Any]] = {}

    def visit(reference: Any, ancestors: tuple[str, ...]) -> None:
        field = reference.get_object()
        name = field.get("/T")
        path = (*ancestors, str(name)) if name is not None else ancestors
        children = [child.get_object() for child in field.get("/Kids", [])]
        named_children = [child for child in children if "/T" in child]
        if name is not None and not named_children:
            qualified = ".".join(path)
            if qualified in found:
                raise AdapterError(
                    "AMBIGUOUS_PDF_FORM_FIELD",
                    "the PDF contains duplicate fully qualified field names",
                    {"field_name": qualified},
                    422,
                )
            found[qualified] = field
        for child in named_children:
            visit(child, path)

    for root in form.get("/Fields", []):
        visit(root, ())
    return found


def _field_value(field: Any) -> Any:
    value = field.get_inherited("/V", None)
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return str(value)


def _widgets(field: Any) -> list[Any]:
    if field.get("/Subtype") == "/Widget":
        return [field]
    return [
        child.get_object()
        for child in field.get("/Kids", [])
        if child.get_object().get("/Subtype") == "/Widget"
    ]


def _page_for_widget(reader: Any) -> dict[int, Any]:
    return {
        id(annotation.get_object()): page
        for page in reader.pages
        for annotation in page.get("/Annots", [])
    }


def _field_info(name: str, field: Any, pages: dict[int, Any]) -> dict[str, Any]:
    field_type = str(field.get_inherited("/FT", ""))
    widgets = _widgets(field)
    info = {
        "field_name": name,
        "label": str(field.get("/TU", "")),
        "field_type": field_type,
        "value": _field_value(field),
        "writable": (
            field_type == "/Tx"
            and not int(field.get_inherited("/Ff", 0)) & 1
            and bool(widgets)
            and all(id(widget) in pages for widget in widgets)
        ),
    }
    max_length = field.get_inherited("/MaxLen", None)
    if max_length is not None:
        info["max_length"] = int(max_length)
    return info


def inspect_pdf_form(params: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Inspect the existing fields of one AcroForm PDF without changing it."""
    PdfReader, _ = _load_pypdf()
    source = _source_file(params["input_path"])
    offset = params.get("field_offset", 0)
    limit = params.get("max_fields", 128)
    if type(offset) is not int or offset < 0:
        raise AdapterError(
            "INVALID_ARGUMENT", "field_offset must be a nonnegative integer"
        )
    if type(limit) is not int or not 1 <= limit <= 256:
        raise AdapterError(
            "INVALID_ARGUMENT", "max_fields must be an integer from 1 to 256"
        )
    reader = _read_pdf(source, PdfReader)
    fields = _fields(reader)
    pages = _page_for_widget(reader)
    selected = list(fields.items())[offset : offset + limit]
    truncated = offset + len(selected) < len(fields)
    return {
        "input_path": str(source),
        "page_count": len(reader.pages),
        "total_fields": len(fields),
        "field_offset": offset,
        "next_offset": offset + len(selected) if truncated else None,
        "truncated": truncated,
        "fields": [_field_info(name, field, pages) for name, field in selected],
    }


def _ensure_font_encoding(writer: Any, widget: Any, value: str) -> None:
    """Re-encode available standard Type1 glyphs when WinAnsi is insufficient."""
    from pypdf._codecs import adobe_glyphs, fill_from_encoding
    from pypdf._codecs.core_font_metrics import CORE_FONT_METRICS
    from pypdf._font import Font
    from pypdf._writer import TextStreamAppearance
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        NameObject,
        NumberObject,
        TextStringObject,
    )

    form = writer.root_object["/AcroForm"]
    appearance = str(widget.get_inherited("/DA", form.get("/DA", "/Helv 0 Tf 0 g")))
    match = re.search(r"(/[^\s]+)\s+[-+\d.]+\s+Tf\b", appearance)
    if match is None:
        raise AdapterError(
            "INVALID_PDF_FORM",
            "text field has no readable default font",
            http_status=422,
        )
    font_name = match.group(1)
    # Font encoding concerns visible characters, not multiline separators.
    visible_text = value.replace("\n", "").replace("\r", "")
    _, font = TextStreamAppearance._find_annotation_font_resource(
        font_name, widget, form, visible_text
    )
    if font.can_encode(visible_text):
        return
    metrics = CORE_FONT_METRICS.get(font.name)
    glyph_names: dict[str, str] = {}
    for glyph_name, character in adobe_glyphs.items():
        glyph_names.setdefault(character, glyph_name)
    if (
        font.sub_type != "Type1"
        or metrics is None
        or any(
            char not in metrics.character_widths or char not in glyph_names
            for char in visible_text
        )
    ):
        raise AdapterError(
            "PDF_FORM_FONT_UNSUPPORTED",
            "the text field font cannot display all requested characters; use a PDF with a compatible font",
            {"font": font.name},
            422,
        )
    encoding = dict(enumerate(fill_from_encoding("cp1252")))
    available = [
        code
        for code in range(1, 256)
        if code not in (10, 13) and encoding[code] not in visible_text
    ]
    differences = ArrayObject()
    for character in dict.fromkeys(visible_text):
        if character in encoding.values():
            continue
        if not available:
            raise AdapterError(
                "PDF_FORM_FONT_UNSUPPORTED",
                "too many distinct characters for the field font",
                http_status=422,
            )
        code = available.pop()
        encoding[code] = character
        differences.extend([NumberObject(code), NameObject(glyph_names[character])])
    resource = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/" + font.name),
            NameObject("/Encoding"): DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Encoding"),
                    NameObject("/BaseEncoding"): NameObject("/WinAnsiEncoding"),
                    NameObject("/Differences"): differences,
                }
            ),
        }
    )
    if not Font.from_font_resource(resource).can_encode(visible_text):
        raise AdapterError(
            "PDF_FORM_FONT_UNSUPPORTED",
            "requested characters could not be encoded",
            http_status=422,
        )
    form_resources = form.setdefault(NameObject("/DR"), DictionaryObject()).get_object()
    form_fonts = form_resources.setdefault(
        NameObject("/Font"), DictionaryObject()
    ).get_object()
    index = 1
    while f"/FormText{index}" in form_fonts:
        index += 1
    replacement_name = NameObject(f"/FormText{index}")
    reference = writer._add_object(resource)
    form_fonts[replacement_name] = reference
    inherited_resources = widget.get_inherited("/DR", form_resources).get_object()
    local_resources = DictionaryObject(inherited_resources)
    local_fonts = DictionaryObject(
        inherited_resources.get("/Font", DictionaryObject()).get_object()
    )
    local_fonts[replacement_name] = reference
    local_resources[NameObject("/Font")] = local_fonts
    widget[NameObject("/DR")] = local_resources
    widget[NameObject("/DA")] = TextStringObject(
        appearance[: match.start(1)] + replacement_name + appearance[match.end(1) :]
    )


def fill_pdf_form(params: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Write model-selected text values into one cloned PDF and verify storage."""
    PdfReader, PdfWriter = _load_pypdf()
    from pypdf._writer import TextStreamAppearance
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject

    deadline = time.monotonic() + max(0.1, timeout)
    source = _source_file(params["input_path"])
    output = _output_file(params["output_path"]).resolve()
    if output == source or (output.exists() and os.path.samefile(source, output)):
        raise AdapterError(
            "OUTPUT_CONFLICT",
            "output_path must not replace input_path",
            http_status=409,
        )
    overwrite = params.get("overwrite", False)
    if type(overwrite) is not bool:
        raise AdapterError("INVALID_ARGUMENT", "overwrite must be a boolean")
    if output.exists() and not overwrite:
        raise AdapterError(
            "OUTPUT_EXISTS",
            "output_path already exists; choose another path or set overwrite=true",
            http_status=409,
        )
    requested = params.get("fields")
    if not isinstance(requested, list) or not 1 <= len(requested) <= 128:
        raise AdapterError(
            "INVALID_ARGUMENT", "fields must contain 1 to 128 field_name/value objects"
        )
    reader = _read_pdf(source, PdfReader)
    original_fields = _fields(reader)
    original_pages = _page_for_widget(reader)
    values: dict[str, str] = {}
    for entry in requested:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("field_name"), str)
            or not isinstance(entry.get("value"), str)
        ):
            raise AdapterError(
                "INVALID_ARGUMENT", "each field requires field_name and value strings"
            )
        name, value = entry["field_name"], entry["value"]
        if name in values:
            raise AdapterError(
                "INVALID_ARGUMENT",
                "fields contains a duplicate field_name",
                {"field_name": name},
            )
        if name not in original_fields:
            details: dict[str, Any] = {"field_name": name}
            matching_names = [
                field_name
                for field_name, field in original_fields.items()
                if name and field.get("/TU") == name
            ]
            if matching_names:
                details["field_names_with_matching_label"] = matching_names
            raise AdapterError(
                "PDF_FORM_FIELD_NOT_FOUND",
                "field_name must exactly match a fully qualified name from pdf.form.inspect",
                details,
                422,
            )
        info = _field_info(name, original_fields[name], original_pages)
        if not info["writable"]:
            raise AdapterError(
                "PDF_FORM_FIELD_NOT_WRITABLE",
                "only writable text fields with widgets attached to PDF pages can be filled",
                info,
                422,
            )
        if "max_length" in info and len(value) > info["max_length"]:
            raise AdapterError(
                "INVALID_ARGUMENT",
                "value exceeds the text field's max_length",
                {"field_name": name, "max_length": info["max_length"]},
            )
        values[name] = value

    writer = PdfWriter(clone_from=reader)
    fields = _fields(writer)
    page_for_widget = _page_for_widget(writer)
    try:
        for name, value in values.items():
            if time.monotonic() >= deadline:
                raise AdapterError(
                    "TIMEOUT",
                    "PDF form filling exceeded the operation timeout",
                    http_status=504,
                )
            field = fields[name]
            field[NameObject("/V")] = TextStringObject(value)
            # A stale rich-text value can override the newly written plain text.
            field.pop("/RV", None)
            appearance_field = DictionaryObject(field)
            for key in ("/FT", "/Ff", "/Q", "/MaxLen"):
                inherited = field.get_inherited(key, None)
                if inherited is not None:
                    appearance_field[NameObject(key)] = inherited
            for widget in _widgets(field):
                _ensure_font_encoding(writer, widget, value)
                # pypdf reads comb width from the widget's local /MaxLen.
                # Preserve the field's inherited value for separate widgets.
                if "/MaxLen" not in widget and "/MaxLen" in appearance_field:
                    widget[NameObject("/MaxLen")] = appearance_field["/MaxLen"]
                page = page_for_widget.get(id(widget))
                if page is None:
                    raise AdapterError(
                        "INVALID_PDF_FORM",
                        "a text widget is not attached to a page",
                        {"field_name": name},
                        422,
                    )
                appearance = TextStreamAppearance.from_text_annotation(
                    writer,
                    page,
                    False,
                    writer.root_object["/AcroForm"],
                    appearance_field,
                    widget,
                )
                widget[NameObject("/AP")] = DictionaryObject(
                    {NameObject("/N"): writer._add_object(appearance)}
                )
        writer.set_need_appearances_writer(False)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".pdf-form-", dir=output.parent
        ) as temporary:
            staged = Path(temporary) / "output.pdf"
            writer.write(str(staged))
            verified = _read_pdf(staged, PdfReader)
            observed = _fields(verified)
            if len(verified.pages) != len(reader.pages) or any(
                name not in observed or _field_value(observed[name]) != value
                for name, value in values.items()
            ):
                raise AdapterError(
                    "PDF_OUTPUT_VERIFICATION_FAILED",
                    "the staged PDF did not preserve the requested form values",
                    http_status=422,
                )
            if output.exists() and not overwrite:
                raise AdapterError(
                    "OUTPUT_EXISTS",
                    "output_path appeared while the PDF was being filled",
                    http_status=409,
                )
            if overwrite:
                os.replace(staged, output)
            else:
                try:
                    os.link(staged, output)
                except FileExistsError as exc:
                    raise AdapterError(
                        "OUTPUT_EXISTS",
                        "output_path appeared while the PDF was being filled",
                        http_status=409,
                    ) from exc
    except AdapterError:
        raise
    except Exception as exc:
        raise AdapterError(
            "PDF_FORM_FILL_FAILED",
            "could not fill the PDF form",
            {"error": str(exc)},
            422,
        ) from exc
    finally:
        writer.close()
    return {
        "input_path": str(source),
        "output_path": str(output),
        "page_count": len(reader.pages),
        "fields_updated": len(values),
        "field_values": [
            {"field_name": name, "value": value} for name, value in values.items()
        ],
        "verification_passed": True,
        "sha256": _sha256_file(output),
        "size_bytes": output.stat().st_size,
    }
