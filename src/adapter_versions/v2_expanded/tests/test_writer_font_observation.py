from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from writer_adapter import uno_worker


FONT_PROPERTIES = ("CharFontName", "CharFontNameAsian", "CharFontNameComplex")


def native_text(names, *, states=None, ignore_writes=False):
    values = dict(zip(FONT_PROPERTIES, names, strict=True))
    property_states = dict(
        zip(FONT_PROPERTIES, states or ["DIRECT_VALUE"] * 3, strict=True)
    )

    class Cursor:
        def gotoRange(self, end, expand):
            assert end == "end" and expand is True

        def getPropertyState(self, name):
            state = property_states[name]
            if state is None:
                raise AttributeError(name)
            return SimpleNamespace(value=state)

        def getPropertyValue(self, name):
            return values[name]

        def setPropertyValue(self, name, value):
            if not ignore_writes:
                values[name] = value

    cursor = Cursor()
    text = SimpleNamespace(
        String="Native sample text.",
        getStart=lambda: "start",
        getEnd=lambda: "end",
        createTextCursorByRange=lambda start: cursor,
    )
    return text, values


def document(body, *cells):
    cell_map = {f"A{i + 1}": SimpleNamespace(Text=text) for i, text in enumerate(cells)}
    table = SimpleNamespace(
        Name="ObservedTable",
        Rows=SimpleNamespace(Count=len(cells)),
        Columns=SimpleNamespace(Count=1),
        getCellNames=lambda: tuple(cell_map),
        getCellByName=cell_map.__getitem__,
    )
    tables = {"ObservedTable": table} if cells else {}
    return SimpleNamespace(
        Text=body,
        getTextTables=lambda: SimpleNamespace(
            getElementNames=lambda: tuple(tables), getByName=tables.__getitem__
        ),
        isModified=lambda: False,
    )


def test_font_summary_reads_body_and_cells_with_separate_script_properties():
    body, _ = native_text(["Sample Sans", "Sample CJK", "Sample Arabic"])
    cell, _ = native_text(["Sample Serif", "Sample CJK", "Sample Arabic"])

    summary = uno_worker._font_summary(document(body, cell))

    assert summary["scope"] == "body_and_table_cells"
    assert summary["text_object_count"] == 2
    assert summary["western"] == {
        "names": ["Sample Sans", "Sample Serif"],
        "mixed_text_objects": 0,
        "unknown_text_objects": 0,
    }
    assert summary["asian"]["names"] == ["Sample CJK"]
    assert summary["complex"]["names"] == ["Sample Arabic"]
    assert body.String == cell.String == "Native sample text."


@pytest.mark.parametrize(
    ("value", "state", "names", "mixed", "unknown"),
    [
        ("Sample Serif", "DEFAULT_VALUE", ["Sample Serif"], 0, 0),
        ("Sample Serif", "AMBIGUOUS_VALUE", [], 1, 0),
        ("Sample Serif", None, [], 0, 1),
        (None, "DIRECT_VALUE", [], 0, 1),
        ("", "DIRECT_VALUE", [], 0, 1),
    ],
)
def test_unknown_or_mixed_fonts_do_not_become_uniform_evidence(
    value, state, names, mixed, unknown
):
    body, _ = native_text([value] * 3, states=[state] * 3)

    summary = uno_worker._font_summary(document(body))

    for script in ("western", "asian", "complex"):
        assert summary[script] == {
            "names": names,
            "mixed_text_objects": mixed,
            "unknown_text_objects": unknown,
        }


def test_unavailable_cursor_keeps_unknown_font_evidence():
    summary = uno_worker._font_summary(document(SimpleNamespace()))

    assert summary["text_object_count"] == 1
    assert summary["western"]["unknown_text_objects"] == 1
    assert summary["western"]["names"] == []


@pytest.mark.parametrize("ignore_writes", [False, True])
def test_set_font_receipt_contains_native_observation_not_requested_echo(ignore_writes):
    body, values = native_text(["Sample Sans"] * 3, ignore_writes=ignore_writes)
    params = {"font_name": "Sample Serif"}
    original = deepcopy(params)

    result = uno_worker._set_font(SimpleNamespace(doc=document(body)), params)

    assert result["font_name"] == "Sample Serif"
    observed = "Sample Sans" if ignore_writes else "Sample Serif"
    assert result["fonts"]["western"]["names"] == [observed]
    assert set(values.values()) == {observed}
    assert params == original
    assert body.String == "Native sample text."


def test_inspection_exposes_native_font_summary(monkeypatch):
    body, _ = native_text(["Sample Sans"] * 3)
    monkeypatch.setattr(uno_worker, "_paragraphs", lambda text: [])
    monkeypatch.setattr(uno_worker, "_page_layout_summary", lambda doc: [])
    monkeypatch.setattr(uno_worker, "_footer_summary", lambda doc: [])
    monkeypatch.setattr(uno_worker, "_highlight_summary", lambda doc: {})
    monkeypatch.setattr(uno_worker, "_graphic_object_count", lambda doc: 0)
    session = SimpleNamespace(doc=document(body), identity=lambda: {}, path=None)

    result = uno_worker._inspect(session, {})

    assert result["fonts"]["western"]["names"] == ["Sample Sans"]


@pytest.mark.parametrize("forwarded", [False, True])
def test_native_font_summary_survives_bounded_model_projection(forwarded):
    body, _ = native_text(["Sample Sans"] * 3)
    fonts = uno_worker._font_summary(document(body))
    result = {
        "paragraphs": ["Native sample text. " * 25] * 30,
        "paragraph_count": 30,
        "paragraph_details": [
            {"index": i, "text": "Native sample text. " * 25} for i in range(30)
        ],
        "fonts": fonts,
    }
    original = deepcopy(result)
    response = {"status": "ok", "result": result}
    if forwarded:
        response = {
            "status": "ok",
            "result": {
                "adapter": "libreoffice_writer",
                "action": "document.inspect",
                "response": response,
            },
        }
    hint = adapter_context_hint(
        "multi_apps" if forwarded else "libreoffice_writer",
        "adapter.call" if forwarded else "document.inspect",
        response,
    )

    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    context = projected["downstream_context"] if forwarded else projected

    assert context["fonts"] == fonts
    assert result == original
