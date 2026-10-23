from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
)
from writer_adapter import uno_worker


def enumeration(values):
    iterator = iter(values)
    remaining = list(iterator)
    return SimpleNamespace(
        hasMoreElements=lambda: bool(remaining),
        nextElement=lambda: remaining.pop(0),
    )


def footer(text="1", *, alignment=0, page_number=True, offset=0):
    field = SimpleNamespace(
        supportsService=lambda name: page_number
        and name == "com.sun.star.text.TextField.PageNumber",
        Offset=offset,
        NumberingType=4,
        SubType=SimpleNamespace(value="CURRENT"),
    )
    paragraph = SimpleNamespace(
        supportsService=lambda name: name == "com.sun.star.text.Paragraph",
        ParaAdjust=alignment,
        createEnumeration=lambda: enumeration([SimpleNamespace(TextField=field)]),
    )
    return SimpleNamespace(
        String=text, createEnumeration=lambda: enumeration([paragraph])
    )


def document(styles):
    collection = SimpleNamespace(
        getElementNames=lambda: tuple(styles), getByName=styles.__getitem__
    )
    return SimpleNamespace(
        StyleFamilies=SimpleNamespace(getByName=lambda _name: collection)
    )


def style(**overrides):
    return SimpleNamespace(
        **{
            "IsPhysical": True,
            "isInUse": lambda: True,
            "FooterIsOn": True,
            "FooterIsShared": True,
            "FirstIsShared": True,
            "FooterText": footer(),
        }
        | overrides
    )


def test_native_footer_field_is_not_inferred_from_literal_digits():
    doc = document(
        {
            "Body": style(),
            "Literal": style(FooterText=footer(page_number=False)),
        }
    )

    records = uno_worker._footer_summary(doc)

    assert records[0]["page_number_fields"] == [
        {
            "paragraph_index": 0,
            "alignment": "left",
            "offset": 0,
            "numbering_type": 4,
            "sub_type": "current",
        }
    ]
    assert records[1]["text"] == "1"
    assert records[1]["page_number_fields"] == []
    assert doc.StyleFamilies.getByName("PageStyles").getByName("Body").FooterText.String == "1"


def test_footer_variants_have_independent_native_fields_and_alignment():
    doc = document(
        {
            "Alternating": style(
                FooterIsShared=False,
                FirstIsShared=False,
                FooterTextRight=footer(alignment=1, offset=2),
                FooterTextLeft=footer(alignment=0),
                FooterTextFirst=footer("Cover", page_number=False),
            )
        }
    )

    records = uno_worker._footer_summary(doc)

    assert [record["variant"] for record in records] == ["right", "left", "first"]
    assert records[0]["page_number_fields"][0]["alignment"] == "right"
    assert records[0]["page_number_fields"][0]["offset"] == 2
    assert records[1]["page_number_fields"][0]["alignment"] == "left"
    assert records[2]["page_number_fields"] == []


def test_disabled_footer_and_unused_template_are_not_read_as_content():
    disabled = SimpleNamespace(IsPhysical=True, isInUse=lambda: True, FooterIsOn=False)
    unused = SimpleNamespace(IsPhysical=False, isInUse=lambda: False)

    records = uno_worker._footer_summary(document({"Body": disabled, "Unused": unused}))

    assert records == [{"page_style": "Body", "in_use": True, "enabled": False}]


@pytest.mark.parametrize("forwarded", [False, True])
def test_footer_readback_survives_existing_model_context_budget(forwarded):
    footers = uno_worker._footer_summary(document({"Body": style()}))
    result = {
        "paragraphs": ["Observed body text. " * 25] * 30,
        "paragraph_count": 30,
        "nonempty_paragraph_count": 30,
        "paragraph_details": [
            {"index": i, "text": "Observed body text. " * 25} for i in range(30)
        ],
        "footers": footers,
    }
    original = deepcopy(result)
    body = {"status": "ok", "result": result}
    hint = adapter_context_hint("libreoffice_writer", "document.inspect", body)
    if forwarded:
        hint = {"downstream_action": "document.inspect", "downstream_context": hint}

    projected = compact_context_hint_for_model(hint, remaining_chars=5000)
    context = projected["downstream_context"] if forwarded else projected

    assert context["footers"] == footers
    assert result == original
