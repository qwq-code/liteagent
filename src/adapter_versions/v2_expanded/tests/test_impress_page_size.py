from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from impress_adapter import uno_worker
from impress_adapter.errors import AdapterError
from impress_adapter.schema import ACTIONS, parse_action_request
from impress_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from integrations.lite_agent.adapter_results import (
    adapter_context_hint,
    compact_context_hint_for_model,
    context_hint_for_model,
)
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    build_tools,
    public_actions,
    search_actions,
)


ACTION = "presentation.set_page_size"


class Pages:
    def __init__(self, values):
        self.values = values

    def getCount(self):
        return len(self.values)

    def getByIndex(self, index):
        return self.values[index]


def page(width, height):
    return SimpleNamespace(
        Width=width,
        Height=height,
        shapes=[{"text": "Sample content", "x": 1300, "y": 2400, "width": 6500, "height": 2100}],
        notes="Speaker notes",
    )


def session():
    slides = Pages([page(21000, 29700), page(28000, 15750)])
    masters = Pages([page(21000, 29700), page(28000, 15750)])
    return SimpleNamespace(
        pages=slides,
        doc=SimpleNamespace(getMasterPages=lambda: masters),
        identity=lambda: {"title": "Sample deck", "url": "file:///tmp/sample.odp"},
    )


def payload(params, **extras):
    return parse_action_request({"action": ACTION, "params": params, **extras}).to_worker_payload()


def exposed_schema():
    return build_tools(
        "libreoffice_impress", [ACTION], include_gui=False,
        include_control_tools=False, strict_generic=True,
    )[0]["function"]["parameters"]


def test_page_size_uses_one_public_schema_and_keeps_the_retired_macro_absent():
    assert ACTION in ACTIONS and ACTION in uno_worker.ACTIONS
    assert ACTION in public_actions("libreoffice_impress")
    owner = STRICT_ACTION_PARAM_SCHEMAS[ACTION]
    assert DIRECT_ACTION_SCHEMAS["libreoffice_impress"][ACTION] == owner
    assert exposed_schema()["properties"] == owner["properties"]
    assert "slide.set_orientation" not in ACTIONS
    assert set(owner["properties"]) == {"width", "height"}


@pytest.mark.parametrize("dimensions", [(14500, 23000), (33000, 18500), (17500, 17500)])
def test_page_size_changes_every_canvas_without_touching_content_or_saving(monkeypatch, dimensions):
    native = session()
    pages = native.pages.values + native.doc.getMasterPages().values
    before_content = deepcopy([(item.shapes, item.notes) for item in pages])
    params = dict(zip(("width", "height"), dimensions))
    original = deepcopy(params)
    jsonschema.validate(params, exposed_schema())
    monkeypatch.setattr(uno_worker, "ImpressSession", lambda selector: native)

    response = uno_worker.execute(payload(params))

    assert response["verification"]["passed"] is True
    assert response["verification"]["checks"]
    assert [(item.Width, item.Height) for item in pages] == [dimensions] * 4
    assert [(item.shapes, item.notes) for item in pages] == before_content
    assert params == original
    assert response["result"]["after"]["slides"] == [params, params]
    assert response["result"]["after"]["masters"] == [params, params]
    hint = adapter_context_hint("libreoffice_impress", ACTION, response)
    assert hint["slides"] == [params, params]
    assert hint["verification_passed"] is True


def test_page_size_cannot_report_success_when_a_native_page_ignores_the_write(monkeypatch):
    class IgnoringWidth:
        Width = property(lambda self: 21000, lambda self, value: None)
        Height = 29700

    native = session()
    native.pages.values[1] = IgnoringWidth()
    monkeypatch.setattr(uno_worker, "ImpressSession", lambda selector: native)

    response = uno_worker.execute(payload(
        {"width": 16000, "height": 24000},
        verify=[{"type": "document_identity"}],
    ))

    assert response["verification"]["passed"] is False
    assert response["verification"]["error_code"] == "VERIFICATION_FAILED"
    assert response["result"]["after"]["slides"][1]["width"] == 21000
    hint = adapter_context_hint("libreoffice_impress", ACTION, response)
    assert hint["verification_passed"] is False


@pytest.mark.parametrize("params", [
    {"width": 0, "height": 21000},
    {"width": True, "height": 21000},
    {"width": 16000.5, "height": 21000},
    {"width": 2147483648, "height": 21000},
    {"width": 16000},
    {"width": 16000, "height": 21000, "orientation": "portrait"},
])
def test_page_size_schema_and_adapter_agree_on_invalid_arguments(params):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(params, exposed_schema())
    with pytest.raises(AdapterError):
        payload(params)


@pytest.mark.parametrize("query", ["portrait landscape page orientation", "custom slide canvas width height"])
def test_page_size_is_retrievable_without_an_instruction_specific_route(query):
    matches = search_actions("libreoffice_impress", query, strict_generic=True)
    assert ACTION in {item["action"] for item in matches}


def test_native_orientation_survives_normal_and_bounded_inspection_projection():
    body = {"result": {
        "identity": {"url": "file:///tmp/sample.odp", "title": "Sample deck"},
        "slide_count": 1,
        "slides": [{"index": 0, "width": 23123, "height": 11234, "orientation": "landscape", "shapes": []}],
    }}
    original = deepcopy(body)
    hint = adapter_context_hint("libreoffice_impress", "presentation.inspect", body)
    normal = context_hint_for_model("libreoffice_impress", "presentation.inspect", hint, strict_generic=True)
    compact = compact_context_hint_for_model(normal, remaining_chars=1800)

    for value in (hint, normal, compact):
        assert value["slides"][0]["orientation"] == "landscape"
    assert body == original
