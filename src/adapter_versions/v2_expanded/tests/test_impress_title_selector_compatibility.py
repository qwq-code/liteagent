from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from jsonschema import validate
import pytest

from impress_adapter import uno_worker
from impress_adapter.errors import AdapterError
from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.impress_title_formatting import (
    constrain_tool_schema,
    title_format_argument_contract_errors,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools


def _shape(path, name="Heading", text="Research Overview", kind="TitleTextShape"):
    return {
        "index": path[-1],
        "path": path,
        "name": name,
        "text": text,
        "kind": f"com.sun.star.presentation.{kind}",
        "x": 100,
        "y": 100,
    }


class _NativeShapes:
    def __init__(self, shapes):
        self.shapes = shapes

    def getCount(self):
        return len(self.shapes)

    def getByIndex(self, index):
        shape = self.shapes[index]
        native = _NativeShapes(shape.get("children", []))
        native.Name = shape["name"]
        native.ShapeType = shape["kind"]
        native.getText = lambda: SimpleNamespace(getString=lambda: shape["text"])
        return native


def _state(shapes):
    response = {"result": {"slides": [{"index": 2, "shapes": shapes}]}}
    result = {
        "adapter_response": response,
        "context_hint": adapter_context_hint(
            "libreoffice_impress", "presentation.inspect", response
        ),
    }
    return RuntimeState(
        task_id="synthetic-title-selector",
        domain="libreoffice_impress",
        instruction="Make the title on slide 3 bold.",
        events=[ExecutionEvent(
            step=1,
            timestamp_utc="2026-09-13T00:00:00Z",
            proposed={
                "kind": "adapter",
                "action": "presentation.inspect",
                "arguments": {"slides": [2]},
            },
            executed=True,
            result=result,
        )],
    )


def _check(shapes, selector, accepted):
    arguments = {"slide": 2, "selector": selector, "bold": True}
    original = deepcopy(arguments)
    errors = title_format_argument_contract_errors(
        _state(shapes), "shape.format_text", arguments
    )
    assert (not errors) is accepted
    session = uno_worker.ImpressSession.__new__(uno_worker.ImpressSession)
    if accepted:
        selected = session.shape(_NativeShapes(shapes), selector)
        assert selected.Name == "Heading"
    else:
        with pytest.raises(AdapterError):
            session.shape(_NativeShapes(shapes), selector)
    assert arguments == original


@pytest.mark.parametrize("locator", [{"path": [0]}, {"index": 0}, {}])
def test_composite_selector_matches_native_without_rewriting_arguments(locator):
    _check(
        [_shape([0])],
        {**locator, "name": "Heading", "text": "Research Overview", "kind": "TITLEtext"},
        True,
    )


@pytest.mark.parametrize(
    "mismatch",
    [
        {"path": [1]},
        {"name": "Different heading"},
        {"text": "Research Overview "},
        {"text": "research overview"},
        {"kind": "OutlinerShape"},
    ],
)
def test_composite_selector_does_not_ignore_conflicting_fields(mismatch):
    selector = {
        "path": [0], "name": "Heading", "text": "Research Overview", "kind": "TitleTextShape"
    }
    _check([_shape([0])], {**selector, **mismatch}, False)


def test_composite_metadata_disambiguates_duplicate_names():
    shapes = [
        _shape([0]),
        _shape([1], text="Body content", kind="OutlinerShape"),
    ]
    _check(shapes, {"name": "Heading"}, False)
    _check(shapes, {"name": "Heading", "text": "Research Overview"}, True)


def test_native_ambiguity_includes_shapes_outside_the_text_projection():
    shapes = [
        _shape([0]),
        _shape([1], text="", kind="CustomShape"),
    ]
    _check(shapes, {"name": "Heading"}, False)
    _check(shapes, {"name": "Heading", "kind": "TitleTextShape"}, True)


def test_nested_title_requires_full_path_when_using_a_positional_selector():
    group = _shape([0], name="Group", text="", kind="GroupShape")
    group["children"] = [_shape([0, 0])]
    _check([group], {"path": [0, 0], "name": "Heading"}, True)
    _check([group], {"index": 0, "name": "Heading"}, False)


@pytest.mark.parametrize("text", ["Research Overview\n", "Research " * 40 + "Overview"])
def test_exact_raw_text_survives_display_line_truncation(text):
    shapes = [_shape([0], text=text)]
    state = _state(shapes)
    display_lines = state.events[0].result["context_hint"]["slides"][0]["text_shapes"][0]["lines"]
    displayed = "\n".join(display_lines)
    assert displayed != text
    _check(shapes, {"path": [0], "text": text}, True)
    _check(shapes, {"path": [0], "text": displayed}, False)


def test_title_schema_describes_and_accepts_combined_selectors():
    function = build_tools(
        "libreoffice_impress", ["shape.format_text"],
        include_gui=False, include_control_tools=False, strict_generic=True,
    )[0]["function"]
    constrain_tool_schema(function, "Make the title on slide 3 bold.")
    selector_schema = function["parameters"]["properties"]["selector"]
    assert "Combined fields must all match" in selector_schema["description"]
    assert "Exactly one" not in selector_schema["description"]
    validate(
        {"slide": 2, "selector": {"path": [0], "name": "Heading", "kind": "TitleTextShape"}, "bold": True},
        function["parameters"],
    )
