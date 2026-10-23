from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from os_adapter.errors import AdapterError, error_payload
from os_adapter.pdf_forms import fill_pdf_form, inspect_pdf_form


@pytest.fixture
def form_pdf(tmp_path):
    path = tmp_path / "synthetic form.pdf"
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
    )
    roots = ArrayObject()
    for index, section in enumerate(("Primary", "Secondary")):
        page = writer.add_blank_page(400, 400)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject({NameObject("/Helv"): font}),
            }
        )
        content = DecodedStreamObject()
        content.set_data(
            f"BT /Helv 12 Tf 20 370 Td (Original page {index + 1}) Tj ET".encode()
        )
        page[NameObject("/Contents")] = writer._add_object(content)
        group = DictionaryObject({NameObject("/T"): TextStringObject(section)})
        group_ref = writer._add_object(group)
        roots.append(group_ref)
        widgets = ArrayObject()
        for position, name in enumerate(("Entry", "Keep", "Locked", "Choice")):
            field = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Widget"),
                    NameObject("/FT"): NameObject(
                        "/Btn" if name == "Choice" else "/Tx"
                    ),
                    NameObject("/T"): TextStringObject(name),
                    NameObject("/TU"): TextStringObject(f"{section} {name} label"),
                    NameObject("/TM"): TextStringObject("unrelated mapping name"),
                    NameObject("/V"): TextStringObject(f"original {name}"),
                    NameObject("/Rect"): RectangleObject(
                        [20, 300 - position * 55, 350, 335 - position * 55]
                    ),
                    NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
                    NameObject("/Ff"): NumberObject(1 if name == "Locked" else 0),
                    NameObject("/Parent"): group_ref,
                    NameObject("/P"): page.indirect_reference,
                }
            )
            if name == "Entry":
                field[NameObject("/MaxLen")] = NumberObject(48)
            widgets.append(writer._add_object(field))
        group[NameObject("/Kids")] = widgets
        page[NameObject("/Annots")] = widgets
    writer.root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Fields"): roots,
                NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
                NameObject("/DR"): writer._add_object(
                    DictionaryObject(
                        {
                            NameObject("/Font"): writer._add_object(
                                DictionaryObject({NameObject("/Helv"): font})
                            )
                        }
                    )
                ),
            }
        )
    )
    writer.write(path)
    writer.close()
    return path


def test_inspect_qualified_names_original_labels_and_pagination(form_pdf):
    result = inspect_pdf_form({"input_path": str(form_pdf), "max_fields": 2}, 10)
    assert result["page_count"] == 2
    assert result["total_fields"] == 8
    assert result["next_offset"] == 2
    assert result["truncated"] is True
    assert result["fields"][0] == {
        "field_name": "Primary.Entry",
        "label": "Primary Entry label",
        "field_type": "/Tx",
        "value": "original Entry",
        "writable": True,
        "max_length": 48,
    }
    last = inspect_pdf_form({"input_path": str(form_pdf), "field_offset": 6}, 10)
    assert last["next_offset"] is None
    assert last["truncated"] is False
    assert [field["writable"] for field in last["fields"]] == [False, False]


def test_fill_preserves_pages_unselected_fields_and_exact_values(form_pdf, tmp_path):
    before = form_pdf.read_bytes()
    output = tmp_path / "new directory" / "filled.pdf"
    values = [
        {"field_name": "Primary.Entry", "value": "  café (sample) \\  "},
        {"field_name": "Secondary.Keep", "value": "A second page value"},
    ]
    result = fill_pdf_form(
        {"input_path": str(form_pdf), "output_path": str(output), "fields": values}, 10
    )
    assert result["verification_passed"] is True
    assert result["fields_updated"] == 2
    assert result["field_values"] == values
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert result["size_bytes"] == output.stat().st_size
    assert form_pdf.read_bytes() == before
    fields = {
        field["field_name"]: field
        for field in inspect_pdf_form({"input_path": str(output)}, 10)["fields"]
    }
    assert fields["Primary.Entry"]["value"] == values[0]["value"]
    assert fields["Secondary.Entry"]["value"] == "original Entry"
    assert fields["Primary.Keep"]["value"] == "original Keep"
    reader = PdfReader(output)
    assert [page.extract_text() for page in reader.pages] == [
        "Original page 1",
        "Original page 2",
    ]
    assert reader.root_object["/AcroForm"]["/NeedAppearances"].value is False
    for page_index, field_index in ((0, 0), (1, 1)):
        assert (
            reader.pages[page_index]["/Annots"][field_index]
            .get_object()["/AP"]["/N"]
            .get_data()
        )


@pytest.mark.parametrize(
    ("name", "value", "error"),
    [
        ("Entry", "x", "PDF_FORM_FIELD_NOT_FOUND"),
        ("Missing", "x", "PDF_FORM_FIELD_NOT_FOUND"),
        ("Primary.Locked", "x", "PDF_FORM_FIELD_NOT_WRITABLE"),
        ("Primary.Choice", "x", "PDF_FORM_FIELD_NOT_WRITABLE"),
        ("Primary.Entry", "x" * 49, "INVALID_ARGUMENT"),
    ],
)
def test_invalid_field_leaves_no_output(form_pdf, tmp_path, name, value, error):
    output = tmp_path / "not created" / "filled.pdf"
    with pytest.raises(AdapterError) as caught:
        fill_pdf_form(
            {
                "input_path": str(form_pdf),
                "output_path": str(output),
                "fields": [{"field_name": name, "value": value}],
            },
            10,
        )
    assert caught.value.code == error
    assert not output.parent.exists()


@pytest.mark.parametrize(
    ("requested_name", "matching_names"),
    [
        ("Primary Entry label", ["Primary.Entry"]),
        ("primary entry label", []),
    ],
)
def test_label_name_error_keeps_exact_candidates_in_parent_feedback(
    form_pdf, tmp_path, requested_name, matching_names
):
    before = form_pdf.read_bytes()
    output = tmp_path / "not created" / "filled.pdf"
    params = {
        "input_path": str(form_pdf),
        "output_path": str(output),
        "fields": [{"field_name": requested_name, "value": "caller selected text"}],
    }
    original_params = deepcopy(params)

    with pytest.raises(AdapterError) as caught:
        fill_pdf_form(params, 10)

    error = caught.value
    assert error.code == "PDF_FORM_FIELD_NOT_FOUND"
    assert error.http_status == 422
    assert error.details["field_name"] == requested_name
    assert error.details.get("field_names_with_matching_label", []) == matching_names
    assert not output.parent.exists()
    assert form_pdf.read_bytes() == before
    assert params == original_params

    native = error_payload(error)
    event = ExecutionEvent(
        step=1,
        timestamp_utc="2026-09-13T00:00:00Z",
        proposed={
            "kind": "adapter",
            "tool": "adapter__adapter_call",
            "action": "adapter.call",
            "arguments": {
                "adapter": "os",
                "action": "pdf.form.fill",
                "payload": {"params": params},
            },
        },
        executed=False,
        error={
            "status": "error",
            "error_code": "DOWNSTREAM_FAILED",
            "error": "downstream Adapter call failed",
            "details": {
                "adapter": "os",
                "response": {"status": "error", "error": native},
            },
        },
    )
    state = RuntimeState(
        task_id="synthetic-pdf-label-feedback",
        domain="multi_apps",
        instruction="Fill the observed PDF form using its actual field names.",
        events=[event],
    )
    original_events = deepcopy(state.events)
    messages = AgentProtocolMixin()._messages(
        state, b"png", execution_recovery=False
    )
    state_text = messages[2]["content"][0]["text"]
    summary = json.loads(state_text.split("\n")[1])
    observed = next(item for item in summary if item.get("step") == 1)

    assert observed["executed"] is False
    assert observed["error"]["details"]["response"]["error"] == native
    assert state.task_id not in state_text
    assert state.events == original_events
    assert params == original_params


def test_duplicate_field_rejected_before_output(form_pdf, tmp_path):
    output = tmp_path / "duplicate.pdf"
    with pytest.raises(AdapterError, match="duplicate"):
        fill_pdf_form(
            {
                "input_path": str(form_pdf),
                "output_path": str(output),
                "fields": [
                    {"field_name": "Primary.Entry", "value": "first"},
                    {"field_name": "Primary.Entry", "value": "second"},
                ],
            },
            10,
        )
    assert not output.exists()


def test_overwrite_and_source_protection(form_pdf, tmp_path):
    output = tmp_path / "filled.pdf"
    params = {
        "input_path": str(form_pdf),
        "output_path": str(output),
        "fields": [{"field_name": "Primary.Entry", "value": "initial"}],
    }
    fill_pdf_form(params, 10)
    saved = output.read_bytes()
    with pytest.raises(AdapterError) as caught:
        fill_pdf_form(params, 10)
    assert caught.value.code == "OUTPUT_EXISTS"
    assert output.read_bytes() == saved
    params["overwrite"] = True
    params["fields"][0]["value"] = "replacement"
    fill_pdf_form(params, 10)
    assert (
        inspect_pdf_form({"input_path": str(output)}, 10)["fields"][0]["value"]
        == "replacement"
    )
    params["output_path"] = str(form_pdf)
    with pytest.raises(AdapterError) as caught:
        fill_pdf_form(params, 10)
    assert caught.value.code == "OUTPUT_CONFLICT"


@pytest.mark.parametrize("widget_resources", [False, True])
def test_unicode_value_has_visible_appearance(form_pdf, tmp_path, widget_resources):
    fitz = pytest.importorskip("fitz")
    if widget_resources:
        writer = PdfWriter(clone_from=form_pdf)
        widget = writer.pages[0]["/Annots"][0].get_object()
        widget[NameObject("/DR")] = writer.root_object["/AcroForm"].raw_get("/DR")
        form_pdf = tmp_path / "widget resources.pdf"
        writer.write(form_pdf)
        writer.close()
    output = tmp_path / "unicode.pdf"
    value = "√ Café déjà vu"
    fill_pdf_form(
        {
            "input_path": str(form_pdf),
            "output_path": str(output),
            "fields": [{"field_name": "Primary.Entry", "value": value}],
        },
        10,
    )
    assert (
        inspect_pdf_form({"input_path": str(output)}, 10)["fields"][0]["value"] == value
    )
    document = fitz.open(output)
    # Bake existing widget appearances in memory so extraction tests their actual glyphs.
    document.bake(annots=True, widgets=True)
    assert value in document[0].get_text()
    assert document[0].get_pixmap().samples
    document.close()


def test_unavailable_glyph_does_not_claim_success(form_pdf, tmp_path):
    output = tmp_path / "unsupported.pdf"
    with pytest.raises(AdapterError) as caught:
        fill_pdf_form(
            {
                "input_path": str(form_pdf),
                "output_path": str(output),
                "fields": [{"field_name": "Primary.Entry", "value": "漢"}],
            },
            10,
        )
    assert caught.value.code == "PDF_FORM_FONT_UNSUPPORTED"
    assert not output.exists()


def test_detached_text_field_is_inspectable_but_not_writable(form_pdf, tmp_path):
    source = tmp_path / "detached widget.pdf"
    output = tmp_path / "must not exist.pdf"
    writer = PdfWriter(clone_from=form_pdf)
    writer.pages[0][NameObject("/Annots")] = ArrayObject(writer.pages[0]["/Annots"][1:])
    writer.write(source)
    writer.close()
    result = inspect_pdf_form({"input_path": str(source)}, 10)
    assert result["total_fields"] == 8
    detached = result["fields"][0]
    assert detached["field_name"] == "Primary.Entry"
    assert detached["value"] == "original Entry"
    assert detached["writable"] is False
    with pytest.raises(AdapterError) as caught:
        fill_pdf_form(
            {
                "input_path": str(source),
                "output_path": str(output),
                "fields": [{"field_name": "Primary.Entry", "value": "new text"}],
            },
            10,
        )
    assert caught.value.code == "PDF_FORM_FIELD_NOT_WRITABLE"
    assert not output.exists()


def test_shared_field_updates_widgets_on_both_pages(form_pdf, tmp_path):
    fitz = pytest.importorskip("fitz")
    source = tmp_path / "shared source.pdf"
    output = tmp_path / "shared result.pdf"
    writer = PdfWriter(clone_from=form_pdf)
    field = DictionaryObject(
        {
            NameObject("/T"): TextStringObject("Shared"),
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/V"): TextStringObject("old shared value"),
            NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
        }
    )
    field_ref = writer._add_object(field)
    widgets = ArrayObject()
    for page in writer.pages:
        widget = writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Annot"),
                    NameObject("/Subtype"): NameObject("/Widget"),
                    NameObject("/Parent"): field_ref,
                    NameObject("/P"): page.indirect_reference,
                    NameObject("/Rect"): RectangleObject([20, 25, 350, 65]),
                }
            )
        )
        widgets.append(widget)
        page["/Annots"].append(widget)
    field[NameObject("/Kids")] = widgets
    writer.root_object["/AcroForm"]["/Fields"].append(field_ref)
    writer.write(source)
    writer.close()
    value = "Shared √ Café"
    fill_pdf_form(
        {
            "input_path": str(source),
            "output_path": str(output),
            "fields": [{"field_name": "Shared", "value": value}],
        },
        10,
    )
    inspected = inspect_pdf_form({"input_path": str(output)}, 10)
    assert inspected["total_fields"] == 9
    assert inspected["fields"][-1]["value"] == value
    document = fitz.open(output)
    document.bake(annots=True, widgets=True)
    assert all(value in page.get_text() for page in document)
    document.close()


def test_comb_field_inherited_max_length_keeps_characters_in_separate_cells(
    form_pdf, tmp_path
):
    fitz = pytest.importorskip("fitz")
    source = tmp_path / "inherited comb.pdf"
    output = tmp_path / "filled comb.pdf"
    writer = PdfWriter(clone_from=form_pdf)
    page = writer.pages[0]
    field_ref = page["/Annots"][0]
    field = field_ref.get_object()
    widget = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/Parent"): field_ref,
            NameObject("/P"): page.indirect_reference,
            NameObject("/Rect"): field["/Rect"],
        }
    )
    widget_ref = writer._add_object(widget)
    for key in ("/Type", "/Subtype", "/P", "/Rect"):
        field.pop(key, None)
    field[NameObject("/Ff")] = NumberObject(1 << 24)
    field[NameObject("/MaxLen")] = NumberObject(4)
    field[NameObject("/Kids")] = ArrayObject([widget_ref])
    page["/Annots"][0] = widget_ref
    writer.write(source)
    writer.close()

    result = fill_pdf_form(
        {
            "input_path": str(source),
            "output_path": str(output),
            "fields": [{"field_name": "Primary.Entry", "value": "AB"}],
        },
        10,
    )
    assert result["verification_passed"] is True
    document = fitz.open(output)
    document.bake(annots=True, widgets=True)
    letters = {
        char["c"]: char
        for block in document[0].get_text("rawdict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        for char in span["chars"]
        if char["c"] in {"A", "B"}
    }
    assert set(letters) == {"A", "B"}
    assert letters["A"]["bbox"][2] < letters["B"]["bbox"][0]
    document.close()
