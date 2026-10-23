from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from impress_adapter import uno_worker
from integrations.lite_agent.adapter_results import (
    PRESENTATION_SELECTOR_GUIDANCE,
    adapter_context_hint,
    compact_context_hint_for_model,
    context_hint_for_model,
)
from integrations.lite_agent.tool_catalog import build_tools


def test_model_visible_shape_schema_explains_slide_and_shape_indices():
    tool = build_tools(
        "libreoffice_impress",
        ["shape.format_text"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )[0]["function"]
    properties = tool["parameters"]["properties"]

    assert "display_slide_number - 1" in properties["slide"]["description"]
    assert "native IDs, not visual positions" in properties["selector"]["description"]
    assert "complete tool_target" in tool["description"]
    assert tool["parameters"]["required"] == ["slide", "selector"]


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        (0, "left"),
        (1, "right"),
        (2, "justify"),
        (3, "center"),
        (4, "stretch"),
        (SimpleNamespace(value="RIGHT"), "right"),
        ("com.sun.star.style.ParagraphAdjust.BLOCK", "justify"),
        (None, None),
        (True, None),
        (99, None),
    ],
)
def test_native_shape_alignment_uses_named_semantics(native, expected):
    shape = SimpleNamespace(
        ParaAdjust=native,
        getText=lambda: SimpleNamespace(getString=lambda: "Sample text"),
    )

    result = uno_worker._shape_summary(shape, 7)

    assert result["text_style"]["alignment"] == expected


@pytest.mark.parametrize(("weight", "expected"), [(100.0, False), (150.0, True), (0.0, None)])
def test_native_bold_semantics_reach_model_without_losing_raw_weight(weight, expected):
    shape = SimpleNamespace(
        CharWeight=weight,
        getText=lambda: SimpleNamespace(getString=lambda: "Synthetic caption"),
    )
    native = uno_worker._shape_summary_at_path(shape, [4, 2, 1])
    body = inspection()
    body["result"]["slides"][0]["shapes"][1]["children"][1]["children"] = [native]
    hint = adapter_context_hint("libreoffice_impress", "presentation.inspect", body)
    normal = context_hint_for_model(
        "libreoffice_impress", "presentation.inspect", hint, strict_generic=True
    )
    bounded = compact_context_hint_for_model(normal, remaining_chars=7000)

    for projection in (normal, bounded):
        observed = next(
            item
            for item in projection["slides"][0]["text_shapes"]
            if item["path"] == [4, 2, 1]
        )
        assert observed["text_style"]["bold"] is expected
        assert observed["text_style"]["bold_weight"] == weight


@pytest.mark.parametrize("ignore_write", [False, True])
def test_format_receipt_reads_alignment_without_echoing_model_argument(
    monkeypatch, ignore_write
):
    class Shape:
        ParaAdjust = 0

        def getText(self):
            return SimpleNamespace(getString=lambda: "Sample text")

        def __setattr__(self, name, value):
            if not (ignore_write and name == "ParaAdjust"):
                super().__setattr__(name, value)

    shape = Shape()
    session = SimpleNamespace(
        page=lambda index: object(), shape=lambda page, selector: shape
    )
    params = {"slide": 6, "selector": {"path": [4, 2]}, "alignment": "right"}
    original = deepcopy(params)
    monkeypatch.setattr(uno_worker, "_set_cursor_properties", lambda *args: None)
    monkeypatch.setattr(
        uno_worker, "_enum", lambda kind, value: SimpleNamespace(value=value)
    )

    result = uno_worker._format_text(session, params)
    hint = adapter_context_hint(
        "libreoffice_impress", "shape.format_text", {"result": result}
    )

    assert result["alignment"] == ("left" if ignore_write else "right")
    assert hint["alignment"] == result["alignment"]
    assert params == original
    assert result["text"] == "Sample text"


def inspection():
    def text(path, label, alignment, underline):
        return {
            "index": path[-1],
            "path": path,
            "name": label,
            "kind": "com.sun.star.drawing.CustomShape",
            "is_text": True,
            "text": label,
            "x": 1800,
            "y": 12000 if label == "Direct caption" else 1200,
            "text_style": {
                "alignment": alignment,
                "underline": underline,
                "font_size": 19,
            },
            "paragraphs": [{"index": 0, "text": label, "bullet": False}],
        }

    return {
        "result": {
            "identity": {
                "title": "Synthetic grouped text",
                "url": "file:///tmp/grouped.odp",
            },
            "slide_count": 9,
            "inspected_slides": [5, 7],
            "slides": [
                {
                    "index": 5,
                    "width": 24000,
                    "height": 18000,
                    "shapes": [
                        text([1], "Direct caption", "left", 0),
                        {
                            "index": 4,
                            "path": [4],
                            "kind": "com.sun.star.drawing.GroupShape",
                            "children": [
                                text([4, 0], "Grouped heading", "center", 1),
                                {
                                    "index": 2,
                                    "path": [4, 2],
                                    "kind": "com.sun.star.drawing.GroupShape",
                                    "children": [
                                        text([4, 2, 1], "Nested caption", "right", 0),
                                    ],
                                },
                            ],
                        },
                    ],
                },
                {
                    "index": 7,
                    "width": 24000,
                    "height": 18000,
                    "shapes": [
                        {
                            "index": 2,
                            "path": [2],
                            "kind": "com.sun.star.drawing.GroupShape",
                            "children": [
                                text([2, 0], "Second page text", "justify", 1),
                            ],
                        },
                    ],
                },
            ],
        }
    }


@pytest.mark.parametrize("forwarded", [False, True])
def test_grouped_text_paths_and_style_survive_normal_and_bounded_projection(forwarded):
    body = inspection()
    original = deepcopy(body)
    domain, action = "libreoffice_impress", "presentation.inspect"
    if forwarded:
        domain, action = "multi_apps", "adapter.call"
        body = {
            "result": {
                "adapter": "libreoffice_impress",
                "action": "presentation.inspect",
                "response": body,
            }
        }
    hint = adapter_context_hint(domain, action, body)
    original_hint = deepcopy(hint)
    normal = context_hint_for_model(domain, action, hint, strict_generic=True)
    bounded = compact_context_hint_for_model(normal, remaining_chars=7000)

    for projection in (normal, bounded):
        context = projection["downstream_context"] if forwarded else projection
        assert PRESENTATION_SELECTOR_GUIDANCE in context["guidance"]
        assert [(slide["slide_index"], slide["display_slide_number"]) for slide in context["slides"]] == [
            (5, 6), (7, 8)
        ]
        assert all("slide" not in slide for slide in context["slides"])
        shapes = [
            shape for slide in context["slides"] for shape in slide["text_shapes"]
        ]
        assert [shape["path"] for shape in shapes] == [[4, 0], [4, 2, 1], [1], [2, 0]]
        assert [shape["y"] for shape in shapes] == [1200, 1200, 12000, 1200]
        assert [shape["text_style"]["alignment"] for shape in shapes] == [
            "center",
            "right",
            "left",
            "justify",
        ]
        assert [shape["text_style"]["underline"] for shape in shapes] == [1, 0, 0, 1]
        assert [shape["paragraphs"][0]["text"] for shape in shapes] == [
            "Grouped heading",
            "Nested caption",
            "Direct caption",
            "Second page text",
        ]
        for slide in context["slides"]:
            assert slide["text_shape_order"] == "top_to_bottom_then_left_to_right"
            for shape in slide["text_shapes"]:
                assert shape["tool_target"] == {
                    "slide": slide["slide_index"], "selector": {"path": shape["path"]}
                }
    canonical = hint["downstream_context"] if forwarded else hint
    assert [slide["slide"] for slide in canonical["slides"]] == [5, 7]
    assert hint == original_hint
    assert len(json.dumps(bounded)) <= 7000
    assert (body["result"]["response"] if forwarded else body) == original


def test_text_targets_keep_native_order_when_geometry_is_incomplete():
    body = inspection()
    del body["result"]["slides"][0]["shapes"][0]["y"]
    original = deepcopy(body)
    hint = adapter_context_hint("libreoffice_impress", "presentation.inspect", body)
    normal = context_hint_for_model(
        "libreoffice_impress", "presentation.inspect", hint, strict_generic=True
    )
    bounded = compact_context_hint_for_model(normal, remaining_chars=7000)
    for projection in (normal, bounded):
        slide = projection["slides"][0]
        assert slide["text_shape_order"] == "native"
        assert [shape["path"] for shape in slide["text_shapes"]] == [[1], [4, 0], [4, 2, 1]]
        assert all(shape["tool_target"]["slide"] == 5 for shape in slide["text_shapes"])
    assert body == original
